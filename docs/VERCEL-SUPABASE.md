# Despliegue de SIDOC-OCI: Vercel + Supabase

Para ver primero las pantallas sin configurar la base de datos, usa la [demostración navegable](DEMOSTRACION.md) con `SIDOC_DEMO=1`. Los pasos siguientes corresponden al aplicativo real.

## Estado

El código está adaptado a Vercel y Supabase. El usuario confirmó mediante las pantallas del panel la creación de tablas y Storage, conexión con Vercel e ingreso de un administrador. La actualización de trámite e inventario requiere aplicar 0004 y desplegar el código nuevo. No se ha verificado esta actualización en su producción.

## Arquitectura

- Vercel ejecuta `wsgi:app` con Python 3.12 y Flask.
- Supabase PostgreSQL conserva cuentas, roles, documentos, expedientes, préstamos y auditoría en el esquema privado `sidoc`.
- Supabase Storage conserva PDF y el escudo personalizado en un bucket privado `sidoc-documents`.
- El servidor conserva el inicio de sesión con contraseña y los roles administrador/personal. No se usa registro público ni se convierte automáticamente una cuenta de Google en una cuenta del aplicativo. Supabase Auth no se necesita para esta versión.
- El escudo original y las fuentes se sirven desde los assets de Vercel. Los assets se copian a `public/static` durante el build.
- No se usa SQLite ni el disco temporal de Vercel para datos de producción. Un despliegue con configuración incompleta falla en vez de crear una base vacía temporal.

## 1. Autorizar las cuentas

Instala las integraciones de Vercel y Supabase disponibles en este chat y autoriza las cuentas donde quieras alojar el proyecto. Con la autorización confirmada se podrá seleccionar o crear los proyectos y ejecutar los pasos restantes. No envíes contraseñas, tokens ni claves privadas por el chat.

Alternativa manual: realiza los pasos siguientes en los paneles oficiales. No contrates un plan sin revisar sus condiciones y límites.

## 2. Preparar Supabase

1. En https://supabase.com/dashboard crea un proyecto o selecciona uno destinado a SIDOC-OCI. Elige la región adecuada para tu institución y guarda la contraseña de la base de datos en tu gestor de contraseñas.
2. En SQL Editor ejecuta una sola vez `supabase/migrations/0001_sidoc.sql` , después `supabase/migrations/0002_google_oauth.sql`, `supabase/migrations/0003_archivo_historico.sql` y `supabase/migrations/0004_tramite_oci.sql`, en ese orden para una instalación nueva. En una base existente aplicar únicamente las migraciones pendientes. La migración no contiene usuarios ni datos de demostración. No la repitas sobre un esquema existente: las modificaciones posteriores deben usar nuevas migraciones.
3. Ejecuta `supabase/storage.sql`. Crea/ajusta el bucket privado `sidoc-documents`, con máximo de 10 MB y tipos PDF/PNG/JPEG. No lo marques público ni crees políticas anónimas de lectura/escritura. PNG/JPEG se usan solo para el escudo administrativo.
4. En **Connect → Transaction pooler**, copia la cadena real de conexión (puerto 6543), con usuario y host exactos del panel, e incorpora la contraseña correctamente codificada. No deduzcas el host a partir de la región. Esta cadena será `DATABASE_URL`.
5. Copia la URL HTTPS del proyecto como `SUPABASE_URL` y la clave heredada `service_role` del apartado API Keys como `SUPABASE_SERVICE_ROLE_KEY`. Esa clave es exclusiva del backend; nunca debe aparecer en HTML, JavaScript ni variables con prefijo público.
6. Mantén `sidoc` fuera de los esquemas expuestos por la Data API. La migración activa RLS y revoca acceso de `anon`/`authenticated`; la conexión privada del backend gestiona los permisos del aplicativo.

El adaptador usa conexiones cortas por solicitud, TLS y `prepare_threshold=None`, compatible con el pooler en modo transacción. No ejecuta migraciones al atender solicitudes. El DSN debe pertenecer a una cuenta del backend autorizada para el esquema, no a un usuario anónimo de Supabase.

## 3. Preparar Vercel

1. En https://vercel.com/new importa el repositorio SIDOC-OCI de GitHub con el código de esta versión. Si el cambio sigue en una rama de trabajo, selecciónala para el primer despliegue o intégrala en `main` antes de importar.
2. Usa la raíz del repositorio y el preset **Flask**. `pyproject.toml` selecciona `wsgi:app` y Python 3.12; `vercel.json` configura la función y el build. El build copia los assets estáticos al CDN; no toca datos ni secretos.
3. En **Settings → Environment Variables** configura como valores privados:

