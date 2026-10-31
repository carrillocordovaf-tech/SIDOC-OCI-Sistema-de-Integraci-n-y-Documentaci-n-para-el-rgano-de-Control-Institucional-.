import io
import tempfile
import unittest
from app import create_app


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.tmp.name})
        result = self.app.test_cli_runner().invoke(args=['create-admin', 'admin', '--password', 'test-password-123'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data=None):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            csrf = session['csrf']
        return self.client.post(path, data=dict(data or {}, csrf=csrf), follow_redirects=True)

    def login(self, username='admin'):
        return self.post('/login', {'username': username, 'password': 'test-password-123'})

    def test_login_and_csrf(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.post('/login', data={}).status_code, 400)
        self.assertIn(b'incorrectos', self.post('/login', {'username': 'admin', 'password': 'wrong'}).data)
        self.assertIn(b'Cargar documento', self.login().data)
        self.post('/logout')
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_roles_upload_and_access(self):
        self.login()
        for username in ('ana', 'luis'):
            self.post('/users', {'username': username, 'password': 'test-password-123', 'role': 'personal'})
        self.post('/logout')
        self.login('ana')
        self.assertEqual(self.client.get('/users').status_code, 403)
        self.assertEqual(self.post('/users', {'username': 'intruso', 'role': 'admin', 'password': 'test-password-123'}).status_code, 403)
        invalid = self.post('/upload', {'title': 'Inválido', 'pdf': (io.BytesIO(b'not a pdf'), 'bad.pdf')})
        self.assertIn(b'cabecera', invalid.data)
        pdf = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n'
        self.post('/upload', {'title': 'Informe reservado de Ana', 'pdf': (io.BytesIO(pdf), 'informe.pdf')})
        with self.client.get('/documents/1/download') as response:
            self.assertEqual(response.data, pdf)
        self.assertEqual(self.post('/documents/1/delete').status_code, 403)
        self.post('/logout')
        self.login('luis')
        self.assertNotIn(b'Informe reservado de Ana', self.client.get('/').data)
        self.assertEqual(self.client.get('/documents/1/download').status_code, 403)
        self.post('/logout')
        self.login()
        self.assertIn(b'Informe reservado de Ana', self.client.get('/').data)
        with self.client.get('/documents/1/download') as response:
            self.assertEqual(response.data, pdf)
        self.post('/documents/1/delete')
        self.assertEqual(self.client.get('/documents/1/download').status_code, 404)

    def test_persistence(self):
        second_app = create_app({'TESTING': True, 'DATA_DIR': self.tmp.name})
        client = second_app.test_client()
        client.get('/login')
        with client.session_transaction() as session:
            token = session['csrf']
        response = client.post('/login', data={'csrf': token, 'username': 'admin', 'password': 'test-password-123'})
        self.assertEqual(response.status_code, 302)


if __name__ == '__main__':
    unittest.main()
