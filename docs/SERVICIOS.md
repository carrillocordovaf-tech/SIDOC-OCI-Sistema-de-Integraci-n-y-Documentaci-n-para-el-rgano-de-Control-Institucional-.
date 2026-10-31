Proveedor elegido: **Vercel + Supabase**. La guía actual está en [VERCEL-SUPABASE.md](VERCEL-SUPABASE.md). El contenido siguiente conserva las opciones de servicios complementarios.

# Servicios externos y pasos pendientes

## Desarrollo local: ninguno obligatorio

SQLite guarda los datos en `instance/sidoc.sqlite` y los PDF en `instance/pdfs`. No se requiere Supabase, Firebase ni una cuenta de almacenamiento externo. Inter se sirve desde el repositorio. Solo se necesita PyPI para instalar las dependencias de Python.

## Acceso con Google: Google Cloud / Google Identity Services (opcional, no implementado)

El botón de la maqueta todavía no inicia OAuth. Para habilitarlo:

1. Entrar en Google Cloud Console con la cuenta institucional y crear o seleccionar un proyecto.
2. En Google Auth Platform, configurar Branding, Audience y Data Access; solicitar únicamente `openid`, `email` y `profile`.
3. Elegir audiencia interna solo si la organización dispone de Google Workspace y el proyecto pertenece a ella. En pruebas externas, añadir usuarios de prueba autorizados.
4. Crear un cliente OAuth de tipo aplicación web. Como URI de redirección local propuesto usar `http://localhost:5000/auth/google/callback`; usar siempre el mismo host al abrir el aplicativo. Esa ruta AÚN NO EXISTE y debe implementarse antes de probar OAuth.
5. Guardar el Client ID y Client Secret en variables privadas del entorno (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`), nunca en Git ni en este chat.
6. Implementar el flujo OpenID Connect y el callback en el servidor, con state/nonce, validación de emisor/audiencia/email verificado y asociación a una cuenta activa ya autorizada por el administrador. No conceder acceso por el solo hecho de tener una cuenta de Google ni confiar en un correo enviado por el navegador.
7. Probar cuenta autorizada, cuenta no autorizada, cuenta desactivada y cierre de sesión. Configurar una URI HTTPS solo cuando se autorice un despliegue.

Las variables anteriores están propuestas; el código actual no las consume. Crear credenciales por sí solo no activa el botón.

## Recuperación automática por correo: servidor SMTP institucional (opcional, no implementado)

El administrador ya puede restablecer una contraseña desde Usuarios y permisos. Para automatizar el proceso por correo:

1. Solicitar a TI el host SMTP, puerto, modalidad TLS, remitente autorizado y credenciales de servicio (o mecanismo institucional equivalente).
2. Guardar los valores en secretos del entorno, sin enviarlos por chat ni incluirlos en Git.
3. Implementar tokens aleatorios de un solo uso, con caducidad, guardados mediante hash; respuesta indistinguible para cuentas existentes e inexistentes; limitación de solicitudes y formulario de cambio de contraseña.
4. Probar envío y expiración con un buzón de pruebas. El acceso a SMTP puede requerir una regla TCP autorizada del entorno.

## Respaldo

No hay respaldo automático configurado. Para una copia manual coherente, detener el servidor y copiar íntegra la carpeta `instance` (base de datos, PDF y clave). Guardarla fuera del equipo con acceso restringido y comprobar una restauración. No ejecutar esta copia sobre un servidor con escrituras activas.

La elección de un proveedor de almacenamiento en nube queda pendiente de las condiciones de la institución. No se ha creado ningún recurso externo ni desplegado el aplicativo.
