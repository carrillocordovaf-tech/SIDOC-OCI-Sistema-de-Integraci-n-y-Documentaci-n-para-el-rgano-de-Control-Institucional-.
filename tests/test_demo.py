import importlib
import os
import unittest
from unittest.mock import patch

from demo_app import create_demo_app


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.app = create_demo_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_can_start_on_vercel_without_database_or_secrets(self):
        with patch.dict(os.environ, {'VERCEL': '1', 'SIDOC_DEMO': '1', 'SECRET_KEY': '',
                                     'DATABASE_URL': '', 'SUPABASE_URL': ''}), \
             patch('sqlite3.connect', side_effect=AssertionError('Demo opened SQLite')), \
             patch('psycopg.connect', side_effect=AssertionError('Demo opened PostgreSQL')):
            import wsgi
            entrypoint = importlib.reload(wsgi)
            self.assertEqual(entrypoint.app.test_client().get('/healthz').get_json()['mode'], 'demo')

    def test_all_modules_and_sample_pdf_are_accessible(self):
        for path in ('/', '/login', '/upload', '/expedients', '/archive', '/loans', '/reports', '/summary',
                     '/activity', '/users', '/settings', '/account', '/documents/1/edit'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(b'DEMOSTRACI', response.data, path)
        with self.client.get('/documents/1/download') as response:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data.startswith(b'%PDF-'))
            self.assertIn(b'demostracion', response.data)

    def test_search_filters_and_favorites(self):
        self.assertIn(b'Informe de control posterior', self.client.get('/?q=INF-024').data)
        self.assertNotIn(b'Solicitud de informaci', self.client.get('/?q=INF-024').data)
        self.assertNotIn(b'Informe de control posterior', self.client.get('/archive').data)
        self.assertIn(b'Informe de control posterior', self.client.get('/?tab=favorites').data)
        self.assertNotIn(b'Visita de control', self.client.get('/?tab=favorites').data)

    def test_personal_profile_hides_administration_and_other_documents(self):
        self.client.get('/demo/role/personal')
        for path in ('/users', '/settings', '/loans', '/documents/1/download', '/documents/1/edit'):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        page = self.client.get('/').data
        self.assertIn(b'Solicitud de informaci', page)
        self.assertNotIn(b'Informe de control posterior', page)
        self.assertNotIn(b'Usuarios y permisos', page)
        self.client.get('/demo/role/admin')
        self.assertEqual(self.client.get('/users').status_code, 200)

    def test_mutations_are_rejected_and_examples_never_change(self):
        before = self.client.get('/').data
        for path in ('/upload', '/users', '/settings', '/account', '/documents/1/delete',
                     '/documents/1/favorite', '/users/1/update', '/loans/1/return', '/api/uploads/start'):
            self.assertEqual(self.client.post(path, data={'title': 'Private content'}).status_code, 405, path)
        self.assertEqual(self.client.get('/').data, before)
        self.assertEqual(self.client.post('/logout').status_code, 302)

    def test_demo_has_no_account_creation_or_credential_form(self):
        page = self.client.get('/login').data
        self.assertIn(b'Entrar como administrador', page)
        self.assertIn(b'Entrar como personal', page)
        self.assertNotIn(b'id="login-form"', page)
        self.assertNotIn(b'name="password"', page)
        self.assertEqual(self.client.get('/setup').status_code, 302)


if __name__ == '__main__':
    unittest.main()
