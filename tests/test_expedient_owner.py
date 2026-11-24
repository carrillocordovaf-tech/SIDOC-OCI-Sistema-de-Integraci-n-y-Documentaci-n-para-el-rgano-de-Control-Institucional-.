import io
import sqlite3
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from app import create_app


class FormFields(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.options = {}
        self.inputs = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'option' and 'data-owner-name' in attrs:
            self.options[attrs['value']] = attrs
        if tag == 'input' and attrs.get('id') == 'expedient-owner':
            self.inputs[attrs['id']] = attrs


class ExpedientOwnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(dict(TESTING=True, DATA_DIR=self.tmp.name))
        result = self.app.test_cli_runner().invoke(
            args=['create-admin', 'admin', '--password', 'test-password-123'])
        self.assertEqual(result.exit_code, 0)
        self.client = self.app.test_client()
        self.client.get('/login')
        self.post('/login', dict(username='admin', password='test-password-123'))
        self.post('/users', dict(username='ana', password='test-password-123',
                                role='personal', display_name='Ana Torres'))
        self.post('/users', dict(username='luis', password='test-password-123',
                                role='personal', display_name='Luis Vargas'))
        self.post('/expedients', dict(code='EXP-ANA', title='Caso de Ana', owner='2'))
        self.post('/expedients', dict(code='EXP-LUIS', title='Caso de Luis', owner='3'))

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, path, data):
        with self.client.session_transaction() as session:
            token = session['csrf']
        return self.client.post(path, data=dict(data, csrf=token), follow_redirects=True)

    def fields(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return FormFields(response.get_data(as_text=True))

    def test_upload_and_expedient_cards_show_assigned_names(self):
        fields = self.fields('/upload')
        self.assertEqual(fields.options['1']['data-owner-name'], 'Ana Torres')
        self.assertEqual(fields.options['2']['data-owner-name'], 'Luis Vargas')
        self.assertIn('readonly', fields.inputs['expedient-owner'])
        self.assertNotIn('name', fields.inputs['expedient-owner'])
        self.assertEqual(fields.inputs['expedient-owner']['value'], '')
        html = self.client.get('/expedients').get_data(as_text=True)
        self.assertIn('<strong>Responsable:</strong> Ana Torres', html)
        self.assertIn('<strong>Responsable:</strong> Luis Vargas', html)

    def test_edit_shows_expedient_owner_even_when_uploader_is_admin(self):
        self.post('/upload', dict(title='Informe', kind='Informe', expedient_id='1',
                  pdf=(io.BytesIO(b'%PDF-1.4\n%%EOF\n'), 'informe.pdf')))
        fields = self.fields('/documents/1/edit')
        self.assertEqual(fields.inputs['expedient-owner']['value'], 'Ana Torres')
        self.assertIn('selected', fields.options['1'])

    def test_personal_sees_only_their_expedients_and_owners(self):
        self.post('/logout', {})
        self.post('/login', dict(username='ana', password='test-password-123'))
        fields = self.fields('/upload')
        self.assertEqual(set(fields.options), {'1'})
        self.assertEqual(fields.options['1']['data-owner-name'], 'Ana Torres')
        html = self.client.get('/expedients').get_data(as_text=True)
        self.assertNotIn('Luis Vargas', html)
        self.assertNotIn('EXP-LUIS', html)

    def test_older_database_without_display_name_uses_username(self):
        with sqlite3.connect(Path(self.tmp.name) / 'sidoc.sqlite') as db:
            db.execute('ALTER TABLE users DROP COLUMN display_name')
        fields = self.fields('/upload')
        self.assertEqual(fields.options['1']['data-owner-name'], 'ana')
        html = self.client.get('/expedients').get_data(as_text=True)
        self.assertIn('<strong>Responsable:</strong> ana', html)
