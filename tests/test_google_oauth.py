import hashlib
import base64
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

import requests
from joserfc import jwt
from joserfc.jwk import RSAKey
from app import create_app


class GoogleOAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = RSAKey.generate_key(2048, parameters={'kid': 'sidoc-test'})
        cls.other_key = RSAKey.generate_key(2048, parameters={'kid': 'sidoc-test'})

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = dict(TESTING=True, DATA_DIR=self.tmp.name, SECRET_KEY='s'*64,
                           GOOGLE_CLIENT_ID='sidoc-test-client', GOOGLE_CLIENT_SECRET='server-only-test-secret',
                           GOOGLE_REDIRECT_URI='http://localhost/auth/google/callback')
        self.app = create_app(self.config)
        self.app.test_cli_runner().invoke(args=['create-admin', 'admin', '--password', 'test-password-123'])
        self.sql('UPDATE users SET google_email=? WHERE id=1', ('admin@example.com',))
        self.client = self.app.test_client()
        self.claim_overrides = {}
        self.use_bad_signature = False
        self.verifier_seen = False
        self.token_calls = 0
        self.patch = patch('requests.sessions.Session.request', autospec=True, side_effect=self.fake_http)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def sql(self, query, values=()):
        with sqlite3.connect(Path(self.tmp.name)/'sidoc.sqlite') as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, values).fetchall()
            return rows

    def fake_http(self, http_session, method, url, **kwargs):
        if url.endswith('/.well-known/openid-configuration'):
            payload = dict(issuer='https://accounts.google.com',
                           authorization_endpoint='https://accounts.google.com/o/oauth2/v2/auth',
                           token_endpoint='https://oauth2.googleapis.com/token',
                           jwks_uri='https://www.googleapis.com/oauth2/v3/certs',
                           token_endpoint_auth_methods_supported=['client_secret_basic'],
                           id_token_signing_alg_values_supported=['RS256'])
        elif url == 'https://www.googleapis.com/oauth2/v3/certs':
            payload = {'keys': [self.key.as_dict(private=False)]}
        elif url == 'https://oauth2.googleapis.com/token':
            self.token_calls += 1
            data = kwargs.get('data', {})
            if isinstance(data, str):
                data = {key: values[0] for key, values in parse_qs(data).items()}
            verifier = data.get('code_verifier', '')
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            self.verifier_seen = bool(verifier and challenge == self.authorization['code_challenge'][0])
            claims = dict(iss='https://accounts.google.com', aud='sidoc-test-client', sub='google-sub-1',
                          email='admin@example.com', email_verified=True, iat=int(time.time()),
                          exp=int(time.time())+300, nonce=self.authorization['nonce'][0])
            claims.update(self.claim_overrides)
            token = jwt.encode({'alg': 'RS256', 'kid': 'sidoc-test'}, claims,
                               self.other_key if self.use_bad_signature else self.key)
            payload = dict(access_token='access-token-not-for-cookies', token_type='Bearer', expires_in=300, id_token=token)
        else:
            raise AssertionError('Unexpected external request: ' + url)
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = json.dumps(payload).encode()
        response.headers['Content-Type'] = 'application/json'
        return response

    def start(self, client=None):
        client = client or self.client
        response = client.get('/auth/google')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.location).netloc, 'accounts.google.com')
        self.authorization = parse_qs(urlsplit(response.location).query)
        self.assertEqual(self.authorization['code_challenge_method'], ['S256'])
        self.assertIn('openid', self.authorization['scope'][0])
        self.assertNotIn('server-only-test-secret', response.location)
        return self.authorization['state'][0]

    def callback(self, state=None, client=None):
        state = state or self.start(client)
        return (client or self.client).get('/auth/google/callback?' + urlencode({'state': state, 'code': 'test-code'}))

    def signed_in(self, client=None):
        with (client or self.client).session_transaction() as session:
            return session.get('uid')

    def test_real_signed_id_token_state_nonce_and_pkce_log_in_authorized_user(self):
        response = self.callback()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/')
        self.assertTrue(self.verifier_seen)
        self.assertEqual(self.signed_in(), 1)
        self.assertEqual(self.sql('SELECT google_sub FROM users WHERE id=1')[0][0], 'google-sub-1')
        with self.client.session_transaction() as session:
            self.assertEqual(session['auth_method'], 'google')
            self.assertNotIn('access_token', session)
            self.assertNotIn('id_token', session)
            self.assertNotIn('refresh_token', session)
        self.assertIn('Inicio de sesión con Google', self.sql('SELECT description FROM events')[0][0])

    def test_invalid_signature_nonce_audience_issuer_expiry_and_unverified_email_rejected(self):
        cases = [('nonce', {'nonce': 'wrong'}), ('aud', {'aud': 'another-client'}),
                 ('iss', {'iss': 'https://attacker.example'}), ('exp', {'exp': int(time.time())-300}),
                 ('email_type', {'email': ['admin@example.com']}),
                 ('email_verified', {'email_verified': False}), ('string_verified', {'email_verified': 'true'})]
        for name, overrides in cases:
            with self.subTest(name=name):
                self.client = self.app.test_client()
                self.claim_overrides = overrides
                self.callback()
                self.assertIsNone(self.signed_in())
        self.claim_overrides = {}
        self.use_bad_signature = True
        self.client = self.app.test_client()
        self.callback()
        self.assertIsNone(self.signed_in())

    def test_missing_or_wrong_state_and_expired_flow_do_not_exchange_code(self):
        self.callback(state='unsolicited')
        self.assertEqual(self.token_calls, 0)
        self.start()
        self.callback(state='wrong-state')
        self.assertEqual(self.token_calls, 0)
        state = self.start()
        with self.client.session_transaction() as session:
            session['google_login_started'] = int(time.time())-601
        self.callback(state=state)
        self.assertEqual(self.token_calls, 0)
        self.assertIsNone(self.signed_in())

    def test_unknown_email_inactive_user_and_changed_subject_are_not_enrolled(self):
        self.claim_overrides = {'email': 'stranger@example.com'}
        self.callback()
        self.assertIsNone(self.signed_in())
        self.assertEqual(self.sql('SELECT count(*) FROM users')[0][0], 1)
        self.claim_overrides = {}
        self.sql('UPDATE users SET active=0 WHERE id=1')
        self.callback()
        self.assertIsNone(self.signed_in())
        self.sql('UPDATE users SET active=1,google_sub=? WHERE id=1', ('previous-owner',))
        self.callback()
        self.assertIsNone(self.signed_in())

    def test_personal_google_login_keeps_personal_permissions(self):
        self.sql("UPDATE users SET role='personal' WHERE id=1")
        self.callback()
        self.assertEqual(self.signed_in(), 1)
        self.assertEqual(self.client.get('/users').status_code, 403)
        self.assertEqual(self.client.get('/settings').status_code, 403)

    def test_optional_workspace_restriction_uses_verified_hd_claim(self):
        self.app.config['GOOGLE_WORKSPACE_DOMAIN'] = 'institution.example'
        self.callback()
        self.assertIsNone(self.signed_in())
        self.claim_overrides = {'hd': 'institution.example'}
        self.callback()
        self.assertEqual(self.signed_in(), 1)

    def test_canonical_origin_redirect_and_disabled_configuration(self):
        canonical = create_app(dict(self.config, GOOGLE_REDIRECT_URI='https://sidoc.example/auth/google/callback'))
        response = canonical.test_client().get('/auth/google')
        self.assertEqual(response.location, 'https://sidoc.example/auth/google')
        disabled = create_app(dict(self.config, GOOGLE_CLIENT_SECRET=''))
        client = disabled.test_client()
        self.assertEqual(client.get('/auth/google').location, '/login')
        self.assertNotIn(b'href="/auth/google"', client.get('/login').data)
        self.assertIn(b'href="/auth/google"', self.client.get('/login').data)
        self.assertIn(b'/static/branding/chachapoyas-login.png', self.client.get('/login').data)

    def post(self, path, data):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf']
        return self.client.post(path, data=dict(data, csrf=csrf), follow_redirects=True)

    def test_administrator_can_authorize_and_revoke_google_without_personal_escalation(self):
        self.post('/login', dict(username='admin', password='test-password-123'))
        self.post('/users', dict(username='ana', password='test-password-123', role='personal', google_email='ANA@example.com'))
        self.assertEqual(self.sql('SELECT google_email FROM users WHERE id=2')[0][0], 'ana@example.com')
        self.post('/users', dict(username='duplicate', password='test-password-123', role='admin', google_email='ana@example.com'))
        self.assertEqual(self.sql('SELECT count(*) FROM users')[0][0], 2)
        self.sql('UPDATE users SET google_sub=? WHERE id=2', ('ana-sub',))
        self.post('/users/2/update', dict(role='personal', active='on', google_email=''))
        row = self.sql('SELECT google_email,google_sub,auth_version FROM users WHERE id=2')[0]
        self.assertIsNone(row['google_email'])
        self.assertIsNone(row['google_sub'])
        self.assertEqual(row['auth_version'], 1)
