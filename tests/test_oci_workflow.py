import io
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from workflow import deadline, stamp


class OCIWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(dict(TESTING=True, DATA_DIR=self.tmp.name))
        self.app.test_cli_runner().invoke(args=['create-admin', 'admin', '--password', 'test-password-123'])
        self.client = self.app.test_client()
        self.login('admin')
        for name in ('ana', 'luis'):
            self.post('/users', dict(username=name, password='test-password-123', role='personal'))

    def tearDown(self):
        self.tmp.cleanup()

    def sql(self, query, params=()):
        with sqlite3.connect(Path(self.tmp.name)/'sidoc.sqlite') as c:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(query, params).fetchall()]

    def post(self, path, data=None, follow=True):
        with self.client.session_transaction() as s:
            token = s['csrf']
        return self.client.post(path, data=dict(data or {}, csrf=token), follow_redirects=follow)

    def login(self, username):
        self.client.get('/login')
        self.post('/login', dict(username=username, password='test-password-123'))

    def request_data(self, **changes):
        data = dict(code='REQ-001-2026', subject='Información de obra', requester='OCI', owner='2',
                    received_at=datetime.now(ZoneInfo('America/Lima')).strftime('%Y-%m-%dT%H:%M'), deadline_days='1')
        data.update(changes)
        return data

    def create_request(self, **changes):
        return self.post('/requests', self.request_data(**changes))

    def upload(self):
        content = b'%PDF-1.4\n%%EOF\n'
        if self.app.extensions['cloud_mode']:
            response = self.post('/api/uploads/start', dict(title='Respuesta PDF',filename='respuesta.pdf',size=str(len(content))), follow=False)
            ticket = response.get_json()['id']
            self.app.extensions['private_storage'].objects[self.app.extensions['private_storage'].signed[-1]] = content
            return self.post('/api/uploads/complete', dict(id=ticket))
        return self.post('/upload', dict(title='Respuesta PDF', pdf=(io.BytesIO(content), 'respuesta.pdf')))

    def create_inventory(self):
        self.post('/inventory', dict(action='location', code='LOC-01', site='Sede central', room='Archivo OCI',
                                     shelf='E02', shelf_level='3', box='C018', folder='04'))
        return self.post('/inventory', dict(action='item', inventory_code='HIST-2018-001', title='Original de prueba',
                         record_type='Expediente', year_from='2018', year_to='2019', custodian='2',
                         physical_location_id='1', conservation='Regular', document_type_id='1'))

    def test_deadline_and_alerts_preserve_lima_and_late_response(self):
        received = datetime(2026, 10, 30, 15, 0, tzinfo=ZoneInfo('America/Lima'))
        self.assertEqual(deadline(received, 1).isoformat(), '2026-10-31T15:00:00-05:00')
        with self.assertRaises(ValueError):
            deadline(received, 4)
        self.create_request(received_at=(datetime.now(ZoneInfo('America/Lima'))-timedelta(days=4)).strftime('%Y-%m-%dT%H:%M'))
        self.assertIn(b'Vencido', self.client.get('/requests').data)
        self.post('/requests/1', dict(action='status', version='0', status='En trámite', note='Iniciada revisión'))
        self.post('/requests/1', dict(action='status', version='1', status='Atendido', note='Respuesta enviada por mesa de partes'))
        row = self.sql('SELECT * FROM service_requests')[0]
        self.assertEqual(row['status'], 'Atendido')
        self.assertIsNotNone(row['responded_at'])
        self.assertIn(b'Atendido fuera de plazo', self.client.get('/requests').data)
        self.assertEqual(len(self.sql('SELECT * FROM request_events')), 3)

    def test_unique_code_validation_and_optimistic_concurrency(self):
        self.create_request()
        self.create_request(code=' req-001-2026 ')
        self.assertEqual(len(self.sql('SELECT * FROM service_requests')), 1)
        self.create_request(code='bad-days', deadline_days='9')
        self.create_request(code='future', received_at='2099-01-01T10:00')
        self.assertEqual(len(self.sql('SELECT * FROM service_requests')), 1)
        self.post('/requests/1', dict(action='status', version='0', status='Atendido', note='Skip'))
        self.assertEqual(self.sql('SELECT status FROM service_requests')[0]['status'], 'Registrado')
        self.post('/requests/1', dict(action='status', version='0', status='En trámite', note='Revisión'))
        self.post('/requests/1', dict(action='assign', version='0', owner='3', note='Formulario antiguo'))
        row = self.sql('SELECT * FROM service_requests')[0]
        self.assertEqual(row['owner'], 2)
        self.assertEqual(row['version'], 1)

    def test_roles_assignment_response_and_archive(self):
        self.create_request()
        original_due = self.sql('SELECT due_at FROM service_requests')[0]['due_at']
        self.login('luis')
        self.assertEqual(self.client.get('/requests/1').status_code, 403)
        self.assertNotIn(b'REQ-001-2026', self.client.get('/requests').data)
        self.assertEqual(self.create_request().status_code, 403)
        self.login('ana')
        self.assertEqual(self.client.get('/requests/1').status_code, 200)
        self.assertEqual(self.post('/requests/1', dict(action='assign', version='0', owner='3', note='Intrusión')).status_code, 403)
        self.post('/requests/1', dict(action='status', version='0', status='En trámite', note='Buscando'))
        self.post('/requests/1', dict(action='status', version='1', status='Atendido', note=''))
        self.assertEqual(self.sql('SELECT status FROM service_requests')[0]['status'], 'En trámite')
        self.login('admin')
        self.upload()
        self.login('ana')
        self.assertEqual(self.post('/requests/1', dict(action='status', version='1', status='Atendido', note='Atendido', response_document_id='1')).status_code, 403)
        self.upload()
        self.post('/requests/1', dict(action='status', version='1', status='Atendido', note='Respondido', response_document_id='2'))
        self.post('/requests/1', dict(action='status', version='2', status='Archivado', note='Personal no archiva'))
        self.assertEqual(self.sql('SELECT status FROM service_requests')[0]['status'], 'Atendido')
        self.login('admin')
        self.post('/requests/1', dict(action='status', version='2', status='Archivado', note='Comprobada atención'))
        row = self.sql('SELECT * FROM service_requests')[0]
        self.assertEqual(row['status'], 'Archivado')
        self.assertEqual(row['due_at'], original_due)
        self.post('/documents/2/delete')
        self.assertEqual(len(self.sql('SELECT * FROM documents WHERE id=2')), 1)

    def test_derivation_revokes_previous_owner_and_keeps_timeline(self):
        self.create_request()
        before = self.sql('SELECT due_at FROM service_requests')[0]['due_at']
        self.post('/requests/1', dict(action='assign', version='0', owner='3', note='Especialidad asignada'))
        self.assertEqual(self.sql('SELECT due_at FROM service_requests')[0]['due_at'], before)
        self.login('ana')
        self.assertEqual(self.client.get('/requests/1').status_code, 403)
        self.login('luis')
        self.assertIn(b'Especialidad asignada', self.client.get('/requests/1').data)

    def test_physical_inventory_without_pdf_year_search_and_location(self):
        page = self.create_inventory()
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'C018', page.data)
        self.assertEqual(self.sql('SELECT digitization_status FROM archive_items')[0]['digitization_status'], 'Pendiente')
        self.assertIn(b'HIST-2018-001', self.client.get('/inventory?q=c018&year=2019').data)
        self.assertNotIn(b'HIST-2018-001', self.client.get('/inventory?year=2020').data)
        self.post('/inventory/1', dict(action='state', digitization_status='Revisado', physical_location_id='1', note='Sin PDF'))
        self.assertEqual(self.sql('SELECT digitization_status FROM archive_items')[0]['digitization_status'], 'Pendiente')
        self.login('luis')
        self.assertEqual(self.client.get('/inventory/1').status_code, 403)
        self.assertNotIn(b'HIST-2018-001', self.client.get('/inventory').data)
        self.login('ana')
        self.assertEqual(self.client.get('/inventory/1').status_code, 200)
        self.assertEqual(self.post('/inventory/1', dict(action='state')).status_code, 403)

    def test_links_protected_pdf_and_location_history(self):
        self.create_inventory()
        self.upload()
        self.post('/inventory/1', dict(action='link', document_id='1', part_label='Tomo I'))
        self.post('/inventory/1', dict(action='link', document_id='1', part_label='Duplicado'))
        self.assertEqual(len(self.sql('SELECT * FROM archive_item_documents')), 1)
        self.post('/inventory/1', dict(action='state', digitization_status='Revisado', physical_location_id='1', note='Legibilidad y folios revisados'))
        self.assertEqual(self.sql('SELECT digitization_status FROM archive_items')[0]['digitization_status'], 'Revisado')
        self.post('/documents/1/delete')
        self.assertEqual(len(self.sql('SELECT * FROM documents')), 1)
        self.login('ana')
        self.assertNotIn(b'Respuesta PDF', self.client.get('/inventory/1').data)
        self.assertEqual(self.client.get('/documents/1/download').status_code, 403)
        self.login('admin')
        event = self.sql("SELECT * FROM events WHERE description LIKE ?", ('%Legibilidad%',))
        self.assertEqual(len(event), 1)

    def test_missing_cloud_migration_shows_instructions_instead_of_crashing(self):
        from cloud_backend import HybridRow
        path = Path(self.tmp.name)/'sidoc.sqlite'
        class Connection:
            def __init__(self):
                self.c = sqlite3.connect(path)
                self.c.row_factory = sqlite3.Row
            def execute(self, sql, params=()):
                if sql.startswith('SELECT to_regclass'):
                    class Cursor:
                        def fetchone(self):
                            return HybridRow(archive='sidoc.archive_items', requests=None)
                    return Cursor()
                return self.c.execute(sql, params)
            def close(self):
                self.c.close()
            def commit(self):
                self.c.commit()
        cloud_app = create_app(dict(TESTING=True, CLOUD_MODE=True, DATABASE_URL='unused',
            SUPABASE_URL='https://supabase.test', SUPABASE_SERVICE_ROLE_KEY='test',
            SECRET_KEY='s'*64, BOOTSTRAP_TOKEN='b'*64, DATABASE_FACTORY=Connection))
        client = cloud_app.test_client()
        client.get('/login')
        with client.session_transaction() as session:
            token = session['csrf']
        client.post('/login', data=dict(username='admin', password='test-password-123', csrf=token))
        for url in ('/requests', '/inventory'):
            result = client.get(url)
            self.assertEqual(result.status_code, 503)
            self.assertIn(b'0004_tramite_oci.sql', result.data)

    def test_csv_respects_scope_and_neutralizes_formula_text(self):
        self.create_request(subject='=1+1')
        self.create_request(code='REQ-LUIS', owner='3', subject='Confidencial de Luis')
        self.login('ana')
        with self.client.get('/requests/export') as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"'=1+1", response.data)
            self.assertNotIn(b'Confidencial de Luis', response.data)
        self.assertEqual(self.client.post('/requests/1', data={}).status_code, 400)

    def test_near_deadline_and_physical_move_history(self):
        from datetime import timezone
        self.create_request()
        current = datetime.now(timezone.utc)
        with patch('workflow.now', return_value=current):
            expected = stamp(current + timedelta(hours=10))
            self.sql('UPDATE service_requests SET due_at=? WHERE id=1 RETURNING id', (expected,))
            self.assertIn(b'Vence en 24 h', self.client.get('/requests').data)
        self.create_inventory()
        self.post('/inventory', dict(action='location', code='LOC-02', site='Sede central', room='Archivo nuevo', box='C019'))
        self.post('/inventory/1', dict(action='state', digitization_status='En proceso', physical_location_id='2', note='Traslado de caja autorizado'))
        self.assertEqual(self.sql('SELECT physical_location_id FROM archive_items')[0]['physical_location_id'], 2)
        page = self.client.get('/inventory/1').data
        self.assertIn(b'Traslado de caja autorizado', page)
        self.assertIn(b'Archivo nuevo', page)

    def test_pdf_duplicate_content_is_reused_per_owner(self):
        self.upload()
        self.upload()
        self.assertEqual(len(self.sql('SELECT * FROM documents')), 1)
        if not self.app.extensions['cloud_mode']:
            self.assertEqual(len(list((Path(self.tmp.name)/'pdfs').glob('*.pdf'))), 1)
        self.login('ana')
        self.upload()
        # No disclosure of other users' documents through duplicate detection.
        self.assertEqual(len(self.sql('SELECT * FROM documents')), 2)


if __name__ == '__main__':
    unittest.main()
