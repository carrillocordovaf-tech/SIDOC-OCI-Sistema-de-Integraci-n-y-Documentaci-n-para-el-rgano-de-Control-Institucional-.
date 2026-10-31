import io
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from app import create_app


PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
PASSWORD = 'test-password-123'


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.tmp.name})
        self.client = self.app.test_client()
        result = self.app.test_cli_runner().invoke(args=['create-admin', 'admin', '--password', PASSWORD])
        self.assertEqual(result.exit_code, 0)
        self.login('admin')

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data=None):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf']
        return self.client.post(path, data=dict(data or {}, csrf=csrf), follow_redirects=True)

    def login(self, username):
        self.post('/login', {'username': username, 'password': PASSWORD})

    def upload(self, title='Informe de prueba', code='INF-001', **kwargs):
        return self.post('/upload', dict(title=title, code=code, pdf=(io.BytesIO(PDF), 'archivo.pdf'), **kwargs))

    def test_document_lifecycle_favorites_filters_export_and_loans(self):
        self.post('/expedients', {'code': 'EXP-001', 'title': 'Control de obras'})
        self.upload(kind='Informe', expedient_id='1', folios='10')
        self.assertIn(b'Informe de prueba', self.client.get('/?q=EXP-001').data)
        self.assertNotIn(b'Informe de prueba', self.client.get('/?q=NOEXISTE').data)
        self.post('/documents/1/favorite')
        self.assertIn(b'Informe de prueba', self.client.get('/?tab=favorites').data)
        self.post('/documents/1/favorite')
        self.assertNotIn(b'Informe de prueba', self.client.get('/?tab=favorites').data)
        self.post('/documents/1/edit', {'title': 'Informe archivado', 'code': 'INF-001', 'kind': 'Informe', 'status': 'Archivado', 'expedient_id': '1'})
        self.assertIn(b'Informe archivado', self.client.get('/archive').data)
        with self.client.get('/export?status=Archivado') as response:
            self.assertIn(b'Informe archivado', response.data)
        due = (date.today() + timedelta(days=30)).isoformat()
        self.post('/loans', {'document_id': '1', 'borrower': 'Oficina OCI', 'due': due})
        duplicate = self.post('/loans', {'document_id': '1', 'borrower': 'Otra oficina', 'due': due})
        self.assertIn(b'ya tiene un', duplicate.data)
        refused = self.post('/documents/1/delete')
        self.assertIn(b'historial de', refused.data)
        self.post('/loans/1/return')
        self.assertIn(b'Devuelto', self.client.get('/loans').data)
        self.assertIn(b'Actualiz', self.client.get('/activity').data)

    def test_personal_cannot_administer_or_cross_document_boundaries(self):
        self.upload()
        self.post('/users', {'username': 'ana', 'password': PASSWORD, 'role': 'personal'})
        self.post('/logout')
        self.login('ana')
        for path in ('/users', '/settings', '/loans', '/documents/1/edit'):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        for path, data in [('/documents/1/favorite', {}), ('/documents/1/delete', {}),
                           ('/expedients', {'code': 'X', 'title': 'Privado'}),
                           ('/users/1/update', {'role': 'personal'}),
                           ('/loans/1/return', {})]:
            self.assertEqual(self.post(path, data).status_code, 403, path)
        self.assertEqual(self.upload(expedient_id='999').status_code, 403)
        with self.client.get('/export') as response:
            self.assertNotIn(b'Informe de prueba', response.data)
        self.assertNotIn(b'Informe de prueba', self.client.get('/reports').data)

    def test_assigned_expedients_keep_personal_document_counts_private(self):
        self.post('/users', {'username': 'ana', 'password': PASSWORD, 'role': 'personal'})
        self.post('/expedients', {'code': 'EXP-ANA', 'title': 'Expediente asignado', 'owner': '2'})
        self.upload(title='Documento privado admin', expedient_id='1')
        self.post('/logout')
        self.login('ana')
        self.assertIn(b'EXP-ANA', self.client.get('/expedients').data)
        self.assertIn(b'0 documentos', self.client.get('/expedients').data)
        self.assertNotIn(b'Documento privado admin', self.client.get('/?expedient=1').data)
        self.upload(title='Documento de Ana', expedient_id='1')
        self.assertIn(b'1 documentos', self.client.get('/expedients').data)

    def test_user_deactivation_password_change_and_self_protection(self):
        self.post('/users', {'username': 'ana', 'password': PASSWORD, 'role': 'personal'})
        personal = self.app.test_client()
        personal.get('/login')
        with personal.session_transaction() as session:
            csrf = session['csrf']
        personal.post('/login', data={'csrf': csrf, 'username': 'ana', 'password': PASSWORD})
        self.assertEqual(personal.get('/account').status_code, 200)
        self.post('/users/2/update', {'role': 'personal'})
        self.assertEqual(personal.get('/account').status_code, 302)
        response = self.post('/users/1/update', {'role': 'personal'})
        self.assertIn(b'No puedes desactivar', response.data)
        self.post('/account', {'current': PASSWORD, 'password': 'new-password-123456'})
        self.post('/logout')
        self.assertIn(b'incorrectos', self.post('/login', {'username': 'admin', 'password': PASSWORD}).data)
        response = self.post('/login', {'username': 'admin', 'password': 'new-password-123456'})
        self.assertIn(b'Gesti', response.data)

    def test_logo_preserves_supplied_image_and_requires_admin(self):
        import base64
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jCTsAAAAASUVORK5CYII=')
        self.assertEqual(self.client.get('/branding/logo').status_code, 404)
        self.post('/settings/logo', {'logo': (io.BytesIO(png), 'escudo.png')})
        with self.client.get('/branding/logo') as response:
            self.assertEqual(response.data, png)
            self.assertEqual(response.mimetype, 'image/png')
        self.assertIn(b'/branding/logo', self.client.get('/login').data)
        self.post('/users', {'username': 'ana', 'password': PASSWORD, 'role': 'personal'})
        self.post('/logout')
        self.login('ana')
        response = self.post('/settings/logo', {'logo': (io.BytesIO(png), 'otro.png')})
        self.assertEqual(response.status_code, 403)

    def test_setup_only_before_first_user(self):
        self.assertEqual(self.client.get('/setup').status_code, 404)
        with tempfile.TemporaryDirectory() as empty:
            app = create_app({'TESTING': True, 'DATA_DIR': empty})
            client = app.test_client()
            self.assertIn(b'crear cuenta', client.get('/login').data)
            client.get('/setup')
            with client.session_transaction() as session:
                csrf = session['csrf']
            response = client.post('/setup', data={'csrf': csrf, 'username': 'first', 'password': PASSWORD, 'confirm': PASSWORD})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(client.get('/setup').status_code, 404)

    def test_pagination_csv_injection_and_oversize(self):
        for i in range(7):
            self.upload(title=f'Caso exclusivo {i}', code=f'COD-{i}')
        self.assertNotIn(b'Caso exclusivo 0', self.client.get('/').data)
        self.assertIn(b'Caso exclusivo 0', self.client.get('/?page=2').data)
        self.upload(title='=1+1')
        with self.client.get('/export') as response:
            self.assertIn(b"'=1+1", response.data)
        response = self.client.post('/upload', data=b'x' * (11 * 1024 * 1024 + 1), content_type='application/octet-stream')
        self.assertEqual(response.status_code, 413)

    def test_login_rate_limit(self):
        self.post('/logout')
        for _ in range(10):
            self.post('/login', {'username': 'admin', 'password': 'wrong'})
        self.assertEqual(self.post('/login', {'username': 'admin', 'password': PASSWORD}).status_code, 429)

    def test_additive_migration_preserves_legacy_documents(self):
        with tempfile.TemporaryDirectory() as legacy:
            connection = sqlite3.connect(Path(legacy) / 'sidoc.sqlite')
            connection.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL);
            CREATE TABLE documents(id INTEGER PRIMARY KEY,title TEXT NOT NULL,filename TEXT NOT NULL,storage TEXT UNIQUE NOT NULL,owner INTEGER NOT NULL REFERENCES users(id),created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO users VALUES(1,'legacy','hash','admin');
            INSERT INTO documents(id,title,filename,storage,owner) VALUES(1,'Histórico','a.pdf','a.pdf',1);''')
            connection.close()
            create_app({'TESTING': True, 'DATA_DIR': legacy})
            connection = sqlite3.connect(Path(legacy) / 'sidoc.sqlite')
            self.assertEqual(connection.execute('SELECT title,status FROM documents').fetchone(), ('Histórico', 'Pendiente'))
            connection.close()


if __name__ == '__main__':
    unittest.main()
