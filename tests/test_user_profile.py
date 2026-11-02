import tempfile
import unittest
from app import create_app

class UserProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=create_app(dict(TESTING=True,DATA_DIR=self.tmp.name))
        self.app.test_cli_runner().invoke(args=['create-admin','admin@example.test','--password','test-password-123'])
        self.client=self.app.test_client()
        self.client.get('/login')
        self.post('/login',dict(username='admin@example.test',password='test-password-123'))
    def tearDown(self):
        self.tmp.cleanup()
    def post(self,path,data):
        with self.client.session_transaction() as s:token=s['csrf']
        return self.client.post(path,data=dict(data,csrf=token),follow_redirects=True)
    def test_name_persists_and_panel_has_correct_entity(self):
        response=self.post('/account',dict(action='profile',display_name='Nombre completo de prueba'))
        self.assertIn(b'Nombre completo de prueba',response.data)
        page=self.client.get('/').get_data(as_text=True)
        self.assertIn('Datos del usuario',page)
        self.assertIn('<dt>Entidad</dt><dd>Órgano de Control Institucional</dd>',page)
        self.assertIn('Nombre completo de prueba',page)
        self.assertNotIn('<div class="profile">',page)
        self.assertIn('class="header-logout"',page)
        self.assertEqual(self.post('/account',dict(action='profile',display_name='x'*161)).status_code,400)
        self.assertIn(b'Nombre completo de prueba',self.client.get('/account').data)
    def test_personal_only_edits_own_name_and_cannot_change_role(self):
        self.post('/users',dict(username='personal',password='test-password-123',role='personal',display_name='Persona de prueba'))
        self.post('/logout',{})
        self.post('/login',dict(username='personal',password='test-password-123'))
        self.post('/account',dict(action='profile',display_name='Otro nombre propio',role='admin',user_id='1'))
        self.assertIn(b'Otro nombre propio',self.client.get('/account').data)
        self.assertEqual(self.client.get('/users').status_code,403)
        self.assertEqual(self.client.post('/account',data=dict(action='profile',display_name='Sin CSRF')).status_code,400)
        self.post('/logout',{})
        self.post('/login',dict(username='admin@example.test',password='test-password-123'))
        self.assertNotIn(b'Otro nombre propio',self.client.get('/account').data)

    def test_existing_schema_without_name_still_renders(self):
        import sqlite3
        from pathlib import Path
        with sqlite3.connect(Path(self.tmp.name)/'sidoc.sqlite') as db:
            db.execute('ALTER TABLE users DROP COLUMN display_name')
        self.assertEqual(self.client.get('/').status_code,200)
        page=self.client.get('/account')
        self.assertIn(b'0005_user_display_name.sql',page.data)
        self.assertNotIn(b'id="display-name"',page.data)
        self.assertEqual(self.client.get('/users').status_code,200)
