const themeButton = document.getElementById('theme-toggle');
function reflectTheme() { themeButton?.setAttribute('aria-pressed', String(document.documentElement.dataset.theme === 'dark')); }
reflectTheme();
themeButton?.addEventListener('click', () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('sidoc-theme', next); } catch {}
  reflectTheme();
});
const menuButton = document.getElementById('menu-toggle');
function closeMenu() { document.body.classList.remove('menu-open'); menuButton?.setAttribute('aria-expanded', 'false'); }
menuButton?.addEventListener('click', () => {
  const open = document.body.classList.toggle('menu-open');
  menuButton.setAttribute('aria-expanded', String(open));
  if(open) document.getElementById('menu-close')?.focus();
});
document.getElementById('menu-close')?.addEventListener('click', () => {closeMenu(); menuButton?.focus();});
document.addEventListener('keydown', e => {if(e.key === 'Escape') closeMenu();});
const password = document.getElementById('password');
document.getElementById('password-toggle')?.addEventListener('click', e => {
  const visible = password.type === 'password';
  password.type = visible ? 'text' : 'password';
  e.currentTarget.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
  e.currentTarget.setAttribute('aria-pressed', String(visible));
});
const username = document.getElementById('username');
const remember = document.getElementById('remember');
if (remember && username) {
  try { const saved = localStorage.getItem('sidoc-username'); if(saved) { username.value = saved; remember.checked = true; } } catch {}
  document.getElementById('login-form')?.addEventListener('submit', () => {
    try { if(remember.checked) localStorage.setItem('sidoc-username', username.value); else localStorage.removeItem('sidoc-username'); } catch {}
  });
}
const info = {
  google: ['Acceso con Google pendiente', 'El acceso con Google todavía no está habilitado. Ingresa con tu cuenta de SIDOC-OCI.'],
  recovery: ['Recuperar el acceso', 'Solicita al administrador que restablezca tu contraseña desde Usuarios y permisos. La recuperación por correo todavía no está habilitada.'],
  support: ['Solicitar una cuenta', 'Solicita tu cuenta al administrador del Órgano de Control Institucional.'],
  privacy: ['Privacidad y seguridad', 'Acceso exclusivo para personal autorizado. Esta versión guarda los PDF y sus datos en el servidor local y registra las operaciones. El respaldo en la nube aún no está configurado.']
};
if (document.body.dataset.cloud === 'true') info.privacy = ['Privacidad y seguridad', 'Acceso exclusivo para personal autorizado. Los documentos se guardan en almacenamiento privado de Supabase y las operaciones quedan registradas.'];
document.querySelectorAll('[data-info]').forEach(button => button.addEventListener('click', () => {
  const [title, text] = info[button.dataset.info];
  document.getElementById('info-title').textContent = title;
  document.getElementById('info-content').textContent = text + (button.dataset.contact ? ' Contacto: ' + button.dataset.contact : '');
  document.getElementById('info-dialog').showModal();
}));
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
  if(!window.confirm(form.dataset.confirm)) event.preventDefault();
}));
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => {
  document.getElementById('document-list')?.classList.toggle('grid-view', button.dataset.view === 'grid');
  document.querySelectorAll('[data-view]').forEach(other => other.setAttribute('aria-pressed', String(other === button)));
}));

const mobileLayout = window.matchMedia('(max-width: 760px)');
function updateFilterLabels() {
  document.querySelectorAll('option[data-mobile-label]').forEach(option => {
    option.textContent = mobileLayout.matches ? option.dataset.mobileLabel : option.dataset.desktopLabel;
  });
}
updateFilterLabels();
mobileLayout.addEventListener('change', updateFilterLabels);

const cloudUpload = document.getElementById('cloud-upload-form');
cloudUpload?.addEventListener('submit', async event => {
  event.preventDefault();
  const button = cloudUpload.querySelector('button[type="submit"], button.primary');
  const status = document.getElementById('upload-status');
  const file = cloudUpload.querySelector('[name="pdf"]').files[0];
  if (!file || file.size > 10 * 1024 * 1024) {
    status.textContent = 'Selecciona un PDF de hasta 10 MB.';
    return;
  }
  button.disabled = true;
  try {
    const metadata = new FormData(cloudUpload);
    metadata.delete('pdf');
    metadata.set('filename', file.name);
    metadata.set('size', String(file.size));
    status.textContent = 'Preparando carga segura…';
    const start = await fetch('/api/uploads/start', {method: 'POST', body: metadata});
    const ticket = await start.json();
    if (!start.ok) throw new Error(ticket.error || 'No se pudo preparar la carga.');
    status.textContent = 'Cargando PDF…';
    const payload = new FormData();
    payload.append('cacheControl', '3600');
    payload.append('', new Blob([file], {type: 'application/pdf'}), file.name);
    const upload = await fetch(ticket.upload_url, {method: 'PUT', body: payload, credentials: 'omit'});
    if (!upload.ok) throw new Error('No se pudo cargar el PDF. Revisa la conexión e inténtalo nuevamente.');
    status.textContent = 'Validando y registrando documento…';
    const complete = await fetch('/api/uploads/complete', {
      method: 'POST', body: new URLSearchParams({id: ticket.id, csrf: metadata.get('csrf')})
    });
    const result = await complete.json();
    if (!complete.ok) throw new Error(result.error || 'No se pudo registrar el documento.');
    window.location.assign(result.redirect);
  } catch (error) {
    status.textContent = error.message || 'No se pudo completar la carga. Inténtalo nuevamente.';
    button.disabled = false;
  }
});
