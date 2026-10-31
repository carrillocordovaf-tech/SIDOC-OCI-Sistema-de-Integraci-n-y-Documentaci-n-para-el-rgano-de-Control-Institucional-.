"""Read-only, stateless demonstration. Never connects to Supabase or opens a database."""
import csv
import io
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, abort, g, redirect, render_template, request, send_file, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from app import TYPES, STATES

USERS = [
    dict(id=1, username='maria.rojas', role='admin', active=1),
    dict(id=2, username='ana.torres', role='personal', active=1),
    dict(id=3, username='luis.vargas', role='personal', active=1),
]
EXPEDIENTS = [dict(id=1, code='EXP-038-2026', title='Control simultáneo · Infraestructura', owner=2),
              dict(id=2, code='EXP-035-2026', title='Auditoría de cumplimiento · Logística', owner=1)]
SAMPLES = [
    ('Informe de control posterior', 'INF-024-2026-OCI', 'Informe', 'Contratación de bienes y servicios', 32, 'En revisión', 1, 1),
    ('Solicitud de información presupuestal', 'OF-186-2026-GRA/OCI', 'Oficio', 'Gerencia Regional de Planeamiento', 4, 'Pendiente', 2, 1),
    ('Visita de control a obra vial', 'INF-023-2026-OCI', 'Informe', 'Mejoramiento de vía · Chachapoyas', 48, 'Archivado', 3, 2),
    ('Asignación de comisión de control', 'MEM-092-2026-OCI', 'Memorando', 'Comisión de control institucional', 3, 'Archivado', 1, 2),
    ('Acta de entrega de documentación', 'ACT-041-2026-OCI', 'Acta', 'Entrega de acervo documental', 12, 'En revisión', 2, 1),
    ('Remisión de informe de orientación', 'OF-185-2026-GRA/OCI', 'Oficio', 'Servicio de orientación de oficio', 8, 'Archivado', 2, 2),
]
DOCUMENTS = [dict(id=i, title=title, code=code, kind=kind, unit=unit, folios=folios, status=status,
                  owner=owner, username=USERS[owner-1]['username'], expedient_id=exp,
                  expedient_code=EXPEDIENTS[exp-1]['code'], size=840000+i*200000,
                  created=f'2026-10-{31-i:02d} 09:30:00', filename=f'demostracion-{i}.pdf', favorite=i in (1, 2))
             for i, (title, code, kind, unit, folios, status, owner, exp) in enumerate(SAMPLES, 1)]
SECTION_TITLES = dict(documents='Gestión documental', archive='Archivo central', expedients='Expedientes',
                      users='Usuarios y permisos', settings='Configuración', summary='Resumen',
                      reports='Reportes', loans='Préstamos', account='Mi cuenta')


def example_pdf():
    stream = b'BT /F1 16 Tf 40 700 Td (SIDOC-OCI - PDF de demostracion, sin datos reales) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    content = b'%PDF-1.4\n'
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(content)
    content += b'xref\n0 6\n0000000000 65535 f \n'
    content += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    return content + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


