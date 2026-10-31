"""Google OpenID Connect login; roles remain controlled by SIDOC administrators."""
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit

import psycopg
import requests
from authlib.common.errors import AuthlibBaseError
from authlib.integrations.flask_client import OAuth
from flask import flash, g, redirect, request, session, url_for
from joserfc.errors import JoseError


DISCOVERY_URL = 'https://accounts.google.com/.well-known/openid-configuration'


def normalized_google_email(value):
    if value is not None and not isinstance(value, str):
        raise ValueError('El correo debe ser texto.')
    email = (value or '').strip().lower()
    if not email:
        return None
    if len(email) > 254 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError('Indica un correo válido para autorizar Google.')
    return email


def configure_google_login(app, db, audit):
    values = [app.config.get(key) for key in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_REDIRECT_URI')]
    enabled = all(values)
    uri = urlsplit(app.config.get('GOOGLE_REDIRECT_URI') or '')
    valid_uri = (uri.scheme == 'https' or (not app.config['PRODUCTION'] and uri.scheme == 'http'
                                         and uri.hostname in ('localhost', '127.0.0.1', '::1')))
    valid_uri = bool(valid_uri and uri.netloc and not uri.username and not uri.password
                     and uri.path == '/auth/google/callback' and not uri.query and not uri.fragment)
    enabled = bool(enabled and valid_uri)
    app.extensions['google_oauth_enabled'] = enabled
    if enabled:
        oauth = OAuth(app)
        app.extensions['google_client'] = oauth.register(
            name='google', client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'], server_metadata_url=DISCOVERY_URL,
            client_kwargs={'scope': 'openid email profile', 'code_challenge_method': 'S256', 'timeout': 15})
        if app.config['PRODUCTION']:
            app.config['TRUSTED_HOSTS'] = list(app.config.get('TRUSTED_HOSTS') or []) + [uri.hostname]

    def denied(message='No se pudo completar el acceso con Google. Inténtalo nuevamente.'):
        flash(message)
        return redirect(url_for('login'))

    @app.get('/auth/google')
    def google_login():
        if not enabled:
            return denied('El administrador todavía debe configurar el acceso con Google.')
        # State cookies and callback must be on the same canonical origin.
        origin = urlunsplit((uri.scheme, uri.netloc, '', '', ''))
        if request.host_url.rstrip('/') != origin:
            return redirect(origin + '/auth/google', code=302)
        session['google_login_started'] = int(time.time())
        try:
            return app.extensions['google_client'].authorize_redirect(
                app.config['GOOGLE_REDIRECT_URI'], nonce=secrets.token_urlsafe(32),
                code_verifier=secrets.token_urlsafe(48), prompt='select_account')
        except (AuthlibBaseError, JoseError, requests.RequestException, ValueError):
            session.pop('google_login_started', None)
            return denied('Google no está disponible en este momento. Inténtalo nuevamente.')

    @app.get('/auth/google/callback')
    def google_callback():
        started = session.pop('google_login_started', None)
        if not enabled or not isinstance(started, int) or not 0 <= time.time() - started <= 600:
            return denied('El acceso con Google venció o no fue iniciado desde este navegador.')
        try:
            # Authlib validates state, PKCE, signature, issuer, audience, expiry and nonce.
            token = app.extensions['google_client'].authorize_access_token(leeway=30)
            claims = token.get('userinfo')
            if not claims or not token.get('id_token') or claims.get('email_verified') is not True:
                return denied('Google no pudo confirmar un correo verificado para esta cuenta.')
            if claims.get('iss') != 'https://accounts.google.com':
                return denied()
            email = normalized_google_email(claims.get('email'))
            subject = claims.get('sub')
            if not email or not isinstance(subject, str) or not subject or len(subject) > 255:
                return denied()
            workspace = app.config.get('GOOGLE_WORKSPACE_DOMAIN', '').strip().lower()
            if workspace and claims.get('hd') != workspace:
                return denied('Esta cuenta no pertenece al dominio institucional autorizado.')
        except (AuthlibBaseError, JoseError, requests.RequestException, ValueError, TypeError):
            return denied()
        unauthorized = 'Esta cuenta no tiene acceso a SIDOC-OCI. Solicita autorización al administrador.'
        user = db().execute('SELECT * FROM users WHERE google_sub=? AND active=1', (subject,)).fetchone()
        if user:
            if user['google_email'] != email:
                return denied(unauthorized)
        else:
            user = db().execute('SELECT * FROM users WHERE google_email=? AND active=1', (email,)).fetchone()
            if not user or user['google_sub']:
                return denied(unauthorized)
            try:
                linked = db().execute('''UPDATE users SET google_sub=?
                    WHERE id=? AND google_email=? AND active=1 AND google_sub IS NULL RETURNING id''',
                    (subject, user['id'], email)).fetchone()
                if not linked:
                    db().rollback()
                    return denied(unauthorized)
            except (sqlite3.IntegrityError, psycopg.IntegrityError):
                db().rollback()
                return denied(unauthorized)
        # Do not retain access, refresh or identity tokens in cookies or the database.
        session.clear()
        session.update(uid=user['id'], auth_version=user['auth_version'],
                       csrf=secrets.token_hex(32), auth_method='google')
        session.permanent = True
        g.user = user
        audit('Inicio de sesión con Google')
        db().commit()
        return redirect(url_for('index'))
