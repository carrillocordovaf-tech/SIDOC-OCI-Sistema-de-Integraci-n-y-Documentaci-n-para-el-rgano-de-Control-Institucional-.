"""Server-only PostgreSQL and private Supabase Storage adapters."""
import re
from urllib.parse import quote, urljoin, urlparse

import requests

TABLES = ('users', 'documents', 'expedients', 'favorites', 'loans', 'events', 'settings',
          'login_attempts', 'pending_uploads', 'object_deletions')
TABLE_PATTERN = re.compile(r'\b(' + '|'.join(TABLES) + r')\b')


class HybridRow(dict):
    """Keep SQLite's named and positional row access for existing application code."""
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def postgres_sql(sql):
    # Application queries are fixed SQL; all visitor values remain bound parameters.
    sql = TABLE_PATTERN.sub(lambda m: 'sidoc.' + m.group(), sql)
    return sql.replace('?', '%s')


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return HybridRow(row) if row is not None else None

    def fetchall(self):
        return [HybridRow(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PostgresDatabase:
    def __init__(self, url):
        import psycopg
        from psycopg.rows import dict_row
        self.connection = psycopg.connect(url, sslmode='require', connect_timeout=10,
                                          prepare_threshold=None, row_factory=dict_row)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        try:
            self.rollback() if error else self.commit()
        finally:
            self.close()

    def execute(self, sql, params=()):
        if sql == 'BEGIN IMMEDIATE':
            # Serialize bootstrap across serverless instances, on this transaction.
            sql = 'SELECT pg_advisory_xact_lock(7340901)'
        return Cursor(self.connection.execute(postgres_sql(sql), params))

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


class StorageError(Exception):
    pass


class PrivateStorage:
    def __init__(self, url, key, bucket='sidoc-documents'):
        if urlparse(url).scheme != 'https' or not urlparse(url).hostname:
            raise ValueError('SUPABASE_URL debe ser una URL HTTPS válida.')
        self.origin = url.rstrip('/')
        self.base = self.origin + '/storage/v1'
        self.bucket = quote(bucket, safe='')
        self.http = requests.Session()
        self.http.headers.update({'apikey': key, 'Authorization': 'Bearer ' + key})

    def _request(self, method, path, **kwargs):
        try:
            response = self.http.request(method, self.base + path, timeout=(10, 40), **kwargs)
        except requests.RequestException:
            raise StorageError('No se pudo conectar al almacenamiento privado.') from None
        if response.status_code >= 400:
            response.close()
            raise StorageError('El almacenamiento no pudo completar la operación.')
        return response

    def _signed_url(self, value):
        if not value:
            raise StorageError('No se pudo generar el enlace temporal.')
        if value.startswith('/object/'):
            value = self.base + value
        else:
            value = urljoin(self.origin, value)
        if urlparse(value).netloc != urlparse(self.origin).netloc or urlparse(value).scheme != 'https':
            raise StorageError('Enlace de almacenamiento inválido.')
        return value

    def sign_upload(self, key):
        with self._request('POST', '/object/upload/sign/' + self.bucket + '/' + quote(key, safe='/'),
                           json={}) as response:
            return self._signed_url(response.json().get('url'))

    def sign_download(self, key, filename):
        with self._request('POST', '/object/sign/' + self.bucket + '/' + quote(key, safe='/'),
                           json={'expiresIn': 60}) as response:
            result = self._signed_url(response.json().get('signedURL'))
        return result + '&download=' + quote(filename, safe='')

    def read(self, key, limit):
        with self._request('GET', '/object/authenticated/' + self.bucket + '/' + quote(key, safe='/'), stream=True) as response:
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > limit:
                    raise StorageError('El archivo supera el tamaño permitido.')
            return bytes(content)

    def put(self, key, content, mime):
        with self._request('POST', '/object/' + self.bucket + '/' + quote(key, safe='/'),
                           data=content, headers={'Content-Type': mime, 'x-upsert': 'true'}):
            pass

    def remove(self, key):
        with self._request('DELETE', '/object/' + self.bucket, json={'prefixes': [key]}):
            pass
