import io
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from app import create_app
from cloud_backend import HybridRow, StorageError, postgres_sql

PASSWORD = 'test-password-123'
PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.signed = []

    def sign_upload(self, key):
        self.signed.append(key)
        return 'https://supabase.test/storage/v1/object/upload/sign/' + key + '?token=test'

    def sign_download(self, key, filename):
        return 'https://supabase.test/storage/v1/object/sign/' + key + '?token=test&download=' + filename

    def read(self, key, limit):
        if key not in self.objects or len(self.objects[key]) > limit:
            raise StorageError('Unavailable or oversized')
        return self.objects[key]

    def put(self, key, content, mime):
        self.objects[key] = content

    def remove(self, key):
        self.objects.pop(key, None)


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        local = create_app({'TESTING': True, 'DATA_DIR': self.tmp.name})
        local.test_cli_runner().invoke(args=['create-admin', 'admin', '--password', PASSWORD])
        self.storage = FakeStorage()
        self.options = dict(TESTING=True, CLOUD_MODE=True, DATABASE_URL='not-used-in-unit-tests',
                            SUPABASE_URL='https://supabase.test', SUPABASE_SERVICE_ROLE_KEY='test-key',
                            SECRET_KEY='s' * 64, BOOTSTRAP_TOKEN='b' * 64,
                            DATA_DIR=self.tmp.name, DATABASE_FACTORY=self.connection, STORAGE_CLIENT=self.storage)
        self.app = create_app(self.options)
        self.client = self.app.test_client()
        self.post('/login', {'username': 'admin', 'password': PASSWORD})

    def tearDown(self):
        self.tmp.cleanup()

    def connection(self):
        connection = sqlite3.connect(Path(self.tmp.name) / 'sidoc.sqlite')
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        return connection

    def post(self, path, data=None, client=None):
        client = client or self.client
        client.get('/login')
        with client.session_transaction() as session:
            token = session['csrf']
        return client.post(path, data=dict(data or {}, csrf=token))

    def start(self, content=PDF):
        response = self.post('/api/uploads/start', {'title': 'Informe nube', 'code': 'INF-CLOUD',
                           'filename': 'informe.pdf', 'size': len(content), 'kind': 'Informe', 'folios': '2'})
        self.assertEqual(response.status_code, 200)
        ticket = response.get_json()['id']
        self.storage.objects[self.storage.signed[-1]] = content
        return ticket

    def count(self, table):
        connection = self.connection()
        result = connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        connection.close()
        return result

    def test_duplicate_cloud_pdf_is_rejected_and_cleaned(self):
        first = self.start()
        self.assertEqual(self.post('/api/uploads/complete', {'id': first}).status_code, 200)
        second = self.start()
        response = self.post('/api/uploads/complete', {'id': second})
        self.assertEqual(response.status_code, 409)
        self.assertIn('PDF exacto', response.get_json()['error'])
        self.assertEqual(self.count('documents'), 1)
        self.assertEqual(len(self.storage.objects), 1)

    def test_direct_upload_over_vercel_body_limit_and_idempotence(self):
        pdf = b'%PDF-1.4\n' + b'x' * (6 * 1024 * 1024) + b'\n%%EOF\n'
        ticket = self.start(pdf)
        self.assertEqual(self.count('documents'), 0)
        complete = self.post('/api/uploads/complete', {'id': ticket})
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(self.post('/api/uploads/complete', {'id': ticket}).status_code, 200)
        self.assertEqual(self.count('documents'), 1)
        response = self.client.get('/documents/1/download')
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.startswith('https://supabase.test/'))
        self.assertLess(len(response.data), 4096)
        self.assertFalse((Path(self.tmp.name) / 'pdfs' / self.storage.signed[-1]).exists())

    def test_reject_invalid_pdf_then_remove_uploaded_object(self):
        ticket = self.start(b'this is not a PDF')
        response = self.post('/api/uploads/complete', {'id': ticket})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.count('documents'), 0)
        self.assertFalse(self.storage.objects)

    def test_ticket_owner_and_expiry_are_enforced(self):
        ticket = self.start()
        self.post('/users', {'username': 'ana', 'password': PASSWORD, 'role': 'personal'})
        other = self.app.test_client()
        self.post('/login', {'username': 'ana', 'password': PASSWORD}, client=other)
        self.assertEqual(self.post('/api/uploads/complete', {'id': ticket}, client=other).status_code, 404)
        with self.connection() as connection:
            connection.execute('UPDATE pending_uploads SET expires=? WHERE id=?', (int(time.time())-1, ticket))
        self.assertEqual(self.post('/api/uploads/complete', {'id': ticket}).status_code, 400)

    def test_download_permissions_and_cloud_delete_cleanup(self):
        ticket = self.start()
        self.post('/api/uploads/complete', {'id': ticket})
        self.post('/users', {'username': 'ana', 'password': PASSWORD, 'role': 'personal'})
        other = self.app.test_client()
        self.post('/login', {'username': 'ana', 'password': PASSWORD}, client=other)
        self.assertEqual(other.get('/documents/1/download').status_code, 403)
        self.assertEqual(self.post('/documents/1/delete').status_code, 302)
        self.assertEqual(self.count('documents'), 0)
        self.assertFalse(self.storage.objects)

    def test_api_requires_session_and_csrf(self):
        anonymous = self.app.test_client()
        response = self.post('/api/uploads/start', {'title': 'X'}, client=anonymous)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.client.post('/api/uploads/start', data={}).status_code, 400)
        self.assertEqual(self.post('/upload', {}).status_code, 400)

    def test_storage_outage_keeps_deletion_for_retry(self):
        ticket = self.start()
        self.post('/api/uploads/complete', {'id': ticket})
        original = self.storage.remove
        def offline(key):
            raise StorageError('offline')
        self.storage.remove = offline
        self.post('/documents/1/delete')
        self.assertEqual(self.count('object_deletions'), 1)
        self.storage.remove = original
        self.post('/settings/storage-cleanup')
        self.assertEqual(self.count('object_deletions'), 0)
        self.assertFalse(self.storage.objects)

    def test_password_reset_revokes_other_sessions(self):
        other = self.app.test_client()
        self.post('/login', {'username': 'admin', 'password': PASSWORD}, client=other)
        self.post('/account', {'current': PASSWORD, 'password': 'new-password-123456'})
        self.assertEqual(other.get('/account').status_code, 302)
        self.assertEqual(self.client.get('/account').status_code, 200)

    def test_cloud_app_requires_credentials_instead_of_ephemeral_sqlite(self):
        with self.assertRaises(RuntimeError):
            create_app({'CLOUD_MODE': True, 'TESTING': True})

    def test_production_bootstrap_token_secure_cookies_https_and_health(self):
        with self.connection() as connection:
            connection.execute('DELETE FROM events')
            connection.execute('DELETE FROM users')
        app = create_app(dict(self.options, PRODUCTION=True))
        client = app.test_client()
        self.assertEqual(client.get('/login').status_code, 308)
        self.assertEqual(client.get('/healthz').status_code, 200)
        response = client.get('/setup', base_url='https://localhost')
        cookie = response.headers.get('Set-Cookie', '')
        for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', '__Host-sidoc'):
            self.assertIn(flag, cookie)
        self.assertIn('Strict-Transport-Security', response.headers)
        with client.session_transaction(base_url='https://localhost') as session:
            token = session['csrf']
        data = dict(username='first', password=PASSWORD, confirm=PASSWORD, csrf=token)
        self.assertEqual(client.post('/setup', data=data, base_url='https://localhost').status_code, 403)
        data['setup_token'] = 'b' * 64
        self.assertEqual(client.post('/setup', data=data, base_url='https://localhost').status_code, 302)
        self.assertEqual(client.get('/setup', base_url='https://localhost').status_code, 404)


class AdapterTests(unittest.TestCase):
    def test_private_schema_and_positional_row_compatibility(self):
        self.assertEqual(postgres_sql('SELECT * FROM users WHERE id=?'), 'SELECT * FROM sidoc.users WHERE id=%s')
        row = HybridRow(id=1, title='Prueba')
        self.assertEqual(row[0], 1)
        self.assertEqual(row['title'], 'Prueba')
