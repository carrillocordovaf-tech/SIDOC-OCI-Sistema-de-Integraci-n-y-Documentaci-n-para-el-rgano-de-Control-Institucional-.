import csv
import functools
import io
import json
import time
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from cloud_backend import PostgresDatabase, PrivateStorage, StorageError
from google_auth import configure_google_login, normalized_google_email
import psycopg

from werkzeug.security import check_password_hash, generate_password_hash

TYPES = ('Informe', 'Oficio', 'Memorando', 'Acta', 'Otro')
STATES = ('Pendiente', 'En revisión', 'Archivado')


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(MAX_CONTENT_LENGTH=11 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
                      DATABASE_URL=os.environ.get('DATABASE_URL', ''),
                      SUPABASE_URL=os.environ.get('SUPABASE_URL', ''),
                      SUPABASE_SERVICE_ROLE_KEY=os.environ.get('SUPABASE_SERVICE_ROLE_KEY', ''),
                      SUPABASE_STORAGE_BUCKET=os.environ.get('SUPABASE_STORAGE_BUCKET', 'sidoc-documents'),
                      SECRET_KEY=os.environ.get('SECRET_KEY', ''),
                      BOOTSTRAP_TOKEN=os.environ.get('BOOTSTRAP_TOKEN', ''),
                      PRODUCTION=os.environ.get('SIDOC_ENV') == 'production' or os.environ.get('VERCEL') == '1',
                      GOOGLE_CLIENT_ID=os.environ.get('GOOGLE_CLIENT_ID', ''),
                      GOOGLE_CLIENT_SECRET=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
                      GOOGLE_REDIRECT_URI=os.environ.get('GOOGLE_REDIRECT_URI', ''),
                      GOOGLE_WORKSPACE_DOMAIN=os.environ.get('GOOGLE_WORKSPACE_DOMAIN', ''))
    if test_config:
        app.config.update(test_config)
    cloud = bool(app.config.get('CLOUD_MODE') or app.config['DATABASE_URL'] or os.environ.get('VERCEL') == '1')
    production = app.config['PRODUCTION']
    if production or cloud:
        required = ['DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SECRET_KEY', 'BOOTSTRAP_TOKEN']
        missing = [key for key in required if not app.config.get(key)]
        if missing:
            raise RuntimeError('Configura las variables privadas: ' + ', '.join(missing))
        if len(app.config['SECRET_KEY']) < 32 or len(app.config['BOOTSTRAP_TOKEN']) < 32:
            raise RuntimeError('SECRET_KEY y BOOTSTRAP_TOKEN deben tener al menos 32 caracteres.')
    root = Path(app.config.get('DATA_DIR', app.instance_path))
    uploads = root / 'pdfs'
    if not cloud:
        root.mkdir(parents=True, exist_ok=True)
        uploads.mkdir(exist_ok=True)
        key_file = root / 'session.key'
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(32))
            key_file.chmod(0o600)
        app.secret_key = app.config['SECRET_KEY'] or key_file.read_text()
    if cloud:
        app.extensions['private_storage'] = app.config.get('STORAGE_CLIENT') or PrivateStorage(
            app.config['SUPABASE_URL'], app.config['SUPABASE_SERVICE_ROLE_KEY'], app.config['SUPABASE_STORAGE_BUCKET'])
    app.extensions['cloud_mode'] = cloud
    if production:
        app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_NAME='__Host-sidoc')
        allowed = os.environ.get('ALLOWED_HOSTS', '').split(',')
        allowed += [os.environ.get('VERCEL_URL', ''), os.environ.get('VERCEL_PROJECT_PRODUCTION_URL', '')]
        app.config['TRUSTED_HOSTS'] = [h.strip() for h in allowed if h.strip()] or ['localhost', '127.0.0.1']
        # Vercel is the trusted TLS-terminating proxy; host forwarding stays disabled.
        if os.environ.get('VERCEL') == '1' or app.config.get('TRUST_PROXY_HEADERS'):
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0)

    def store():
        return app.extensions['private_storage']

    def db():
        if 'db' not in g:
            if app.config.get('DATABASE_FACTORY'):
                g.db = app.config['DATABASE_FACTORY']()
            elif cloud:
                g.db = PostgresDatabase(app.config['DATABASE_URL'])
            else:
                g.db = sqlite3.connect(root / 'sidoc.sqlite', timeout=15)
                g.db.row_factory = sqlite3.Row
                g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close_db(error):
        if 'db' in g:
            g.pop('db').close()

    if not cloud:
        with app.app_context():
            db().executescript('''
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
              password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','personal')));
            CREATE TABLE IF NOT EXISTS documents (
              id INTEGER PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,
              storage TEXT UNIQUE NOT NULL, owner INTEGER NOT NULL REFERENCES users(id),
              created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS expedients (
              id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
              owner INTEGER NOT NULL REFERENCES users(id), created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS favorites (
              user_id INTEGER REFERENCES users(id), document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
              PRIMARY KEY(user_id,document_id));
            CREATE TABLE IF NOT EXISTS loans (
              id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
              borrower TEXT NOT NULL, due TEXT NOT NULL, returned TEXT,
              created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan ON loans(document_id) WHERE returned IS NULL;
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, actor INTEGER REFERENCES users(id),
              description TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS login_attempts (address TEXT, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS pending_uploads (
              id TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES users(id), storage TEXT UNIQUE NOT NULL,
              metadata TEXT NOT NULL, expires INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL);
            CREATE TABLE IF NOT EXISTS object_deletions (storage TEXT PRIMARY KEY);
            ''')
            # Additive migration preserves accounts, PDF files and existing documents.
            for table, fields in {
                'users': {'active': 'INTEGER NOT NULL DEFAULT 1', 'auth_version': 'INTEGER NOT NULL DEFAULT 0',
                          'google_email': 'TEXT', 'google_sub': 'TEXT'},
                'documents': {'code': "TEXT NOT NULL DEFAULT ''", 'kind': "TEXT NOT NULL DEFAULT 'Otro'",
                              'unit': "TEXT NOT NULL DEFAULT ''", 'folios': 'INTEGER NOT NULL DEFAULT 0',
                              'size': 'INTEGER NOT NULL DEFAULT 0', 'status': "TEXT NOT NULL DEFAULT 'Pendiente'",
                              'expedient_id': 'INTEGER REFERENCES expedients(id)'}
            }.items():
                present = {row['name'] for row in db().execute(f'PRAGMA table_info({table})')}
                for field, definition in fields.items():
                    if field not in present:
                        db().execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
            db().execute('CREATE UNIQUE INDEX IF NOT EXISTS users_google_email ON users(google_email) WHERE google_email IS NOT NULL')
            db().execute('CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub ON users(google_sub) WHERE google_sub IS NOT NULL')
            db().commit()

    def audit(description):
        db().execute('INSERT INTO events(actor,description) VALUES (?,?)',
                     (g.user['id'] if getattr(g, 'user', None) else None, description))

    def settings():
        values = {'institution': 'Gobierno Regional Amazonas', 'contact': ''}
        values.update({r['key']: r['value'] for r in db().execute('SELECT * FROM settings')})
        return values

    @app.before_request
    def load_user():
        if request.endpoint == 'healthz':
            return
        if production and not request.is_secure:
            return redirect(request.url.replace('http://', 'https://', 1), code=308)
        g.user = db().execute('SELECT * FROM users WHERE id=? AND active=1', (session.get('uid'),)).fetchone()
        if g.user and session.get('auth_version', 0) != g.user['auth_version']:
            session.clear()
            g.user = None
        session.setdefault('csrf', secrets.token_hex(32))
        if request.method == 'POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf', '')):
            abort(400, 'Formulario vencido. Recarga la página e inténtalo de nuevo.')

    def protected(admin=False):
        def decorate(fn):
            @functools.wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.user:
                    if request.path.startswith('/api/'):
                        return {'error': 'Inicia sesión para continuar.'}, 401
                    return redirect(url_for('login'))
                if admin and g.user['role'] != 'admin':
                    abort(403)
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    def scope(alias='d'):
        return ('1=1', []) if g.user['role'] == 'admin' else (f'{alias}.owner=?', [g.user['id']])

    def document(doc_id):
        row = db().execute('SELECT * FROM documents WHERE id=?', (doc_id,)).fetchone()
        if not row:
            abort(404)
        if g.user['role'] != 'admin' and row['owner'] != g.user['id']:
            abort(403)
        return row

    def expedients_for_user():
        where, params = scope('e')
        return db().execute(f'SELECT e.* FROM expedients e WHERE {where} ORDER BY id DESC', params).fetchall()

    @app.context_processor
    def context():
        assets_dir = Path(app.static_folder) / 'figma'
        return dict(google_enabled=app.extensions.get('google_oauth_enabled', False), cloud_mode=cloud, bootstrap_required=bool(production or cloud), custom_logo=bool(settings().get('logo_mime')) if cloud else (root / 'institution-logo').is_file(), section_titles={'documents':'Gestión documental','archive':'Archivo central','expedients':'Expedientes','users':'Usuarios y permisos','settings':'Configuración','summary':'Resumen','reports':'Reportes','loans':'Préstamos','account':'Mi cuenta'}, config_values=settings(), types=TYPES, states=STATES,
                    today=datetime.now(ZoneInfo('America/Lima')).strftime('%d/%m/%Y'),
                    asset_exists=lambda name: (assets_dir / name).is_file() and (assets_dir / name).stat().st_size > 0)

    @app.template_filter('filesize')
    def filesize(value):
        return f'{value / (1024 * 1024):.1f} MB' if value >= 1024 * 1024 else f'{value / 1024:.0f} KB'

    @app.cli.command('create-admin')
    @click.argument('username')
    @click.password_option(confirmation_prompt=True)
    def create_admin(username, password):
        if not username.strip() or len(password) < 12:
            raise click.ClickException('Indica un usuario y una contraseña de al menos 12 caracteres.')
        try:
            db().execute('INSERT INTO users(username,password,role) VALUES (?,?,?)',
                         (username.strip().lower(), generate_password_hash(password), 'admin'))
            db().commit()
        except (sqlite3.IntegrityError, psycopg.IntegrityError):
            raise click.ClickException('Ese usuario ya existe.')
        click.echo('Administrador creado.')

    @app.route('/setup', methods=['GET', 'POST'])
    def setup():
        if db().execute('SELECT 1 FROM users LIMIT 1').fetchone():
            abort(404)
        if request.method == 'POST':
            if (production or cloud) and not secrets.compare_digest(app.config['BOOTSTRAP_TOKEN'], request.form.get('setup_token', '')):
                abort(403)
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            if not username or len(username) > 80 or len(password) < 12 or password != request.form.get('confirm'):
                flash('Indica un usuario y dos contraseñas iguales de al menos 12 caracteres.')
            else:
                db().execute('BEGIN IMMEDIATE')
                if db().execute('SELECT 1 FROM users LIMIT 1').fetchone():
                    db().rollback()
                    abort(409)
                db().execute('INSERT INTO users(username,password,role) VALUES (?,?,?)',
                             (username, generate_password_hash(password), 'admin'))
                audit('Configuración inicial: administrador creado')
                db().commit()
                flash('Cuenta creada. Ya puedes iniciar sesión.')
                return redirect(url_for('login'))
        return render_template('setup.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            address = request.remote_addr or 'unknown'
            db().execute('DELETE FROM login_attempts WHERE created < ?', ((datetime.now(ZoneInfo('UTC')) - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S'),))
            failures = db().execute('SELECT count(*) FROM login_attempts WHERE address=?', (address,)).fetchone()[0]
            if failures >= 10:
                db().commit()
                return render_template('login.html', setup_available=False, throttled=True), 429
            user = db().execute('SELECT * FROM users WHERE username=? AND active=1',
                                (request.form.get('username', '').strip().lower(),)).fetchone()
            if user and check_password_hash(user['password'], request.form.get('password', '')):
                session.clear()
                session.update(uid=user['id'], auth_version=user['auth_version'], csrf=secrets.token_hex(32))
                session.permanent = True
                g.user = user
                audit('Inicio de sesión')
                db().execute('DELETE FROM login_attempts WHERE address=?', (address,))
                db().commit()
                return redirect(url_for('index'))
            db().execute('INSERT INTO login_attempts(address) VALUES (?)', (address,))
            db().commit()
            flash('Usuario o contraseña incorrectos.')
        return render_template('login.html', setup_available=not db().execute('SELECT 1 FROM users LIMIT 1').fetchone())

    @app.post('/logout')
    def logout():
        if g.user:
            audit('Cierre de sesión')
            db().commit()
        session.clear()
        return redirect(url_for('login'))

    def filtered_documents(archive=False):
        where, params = scope()
        clauses = [where]
        q = request.args.get('q', '').strip()[:200]
        if q:
            clauses.append('(d.title LIKE ? OR d.code LIKE ? OR e.code LIKE ? OR d.unit LIKE ?)')
            params += [f'%{q}%'] * 4
        for key, column in [('kind', 'd.kind'), ('status', 'd.status')]:
            value = request.args.get(key, '')
            if value:
                clauses.append(f'{column}=?')
                params.append(value)
        year = request.args.get('year', '')
        if year:
            clauses.append("substr(d.created,1,4)=?")
            params.append(year)
        if archive:
            clauses.append("d.status='Archivado'")
        tab = request.args.get('tab', 'all')
        if tab == 'mine':
            clauses.append('d.owner=?')
            params.append(g.user['id'])
        elif tab == 'favorites':
            clauses.append('f.user_id IS NOT NULL')
        expedient_id = request.args.get('expedient', type=int)
        if expedient_id:
            clauses.append('d.expedient_id=?')
            params.append(expedient_id)
        query = '''SELECT d.*,u.username,e.code AS expedient_code,
                   f.user_id IS NOT NULL AS favorite FROM documents d
                   JOIN users u ON u.id=d.owner LEFT JOIN expedients e ON e.id=d.expedient_id
                   LEFT JOIN favorites f ON f.document_id=d.id AND f.user_id=? WHERE '''
        order = 'ASC' if request.args.get('sort') == 'oldest' else 'DESC'
        return db().execute(query + ' AND '.join(clauses) + f' ORDER BY d.id {order}', [g.user['id']] + params).fetchall()

    @app.get('/archive', endpoint='archive')
    @app.get('/')
    @protected()
    def index():
        archive = request.path == '/archive'
        documents = filtered_documents(archive)
        where, params = scope()
        totals = db().execute(f'''SELECT count(*) AS total,
            sum(CASE WHEN status IN ('Pendiente','En revisión') THEN 1 ELSE 0 END) AS pending,
            sum(CASE WHEN status='Archivado' THEN 1 ELSE 0 END) AS archived FROM documents d WHERE {where}''', params).fetchone()
        exp_where, exp_params = scope('e')
        exp_count = db().execute(f'SELECT count(*) FROM expedients e WHERE {exp_where}', exp_params).fetchone()[0]
        years = [r[0] for r in db().execute(f'SELECT DISTINCT substr(created,1,4) FROM documents d WHERE {where} ORDER BY 1 DESC', params)]
        page = max(1, request.args.get('page', 1, type=int))
        pages = max(1, (len(documents) + 5) // 6)
        page = min(page, pages)
        events = recent_events(4)
        return render_template('index.html', documents=documents[(page-1)*6:page*6], total=len(documents),
                               totals=totals, exp_count=exp_count, years=years, page=page, pages=pages,
                               expedients=expedients_for_user(), events=events, archive=archive,
                               section='archive' if archive else 'documents')

    def recent_events(limit=20):
        where = '1=1' if g.user['role'] == 'admin' else 'ev.actor=?'
        params = [] if g.user['role'] == 'admin' else [g.user['id']]
        return db().execute(f'''SELECT ev.*,u.username FROM events ev LEFT JOIN users u ON u.id=ev.actor
                            WHERE {where} ORDER BY ev.id DESC LIMIT ?''', params + [limit]).fetchall()

    def cleanup_objects():
        removed = 0
        for row in db().execute('SELECT storage FROM object_deletions LIMIT 20').fetchall():
            try:
                store().remove(row['storage'])
            except StorageError:
                continue
            db().execute('DELETE FROM object_deletions WHERE storage=?', (row['storage'],))
            db().commit()
            removed += 1
        # Signed uploads can remain valid for two hours; wait beyond that window.
        expired = db().execute("SELECT id,storage FROM pending_uploads WHERE expires<? AND status!='complete' LIMIT 20",
                               (int(time.time()) - 7200,)).fetchall()
        for row in expired:
            try:
                store().remove(row['storage'])
            except StorageError:
                continue
            db().execute('DELETE FROM pending_uploads WHERE id=?', (row['id'],))
            db().commit()
            removed += 1
        db().execute("DELETE FROM pending_uploads WHERE expires<? AND status='complete'", (int(time.time()) - 7200,))
        db().commit()
        return removed

    @app.post('/settings/storage-cleanup')
    @protected(admin=True)
    def storage_cleanup():
        if not cloud:
            abort(404)
        removed = cleanup_objects()
        flash(f'Limpieza completada: {removed} archivos temporales o eliminados procesados.')
        return redirect(url_for('configuration'))

    @app.post('/api/uploads/start')
    @protected()
    def upload_start():
        if not cloud:
            abort(404)
        title = request.form.get('title', '').strip()
        code = request.form.get('code', '').strip()
        kind = request.form.get('kind', 'Otro')
        unit = request.form.get('unit', '').strip()
        folios = request.form.get('folios', '0')
        filename = request.form.get('filename', '').replace('\\', '/').rsplit('/', 1)[-1]
        declared_size = request.form.get('size', type=int)
        exp = request.form.get('expedient_id', type=int)
        if (not title or len(title) > 200 or len(code) > 80 or len(unit) > 200 or kind not in TYPES
                or not folios.isdigit() or not 0 <= int(folios) <= 100000
                or not filename.lower().endswith('.pdf') or len(filename) > 200
                or declared_size is None or not 0 < declared_size <= 10 * 1024 * 1024):
            return {'error': 'Revisa los datos y selecciona un PDF de hasta 10 MB.'}, 400
        if exp and exp not in [row['id'] for row in expedients_for_user()]:
            abort(403)
        count = db().execute("SELECT count(*) FROM pending_uploads WHERE owner=? AND expires>? AND status IN ('pending','processing')",
                             (g.user['id'], int(time.time()))).fetchone()[0]
        if count >= 5:
            return {'error': 'Ya tienes varias cargas en curso. Espera 15 minutos o completa las pendientes.'}, 429
        ticket = secrets.token_hex(24)
        storage = f'pdfs/{g.user["id"]}/{ticket}.pdf'
        metadata = dict(title=title, code=code, kind=kind, unit=unit, folios=int(folios),
                        filename=filename, size=declared_size, expedient_id=exp)
        signed = store().sign_upload(storage)
        db().execute('INSERT INTO pending_uploads(id,owner,storage,metadata,expires) VALUES (?,?,?,?,?)',
                     (ticket, g.user['id'], storage, json.dumps(metadata), int(time.time()) + 900))
        db().commit()
        return {'id': ticket, 'upload_url': signed}

    @app.post('/api/uploads/complete')
    @protected()
    def upload_complete():
        if not cloud:
            abort(404)
        ticket = request.form.get('id', '')
        row = db().execute('SELECT * FROM pending_uploads WHERE id=? AND owner=?', (ticket, g.user['id'])).fetchone()
        if not row:
            abort(404)
        if row['status'] == 'complete':
            return {'redirect': url_for('index')}
        if row['expires'] < int(time.time()):
            return {'error': 'La carga venció. Selecciona el PDF e inténtalo nuevamente.'}, 400
        claimed = db().execute("UPDATE pending_uploads SET status='processing' WHERE id=? AND owner=? AND status='pending' RETURNING id",
                               (ticket, g.user['id'])).fetchone()
        db().commit()
        if not claimed:
            return {'error': 'Esta carga ya se está procesando.'}, 409
        metadata = json.loads(row['metadata'])
        try:
            content = store().read(row['storage'], 10 * 1024 * 1024)
        except StorageError:
            db().execute("UPDATE pending_uploads SET status='pending' WHERE id=?", (ticket,))
            db().commit()
            raise
        if (not content.startswith(b'%PDF-') or b'%%EOF' not in content[-4096:]
                or len(content) != metadata['size']):
            db().execute("UPDATE pending_uploads SET status='failed' WHERE id=?", (ticket,))
            db().execute('INSERT INTO object_deletions(storage) VALUES (?) ON CONFLICT(storage) DO NOTHING', (row['storage'],))
            db().commit()
            cleanup_objects()
            return {'error': 'El archivo recibido no es un PDF válido o su tamaño cambió.'}, 400
        # An administrator could have reassigned an expedient during the upload.
        if metadata['expedient_id'] and metadata['expedient_id'] not in [r['id'] for r in expedients_for_user()]:
            db().execute("UPDATE pending_uploads SET status='failed' WHERE id=?", (ticket,))
            db().commit()
            abort(403)
        try:
            created = db().execute('''INSERT INTO documents(title,filename,storage,owner,code,kind,unit,folios,size,expedient_id)
                              VALUES(?,?,?,?,?,?,?,?,?,?) RETURNING id''',
                              (metadata['title'], metadata['filename'], row['storage'], g.user['id'], metadata['code'],
                               metadata['kind'], metadata['unit'], metadata['folios'], len(content), metadata['expedient_id'])).fetchone()
            db().execute("UPDATE pending_uploads SET status='complete',document_id=? WHERE id=?", (created['id'], ticket))
            audit(f'Registró documento: {metadata["code"] or metadata["title"]}')
            db().commit()
        except Exception:
            db().rollback()
            db().execute("UPDATE pending_uploads SET status='pending' WHERE id=?", (ticket,))
            db().commit()
            raise
        flash('Documento cargado correctamente.')
        return {'redirect': url_for('index')}

    @app.get('/healthz')
    def healthz():
        try:
            db().execute('SELECT id FROM users LIMIT 1').fetchone()
        except Exception:
            return {'status': 'unavailable'}, 503
        return {'status': 'ok'}

    @app.route('/upload', methods=['GET', 'POST'])
    @protected()
    def upload():
        if request.method == 'GET':
            return render_template('document_form.html', section='documents', expedients=expedients_for_user(), doc=None)
        if cloud:
            abort(400, 'Usa la carga directa al almacenamiento privado.')
        file = request.files.get('pdf')
        title = request.form.get('title', '').strip()
        code = request.form.get('code', '').strip()
        kind = request.form.get('kind', 'Otro')
        unit = request.form.get('unit', '').strip()
        folios = request.form.get('folios', '0')
        exp = request.form.get('expedient_id', type=int)
        if (not title or len(title) > 200 or not file or not file.filename or len(code) > 80
                or len(unit) > 200 or kind not in TYPES or not folios.isdigit() or not 0 <= int(folios) <= 100000):
            flash('Indica un título de hasta 200 caracteres, metadatos válidos y selecciona un PDF.')
            return redirect(url_for('upload'))
        if exp and exp not in [r['id'] for r in expedients_for_user()]:
            abort(403)
        content = file.read(10 * 1024 * 1024 + 1)
        if (not file.filename.lower().endswith('.pdf') or not content.startswith(b'%PDF-')
                or b'%%EOF' not in content[-4096:] or len(content) > 10 * 1024 * 1024):
            flash('Selecciona un archivo PDF con cabecera y cierre válidos, de hasta 10 MB.')
            return redirect(url_for('upload'))
        storage = secrets.token_hex(24) + '.pdf'
        path = uploads / storage
        path.write_bytes(content)
        try:
            db().execute('''INSERT INTO documents(title,filename,storage,owner,code,kind,unit,folios,size,expedient_id)
                         VALUES(?,?,?,?,?,?,?,?,?,?)''',
                         (title, Path(file.filename).name, storage, g.user['id'], code, kind, unit, int(folios), len(content), exp))
            audit(f'Registró documento: {code or title}')
            db().commit()
        except Exception:
            path.unlink(missing_ok=True)
            raise
        flash('Documento cargado correctamente.')
        return redirect(url_for('index'))

    @app.get('/documents/<int:doc_id>/download')
    @protected()
    def download(doc_id):
        row = document(doc_id)
        audit(f'Descargó documento: {row["code"] or row["title"]}')
        db().commit()
        if cloud:
            return redirect(store().sign_download(row['storage'], row['filename']), code=303)
        if not (uploads / row['storage']).is_file():
            abort(404)
        return send_file(uploads / row['storage'], as_attachment=True, download_name=row['filename'], mimetype='application/pdf')

    @app.route('/documents/<int:doc_id>/edit', methods=['GET', 'POST'])
    @protected(admin=True)
    def edit_document(doc_id):
        row = document(doc_id)
        if request.method == 'POST':
            status = request.form.get('status')
            title = request.form.get('title', '').strip()
            kind = request.form.get('kind')
            code = request.form.get('code', '').strip()
            unit = request.form.get('unit', '').strip()
            folios = request.form.get('folios', '0')
            exp = request.form.get('expedient_id', type=int)
            if (status not in STATES or not title or len(title) > 200 or len(code) > 80
                    or len(unit) > 200 or kind not in TYPES or not folios.isdigit() or not 0 <= int(folios) <= 100000):
                abort(400)
            if exp and exp not in [r['id'] for r in expedients_for_user()]:
                abort(400)
            db().execute('''UPDATE documents SET title=?,code=?,kind=?,unit=?,folios=?,status=?,expedient_id=? WHERE id=?''',
                         (title, code, kind, unit, int(folios), status, exp, doc_id))
            audit(f'Actualizó documento: {code or title} · {status}')
            db().commit()
            flash('Documento actualizado.')
            return redirect(url_for('index'))
        return render_template('document_form.html', section='documents', doc=row, expedients=expedients_for_user())

    @app.post('/documents/<int:doc_id>/favorite')
    @protected()
    def favorite(doc_id):
        document(doc_id)
        existing = db().execute('SELECT 1 FROM favorites WHERE user_id=? AND document_id=?', (g.user['id'], doc_id)).fetchone()
        if existing:
            db().execute('DELETE FROM favorites WHERE user_id=? AND document_id=?', (g.user['id'], doc_id))
        else:
            db().execute('INSERT INTO favorites VALUES (?,?)', (g.user['id'], doc_id))
        db().commit()
        return redirect(url_for('index', tab=request.form.get('tab', 'all')))

    @app.post('/documents/<int:doc_id>/delete')
    @protected(admin=True)
    def delete(doc_id):
        row = document(doc_id)
        if db().execute('SELECT 1 FROM loans WHERE document_id=?', (doc_id,)).fetchone():
            flash('El documento tiene historial de préstamos. Consérvalo en el archivo central.')
            return redirect(url_for('index'))
        db().execute('DELETE FROM documents WHERE id=?', (doc_id,))
        if cloud:
            db().execute('INSERT INTO object_deletions(storage) VALUES (?) ON CONFLICT(storage) DO NOTHING', (row['storage'],))
        audit(f'Eliminó documento: {row["code"] or row["title"]}')
        db().commit()
        if cloud:
            cleanup_objects()
        else:
            (uploads / row['storage']).unlink(missing_ok=True)
        flash('Documento eliminado.')
        return redirect(url_for('index'))

    @app.route('/expedients', methods=['GET', 'POST'])
    @protected()
    def expedients():
        if request.method == 'POST':
            if g.user['role'] != 'admin':
                abort(403)
            code = request.form.get('code', '').strip()
            title = request.form.get('title', '').strip()
            owner = request.form.get('owner', g.user['id'], type=int)
            if not db().execute('SELECT 1 FROM users WHERE id=? AND active=1', (owner,)).fetchone():
                abort(400)
            if not code or len(code) > 80 or not title or len(title) > 200:
                flash('Indica un código y un asunto válidos.')
            else:
                try:
                    db().execute('INSERT INTO expedients(code,title,owner) VALUES(?,?,?)', (code, title, owner))
                    audit(f'Creó expediente: {code}')
                    db().commit()
                    flash('Expediente creado.')
                except (sqlite3.IntegrityError, psycopg.IntegrityError):
                    flash('El código del expediente ya existe.')
            return redirect(url_for('expedients'))
        where, params = scope('e')
        join_scope = '' if g.user['role'] == 'admin' else ' AND d.owner=e.owner'
        rows = db().execute(f'''SELECT e.*,count(d.id) AS count FROM expedients e
                   LEFT JOIN documents d ON d.expedient_id=e.id {join_scope} WHERE {where} GROUP BY e.id ORDER BY e.id DESC''', params).fetchall()
        owners = db().execute('SELECT id,username FROM users WHERE active=1 ORDER BY username').fetchall() if g.user['role'] == 'admin' else []
        return render_template('expedients.html', section='expedients', expedients=rows, owners=owners)

    @app.route('/loans', methods=['GET', 'POST'])
    @protected(admin=True)
    def loans():
        if request.method == 'POST':
            doc_id = request.form.get('document_id', type=int)
            document(doc_id)
            borrower = request.form.get('borrower', '').strip()
            due = request.form.get('due', '')
            try:
                if not borrower or len(borrower) > 120 or datetime.strptime(due, '%Y-%m-%d').date() < datetime.now(ZoneInfo('America/Lima')).date():
                    raise ValueError()
                db().execute('INSERT INTO loans(document_id,borrower,due) VALUES(?,?,?)', (doc_id, borrower, due))
                audit(f'Registró préstamo de documento #{doc_id} a {borrower}')
                db().commit()
                flash('Préstamo registrado.')
            except ValueError:
                flash('Revisa el destinatario y la fecha de devolución (hoy o posterior).')
            except (sqlite3.IntegrityError, psycopg.IntegrityError):
                flash('Este documento ya tiene un préstamo activo.')
            return redirect(url_for('loans'))
        rows = db().execute('SELECT l.*,d.title,d.code FROM loans l JOIN documents d ON d.id=l.document_id ORDER BY l.id DESC').fetchall()
        docs = db().execute('SELECT id,title FROM documents ORDER BY id DESC').fetchall()
        return render_template('loans.html', section='loans', loans=rows, documents=docs)

    @app.post('/loans/<int:loan_id>/return')
    @protected(admin=True)
    def return_loan(loan_id):
        row = db().execute('SELECT * FROM loans WHERE id=?', (loan_id,)).fetchone()
        if not row:
            abort(404)
        if not row['returned']:
            db().execute('UPDATE loans SET returned=CURRENT_TIMESTAMP WHERE id=?', (loan_id,))
            audit(f'Registró devolución de préstamo #{loan_id}')
            db().commit()
        return redirect(url_for('loans'))

    @app.get('/export')
    @protected()
    def export():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Código', 'Asunto', 'Tipo', 'Estado', 'Responsable', 'Fecha UTC', 'Expediente'])
        for row in filtered_documents():
            cells = [row[k] or '' for k in ('code', 'title', 'kind', 'status', 'username', 'created', 'expedient_code')]
            writer.writerow(["'" + str(c) if str(c).lstrip().startswith(('=', '+', '-', '@')) else c for c in cells])
        audit('Exportó listado documental')
        db().commit()
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), as_attachment=True,
                         download_name='sidoc-documentos.csv', mimetype='text/csv')

    @app.get('/summary', endpoint='summary')
    @app.get('/activity', endpoint='activity')
    @app.get('/reports')
    @protected()
    def reports():
        where, params = scope()
        counts = db().execute(f'SELECT status,count(*) AS count FROM documents d WHERE {where} GROUP BY status', params).fetchall()
        return render_template('reports.html', section='summary' if request.path == '/summary' else 'reports',
                               counts=counts, events=recent_events(50))

    @app.route('/users', methods=['GET', 'POST'])
    @protected(admin=True)
    def users():
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            role = request.form.get('role')
            try:
                google_email = normalized_google_email(request.form.get('google_email'))
            except ValueError:
                flash('Indica un correo válido para Google o deja ese campo vacío.')
                return redirect(url_for('users'))
            if not username or len(username) > 80 or len(password) < 12 or role not in ('admin', 'personal'):
                flash('Revisa los datos. La contraseña debe tener al menos 12 caracteres.')
            else:
                try:
                    db().execute('INSERT INTO users(username,password,role,google_email) VALUES(?,?,?,?)',
                                 (username, generate_password_hash(password), role, google_email))
                    audit(f'Creó usuario: {username} · {role}')
                    db().commit()
                    flash('Usuario creado.')
                except (sqlite3.IntegrityError, psycopg.IntegrityError):
                    flash('Ese usuario o correo de Google ya está asignado.')
            return redirect(url_for('users'))
        return render_template('users.html', section='users', users=db().execute('SELECT id,username,role,active,google_email,google_sub FROM users').fetchall())

    @app.post('/users/<int:user_id>/update')
    @protected(admin=True)
    def update_user(user_id):
        user = db().execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not user:
            abort(404)
        role = request.form.get('role')
        active = 1 if request.form.get('active') else 0
        password = request.form.get('password', '')
        if role not in ('admin', 'personal') or (password and len(password) < 12):
            abort(400)
        if user_id == g.user['id'] and (not active or role != 'admin'):
            flash('No puedes desactivar tu propia cuenta ni quitarte el rol administrador.')
            return redirect(url_for('users'))
        try:
            google_email = normalized_google_email(request.form.get('google_email', user['google_email'] or ''))
            db().execute('UPDATE users SET role=?,active=?,google_email=?,google_sub=? WHERE id=?',
                         (role, active, google_email, user['google_sub'] if google_email == user['google_email'] else None, user_id))
        except (ValueError, sqlite3.IntegrityError, psycopg.IntegrityError):
            db().rollback()
            flash('El correo de Google no es válido o ya está autorizado en otra cuenta.')
            return redirect(url_for('users'))
        if password:
            db().execute('UPDATE users SET password=? WHERE id=?', (generate_password_hash(password), user_id))
        db().execute('UPDATE users SET auth_version=auth_version+1 WHERE id=?', (user_id,))
        if user_id == g.user['id']:
            session['auth_version'] = user['auth_version'] + 1
        audit(f'Actualizó permisos o acceso: {user["username"]}')
        db().commit()
        flash('Cuenta actualizada.')
        return redirect(url_for('users'))

    @app.route('/account', methods=['GET', 'POST'])
    @protected()
    def account():
        if request.method == 'POST':
            password = request.form.get('password', '')
            if not check_password_hash(g.user['password'], request.form.get('current', '')) or len(password) < 12:
                flash('Revisa la contraseña actual. La nueva debe tener al menos 12 caracteres.')
            else:
                db().execute('UPDATE users SET password=?,auth_version=auth_version+1 WHERE id=?', (generate_password_hash(password), g.user['id']))
                session['auth_version'] = g.user['auth_version'] + 1
                audit('Cambió su contraseña')
                db().commit()
                session['csrf'] = secrets.token_hex(32)
                flash('Contraseña actualizada.')
            return redirect(url_for('account'))
        return render_template('account.html', section='account')

    @app.get('/branding/logo')
    def institutional_logo():
        if cloud:
            mime = settings().get('logo_mime')
            if mime not in ('image/png', 'image/jpeg'):
                abort(404)
            return send_file(io.BytesIO(store().read('branding/institution-logo', 2 * 1024 * 1024)), mimetype=mime)
        path = root / 'institution-logo'
        if not path.is_file():
            abort(404)
        signature = path.read_bytes()[:8]
        mime = 'image/png' if signature == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'
        return send_file(path, mimetype=mime)

    @app.post('/settings/logo')
    @protected(admin=True)
    def upload_logo():
        file = request.files.get('logo')
        if not file or not file.filename:
            flash('Selecciona el archivo original del escudo en PNG o JPG.')
            return redirect(url_for('configuration'))
        content = file.read(2 * 1024 * 1024 + 1)
        png = content.startswith(b'\x89PNG\r\n\x1a\n') and content.endswith(b'IEND\xaeB`\x82')
        jpeg = content.startswith(b'\xff\xd8\xff') and content.endswith(b'\xff\xd9')
        if len(content) > 2 * 1024 * 1024 or not (png or jpeg):
            flash('Selecciona una imagen PNG o JPG de hasta 2 MB.')
            return redirect(url_for('configuration'))
        # Preserve the supplied image bytes; no redraw, cropping or recompression.
        if cloud:
            mime = 'image/png' if png else 'image/jpeg'
            store().put('branding/institution-logo', content, mime)
            db().execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', ('logo_mime', mime))
            audit('Actualizó el escudo institucional')
            db().commit()
            flash('Escudo institucional guardado.')
            return redirect(url_for('configuration'))
        temporary = root / ('logo-' + secrets.token_hex(12) + '.tmp')
        temporary.write_bytes(content)
        temporary.replace(root / 'institution-logo')
        audit('Actualizó el escudo institucional')
        db().commit()
        flash('Escudo institucional guardado.')
        return redirect(url_for('configuration'))

    @app.route('/settings', methods=['GET', 'POST'])
    @protected(admin=True)
    def configuration():
        if request.method == 'POST':
            institution = request.form.get('institution', '').strip()
            contact = request.form.get('contact', '').strip()
            if not institution or len(institution) > 120 or len(contact) > 120 or (contact and ('@' not in contact or '\n' in contact or '\r' in contact)):
                abort(400)
            for key, value in [('institution', institution), ('contact', contact)]:
                db().execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
            audit('Actualizó configuración institucional')
            db().commit()
            flash('Configuración guardada.')
            return redirect(url_for('configuration'))
        return render_template('settings.html', section='settings')

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error_page(error):
        messages = {400: 'Datos inválidos o formulario vencido. Recarga la página e inténtalo de nuevo.',
                    403: 'No tienes permisos para realizar esta acción.', 404: 'No encontramos esta página o documento.',
                    413: 'El archivo supera el tamaño permitido (10 MB).'}
        if request.path.startswith('/api/'):
            return {'error': messages[error.code]}, error.code
        return render_template('error.html', message=messages[error.code]), error.code

    @app.errorhandler(StorageError)
    def storage_error(error):
        if request.path.startswith('/api/'):
            return {'error': 'No se pudo completar la operación de almacenamiento. Inténtalo nuevamente.'}, 502
        return render_template('error.html', message='El almacenamiento no está disponible. Inténtalo nuevamente.'), 502

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            + ("connect-src 'self' " + app.config['SUPABASE_URL'] + "; " if cloud else '')
            + "img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if production and request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    configure_google_login(app, db, audit)
    return app