def create_demo_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 64 * 1024
    # Role selection is only a tour preference, never an authentication credential.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0)

    @app.before_request
    def demo_user():
        g.user = USERS[1] if request.cookies.get('sidoc_demo_role') == 'personal' else USERS[0]
        if request.endpoint in ('login', 'setup'):
            g.user = None
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.endpoint != 'logout':
            return render_template('error.html', message='Esta es una demostración. No se guardan cambios ni archivos.'), 405

    @app.context_processor
    def context():
        return dict(demo_mode=True, cloud_mode=False, custom_logo=False, setup_available=False,
                    bootstrap_required=False, section_titles=SECTION_TITLES, types=TYPES, states=STATES,
                    config_values=dict(institution='Gobierno Regional Amazonas', contact=''),
                    today=datetime.now(ZoneInfo('America/Lima')).strftime('%d/%m/%Y'),
                    asset_exists=lambda filename: False)

    @app.template_filter('filesize')
    def filesize(value):
        return f'{value/1048576:.1f} MB' if value >= 1048576 else f'{value/1024:.0f} KB'

    def admin():
        if g.user['role'] != 'admin':
            abort(403)

    def visible_documents():
        return [dict(doc) for doc in DOCUMENTS if g.user['role'] == 'admin' or doc['owner'] == g.user['id']]

    def visible_expedients():
        return [dict(exp, count=sum(doc['expedient_id'] == exp['id'] for doc in visible_documents()))
                for exp in EXPEDIENTS if g.user['role'] == 'admin' or exp['owner'] == g.user['id']]

    def filtered(archive=False):
        documents = visible_documents()
        query = request.args.get('q', '').strip().casefold()
        if query:
            documents = [doc for doc in documents if query in ' '.join(str(doc[k]) for k in ('title', 'code', 'unit', 'expedient_code')).casefold()]
        for key in ('kind', 'status'):
            if request.args.get(key):
                documents = [doc for doc in documents if doc[key] == request.args[key]]
        if request.args.get('year'):
            documents = [doc for doc in documents if doc['created'].startswith(request.args['year'])]
        if archive:
            documents = [doc for doc in documents if doc['status'] == 'Archivado']
        if request.args.get('tab') == 'mine':
            documents = [doc for doc in documents if doc['owner'] == g.user['id']]
        elif request.args.get('tab') == 'favorites':
            documents = [doc for doc in documents if doc['favorite']]
        if request.args.get('expedient', type=int):
            documents = [doc for doc in documents if doc['expedient_id'] == request.args.get('expedient', type=int)]
        return sorted(documents, key=lambda doc: doc['id'], reverse=request.args.get('sort') == 'oldest')

    def document(doc_id):
        doc = next((doc for doc in DOCUMENTS if doc['id'] == doc_id), None)
        if not doc:
            abort(404)
        if g.user['role'] != 'admin' and doc['owner'] != g.user['id']:
            abort(403)
        return doc

    def events():
        return [dict(username=doc['username'], description=f'Registró {doc["code"]} · ejemplo', created=doc['created'])
                for doc in visible_documents()][:4]

    @app.get('/login')
    def login():
        return render_template('login.html')

    @app.get('/setup')
    def setup():
        return redirect(url_for('login'))

    @app.get('/demo/role/<role>')
    def demo_role(role):
        if role not in ('admin', 'personal'):
            abort(404)
        response = redirect(url_for('index'))
        response.set_cookie('sidoc_demo_role', role, httponly=True, samesite='Lax', secure=request.is_secure)
        return response

    @app.post('/logout')
    def logout():
        response = redirect(url_for('login'))
        response.delete_cookie('sidoc_demo_role', httponly=True, samesite='Lax', secure=request.is_secure)
        return response

    @app.get('/archive', endpoint='archive')
    @app.get('/')
    def index():
        archive = request.path == '/archive'
        documents = filtered(archive)
        scoped = visible_documents()
        totals = dict(total=len(scoped), pending=sum(d['status'] != 'Archivado' for d in scoped),
                      archived=sum(d['status'] == 'Archivado' for d in scoped))
        return render_template('index.html', section='archive' if archive else 'documents', archive=archive,
                               documents=documents, total=len(documents), totals=totals,
                               exp_count=len(visible_expedients()), years=['2026'], page=1, pages=1,
                               expedients=visible_expedients(), events=events())

    @app.get('/upload')
    def upload():
        return render_template('document_form.html', section='documents', doc=None, expedients=visible_expedients())

    @app.get('/documents/<int:doc_id>/edit')
    def edit_document(doc_id):
        admin()
        return render_template('document_form.html', section='documents', doc=document(doc_id), expedients=visible_expedients())

    @app.get('/documents/<int:doc_id>/download')
    def download(doc_id):
        document(doc_id)
        return send_file(io.BytesIO(example_pdf()), mimetype='application/pdf', as_attachment=True,
                         download_name=f'SIDOC-demostracion-{doc_id}.pdf')

    @app.get('/expedients')
    def expedients():
        return render_template('expedients.html', section='expedients', expedients=visible_expedients(), owners=USERS)

    @app.get('/users')
    def users():
        admin()
        return render_template('users.html', section='users', users=USERS)

    @app.get('/loans')
    def loans():
        admin()
        loan = dict(id=1, code=DOCUMENTS[0]['code'], title=DOCUMENTS[0]['title'],
                    borrower='Oficina de Infraestructura · Ejemplo', due='2026-11-07', returned=None)
        return render_template('loans.html', section='loans', loans=[loan], documents=visible_documents())

    @app.get('/summary', endpoint='summary')
    @app.get('/activity', endpoint='activity')
    @app.get('/reports')
    def reports():
        counts = [dict(status=status, count=count) for status, count in Counter(d['status'] for d in visible_documents()).items()]
        return render_template('reports.html', section='summary' if request.path == '/summary' else 'reports',
                               counts=counts, events=events())

    @app.get('/account')
    def account():
        return render_template('account.html', section='account')

    @app.get('/settings')
    def configuration():
        admin()
        return render_template('settings.html', section='settings')

    @app.get('/branding/logo')
    def institutional_logo():
        return redirect(url_for('static', filename='branding/escudo-amazonas.jpg'))

    @app.get('/export')
    def export():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['DEMOSTRACIÓN: datos ficticios'])
        writer.writerow(['Código', 'Asunto', 'Estado'])
        writer.writerows((d['code'], d['title'], d['status']) for d in filtered())
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv',
                         as_attachment=True, download_name='SIDOC-demostracion.csv')

    @app.get('/healthz')
    def healthz():
        return {'status': 'ok', 'mode': 'demo'}

    # Keep shared template links valid. These routes never change anything.
    def readonly(**kwargs):
        return render_template('error.html', message='La demostración no guarda cambios ni archivos.'), 405
    for endpoint, path in [('favorite', '/documents/<int:doc_id>/favorite'),
                           ('delete', '/documents/<int:doc_id>/delete'),
                           ('update_user', '/users/<int:user_id>/update'),
                           ('return_loan', '/loans/<int:loan_id>/return'),
                           ('upload_logo', '/settings/logo'), ('storage_cleanup', '/settings/storage-cleanup')]:
        app.add_url_rule(path, endpoint, readonly, methods=['POST'])

    @app.errorhandler(403)
    @app.errorhandler(404)
    def error(error):
        message = 'Esta vista está reservada al administrador. Puedes cambiar de perfil en la barra de demostración.' if error.code == 403 else 'Esta página no existe.'
        return render_template('error.html', message=message), error.code

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    return app