| Variable | Valor |
|---|---|
| `SIDOC_ENV` | `production` |
| `DATABASE_URL` | Cadena del Transaction pooler de Supabase |
| `SUPABASE_URL` | URL HTTPS del proyecto |
| `SUPABASE_SERVICE_ROLE_KEY` | Clave backend `service_role` |
| `SUPABASE_STORAGE_BUCKET` | `sidoc-documents` |
| `SECRET_KEY` | Secreto aleatorio de al menos 32 caracteres |
| `BOOTSTRAP_TOKEN` | Otro secreto aleatorio de al menos 32 caracteres |
| `ALLOWED_HOSTS` | Dominio de producción, sin https://; separar varios con comas |

Puedes generar los dos secretos por separado con tu gestor de contraseñas. No compartas esos valores por chat. Vercel proporciona también sus hostnames de preview/producción; el código los reconoce. Si añades un dominio propio, inclúyelo en `ALLOWED_HOSTS` y vuelve a desplegar.

4. Usa proyectos de Supabase separados para producción y previews modificables, o desactiva previews públicas: no apuntes una rama de pruebas a documentos reales sin control. Activa Deployment Protection para limitar el acceso durante la validación; no cambies la audiencia a pública solo para facilitar una prueba.
5. Despliega y revisa el build. Una vez asignado el dominio, verifica `/healthz` (HTTP 200); ese endpoint comprueba que la base y la tabla de usuarios sean accesibles, sin exponer datos ni secretos.
6. Si corriges variables, vuelve a desplegar para que el nuevo entorno las utilice.

## 4. Activar al administrador

1. Abre `https://TU-DOMINIO/login` y pulsa **Primera vez: crear cuenta de administrador**.
2. En el formulario indica el `BOOTSTRAP_TOKEN`, tu usuario/correo y una contraseña de al menos 12 caracteres.
3. Inicia sesión y crea las cuentas del personal desde **Usuarios y permisos**.
4. El formulario inicial deja de estar disponible en cuanto existe una cuenta. No hay contraseñas predeterminadas ni usuarios de demostración en producción.

El token no se envía en una URL ni se escribe en el código. Las sesiones usan cookies Secure/HttpOnly/SameSite; cambiar la contraseña o desactivar una cuenta invalida las otras sesiones de esa cuenta.

## PDF de hasta 10 MB

Vercel limita las solicitudes/respuestas de una función a 4,5 MB. Para respetar ese límite:

1. El navegador envía solo metadatos y CSRF a `/api/uploads/start`.
2. El backend comprueba permisos y emite una URL firmada para un nombre aleatorio específico en Supabase.
3. El navegador envía el PDF directamente a Supabase Storage, sin pasar los bytes por la solicitud de Vercel.
4. `/api/uploads/complete` verifica propietario, vencimiento, tamaño, cabecera/cierre de PDF y registra el documento una sola vez. Los archivos sin validar no aparecen en el acervo.
5. La descarga comprueba permisos en el servidor y redirige a un enlace firmado de 60 segundos.

El formulario necesita JavaScript para la carga en nube. No expone la clave `service_role`. La validación de cabecera/cierre no sustituye un antivirus ni un analizador PDF completo.

## Comprobación antes de usar documentos reales

Crear administrador y personal; cargar PDF pequeño y mayor de 4,5 MB; comprobar listado, filtros, favoritos, descarga y revisión/archivo. Comprobar que el personal no accede a documentos ajenos, cuentas, préstamos ni configuración. Cambiar contraseña y comprobar revocación de otra sesión. Volver a desplegar y comprobar que cuentas y PDF persisten. Revisar copias/restauración y políticas institucionales de acceso.

En Configuración existe una acción administrativa para limpiar cargas incompletas y eliminaciones pendientes. Los archivos de cargas inconclusas solo se limpian cuando su URL de subida ya no puede seguir utilizándose. Las eliminaciones fallidas se conservan en una cola persistente para reintento. No hay tarea periódica de mantenimiento configurada todavía.

Google OAuth está implementado y pendiente de configurar según [GOOGLE-OAUTH.md](GOOGLE-OAUTH.md). La recuperación automática por correo sigue pendiente; el administrador puede restablecer contraseñas desde la aplicación. La fotografía adjunta de Chachapoyas/Kuélap ya forma parte del login; los iconos originales de Figma pendientes usan etiquetas accesibles.

## Documentación oficial consultada

- Flask en Vercel: https://vercel.com/docs/frameworks/backend/flask
- Límites de funciones: https://vercel.com/docs/functions/limitations
- Conexión y pooler: https://supabase.com/docs/guides/database/connecting-to-postgres
- URLs de carga firmadas: https://supabase.com/docs/reference/python/storage-from-createsigneduploadurl
