"""Opt-in real PostgreSQL suite. Only permits the disposable loopback QA database."""
import os
import tempfile
import unittest
from urllib.parse import urlparse

import psycopg
from app import create_app
from cloud_backend import PostgresDatabase
import test_cloud as cloud_tests

FakeStorage = cloud_tests.FakeStorage
PASSWORD = cloud_tests.PASSWORD

QA_URL = os.environ.get('SIDOC_TEST_DATABASE_URL', '')


@unittest.skipUnless(QA_URL, 'Requires disposable local PostgreSQL QA database')
class PostgresCloudTests(cloud_tests.CloudTests):
    def setUp(self):
        url = urlparse(QA_URL)
        if url.hostname not in ('127.0.0.1', 'localhost') or url.path != '/sidoc_qa':
            raise RuntimeError('Integration tests only permit loopback /sidoc_qa')
        with psycopg.connect(QA_URL, sslmode='require') as connection:
            connection.execute('''TRUNCATE sidoc.object_deletions,sidoc.pending_uploads,sidoc.favorites,
                sidoc.loans,sidoc.events,sidoc.login_attempts,sidoc.documents,sidoc.expedients,sidoc.settings,sidoc.users
                RESTART IDENTITY CASCADE''')
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = FakeStorage()
        self.options = dict(TESTING=True, CLOUD_MODE=True, DATABASE_URL=QA_URL,
                            SUPABASE_URL='https://supabase.test', SUPABASE_SERVICE_ROLE_KEY='test-key',
                            SECRET_KEY='s' * 64, BOOTSTRAP_TOKEN='b' * 64,
                            DATA_DIR=self.tmp.name, STORAGE_CLIENT=self.storage)
        self.app = create_app(self.options)
        result = self.app.test_cli_runner().invoke(args=['create-admin', 'admin', '--password', PASSWORD])
        self.assertEqual(result.exit_code, 0, result.output)
        self.client = self.app.test_client()
        self.post('/login', {'username': 'admin', 'password': PASSWORD})

    def connection(self):
        return PostgresDatabase(QA_URL)

    def test_postgres_reports_filters_settings_and_loans(self):
        self.post('/expedients', {'code': 'EXP-001', 'title': 'Prueba PostgreSQL'})
        ticket = self.start()
        self.post('/api/uploads/complete', {'id': ticket})
        self.post('/documents/1/edit', {'title': 'Informe archivado PG', 'code': 'INF-PG', 'kind': 'Informe',
                                     'status': 'Archivado', 'folios': '2', 'expedient_id': '1'})
        self.assertIn(b'Informe archivado PG', self.client.get('/?q=EXP-001').data)
        self.assertIn(b'Informe archivado PG', self.client.get('/archive').data)
        self.post('/documents/1/favorite')
        self.assertIn(b'Informe archivado PG', self.client.get('/?tab=favorites').data)
        self.post('/settings', {'institution': 'OCI de prueba', 'contact': 'demo@example.invalid'})
        self.assertIn(b'OCI de prueba', self.client.get('/settings').data)
        self.post('/loans', {'document_id': '1', 'borrower': 'Oficina de prueba', 'due': '2099-12-31'})
        self.post('/loans/1/return')
        self.assertIn(b'Devuelto', self.client.get('/loans').data)
        self.assertEqual(self.client.get('/reports').status_code, 200)
        with self.client.get('/export') as response:
            self.assertIn(b'INF-PG', response.data)
        self.assertEqual(self.client.get('/healthz').status_code, 200)

    def test_anonymous_database_role_cannot_read_private_user_table(self):
        with psycopg.connect(QA_URL, sslmode='require') as connection:
            connection.execute('SET ROLE anon')
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                connection.execute('SELECT * FROM sidoc.users')
            connection.rollback()
