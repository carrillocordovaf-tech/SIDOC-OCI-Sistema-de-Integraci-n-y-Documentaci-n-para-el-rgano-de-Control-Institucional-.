Proveedor elegido: **Vercel + Supabase**. La guía actual está en [VERCEL-SUPABASE.md](VERCEL-SUPABASE.md). El contenido siguiente conserva las opciones de servicios complementarios.

# Servicios externos y pasos pendientes

## Desarrollo local: ninguno obligatorio

SQLite guarda los datos en `instance/sidoc.sqlite` y los PDF en `instance/pdfs`. No se requiere Supabase, Firebase ni una cuenta de almacenamiento externo. Inter se sirve desde el repositorio. Solo se necesita PyPI para instalar las dependencias de Python.

## Acceso con Google: Google Cloud / OpenID Connect (opcional, implementado; activación pendiente)

El módulo está implementado. Sigue [GOOGLE-OAUTH.md](GOOGLE-OAUTH.md) para crear el cliente, aplicar la segunda migración, configurar sus variables y autorizar cada cuenta. No se habilita en el modo de demostración.

## Recuperación automática por correo: servidor SMTP institucional (opcional, no implementado)

El administrador ya puede restablecer una contraseña desde Usuarios y permisos. Para automatizar el proceso por correo:

1. Solicitar a TI el host SMTP, puerto, modalidad TLS, remitente autorizado y credenciales de servicio (o mecanismo institucional equivalente).
2. Guardar los valores en secretos del entorno, sin enviarlos por chat ni incluirlos en Git.
3. Implementar tokens aleatorios de un solo uso, con caducidad, guardados mediante hash; respuesta indistinguible para cuentas existentes e inexistentes; limitación de solicitudes y formulario de cambio de contraseña.
4. Probar envío y expiración con un buzón de pruebas. El acceso a SMTP puede requerir una regla TCP autorizada del entorno.

## Respaldo

No hay respaldo automático configurado. Para una copia manual coherente, detener el servidor y copiar íntegra la carpeta `instance` (base de datos, PDF y clave). Guardarla fuera del equipo con acceso restringido y comprobar una restauración. No ejecutar esta copia sobre un servidor con escrituras activas.

La elección de un proveedor de almacenamiento en nube queda pendiente de las condiciones de la institución. No se ha creado ningún recurso externo ni desplegado el aplicativo.
