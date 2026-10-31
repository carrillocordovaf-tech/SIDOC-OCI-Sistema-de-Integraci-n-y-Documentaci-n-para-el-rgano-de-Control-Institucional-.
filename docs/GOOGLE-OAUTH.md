# Acceso con Google en SIDOC-OCI

## Estado y alcance

El módulo implementa OAuth 2.0/OpenID Connect con Authlib y Google. La activación real está pendiente de crear el cliente en Google Cloud, configurar las variables privadas de Vercel y completar las tablas de Supabase. No se crearon credenciales ni se verificó una cuenta real de Google desde este entorno.

La demostración `SIDOC_DEMO=1` sigue siendo un recorrido con perfiles ficticios: no autentica cuentas reales ni se conecta a Google. El botón explica cómo habilitar el aplicativo real. No es necesario registrar usuarios reales para mostrar el diseño.

La imagen enviada en `chachapoyas.pgn.rar` se extrajo y verificó como PNG de 567 × 548. Incluye texto y fotografía del diseño, por lo que se conserva intacta en `docs/referencias/chachapoyas-login-referencia.png` como referencia y se incorpora completa en el panel izquierdo de acceso mediante `static/branding/chachapoyas-login.png`, a petición del usuario. Se conservan sus proporciones y no se superpone el mismo texto HTML sobre la imagen. En celular se mantiene el formulario compacto de la maqueta. El botón de Google usa una imagen original de Google descargada de https://www.gstatic.com/images/branding/product/1x/gsa_64dp.png, servida localmente sin modificar sus bytes.

## 1. Preparar la base de datos

En el proyecto de Supabase destinado al aplicativo real:

1. Si aún no creaste las tablas, aplica `supabase/migrations/0001_sidoc.sql`.
2. Aplica una sola vez `supabase/migrations/0002_google_oauth.sql`.
3. Completa el bucket privado y las variables del aplicativo descritas en [VERCEL-SUPABASE.md](VERCEL-SUPABASE.md).

La segunda migración añade `google_email` y `google_sub` al esquema privado `sidoc.users`, con unicidad. No importa usuarios, no cambia roles y no expone tablas. Las migraciones se aplican antes de activar esta versión contra una base existente. En desarrollo local SQLite se actualiza automáticamente sin perder los datos anteriores.

## 2. Crear el cliente de Google

1. Abre https://console.cloud.google.com/ y crea o selecciona un proyecto para **SIDOC-OCI**.
2. En **Google Auth Platform → Branding**, configura el nombre del aplicativo, correo de soporte y contacto del desarrollador.
3. En **Audience**, usa **External / Testing** para probar con cuentas Gmail autorizadas y añade sus correos a **Test users**. La audiencia Internal requiere una organización de Google Workspace adecuada.
4. En **Data Access**, solicita únicamente `openid`, `email` y `profile`.
5. En **Clients → Create client**, selecciona **Web application**.
6. En **Authorized redirect URIs**, registra exactamente:

   `https://TU-DOMINIO-ESTABLE/auth/google/callback`

7. Copia el Client ID y el Client Secret al gestor de secretos o directamente a las variables privadas de Vercel. No los compartas por chat ni los incluyas en Git.

Usa el dominio estable que aparece en **Vercel → Project → Settings → Domains**. La dirección con un identificador diferente en cada despliegue no es conveniente para OAuth. Las rutas y la barra final deben coincidir exactamente con la configuración de Google. Este flujo se inicia mediante redirección desde el servidor.

## 3. Configurar Vercel

Añade estas variables al entorno de producción:

| Variable | Valor |
|---|---|
| `GOOGLE_CLIENT_ID` | Client ID de la aplicación web de Google |
| `GOOGLE_CLIENT_SECRET` | Client Secret privado de ese cliente |
| `GOOGLE_REDIRECT_URI` | La misma URL exacta registrada en Google, terminada en `/auth/google/callback` |
| `GOOGLE_WORKSPACE_DOMAIN` | Opcional: dominio Workspace permitido, por ejemplo `regionamazonas.gob.pe`; dejar vacío para probar con Gmail autorizado |

Mantén las demás variables privadas del aplicativo (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SECRET_KEY`, `BOOTSTRAP_TOKEN`). Para el aplicativo real elimina `SIDOC_DEMO` o cambia su valor a `0`. Vuelve a desplegar después de modificar las variables.

Si faltan credenciales de Google o la URI de retorno no es válida, el acceso por contraseña continúa disponible y el botón de Google muestra el aviso de configuración pendiente. No se simula un acceso exitoso. El flujo real requiere un dominio HTTPS; para pruebas locales se admite HTTP únicamente en loopback.

## 4. Autorizar personas y asignar permisos

1. Crea el primer administrador mediante el formulario protegido de activación y su `BOOTSTRAP_TOKEN`.
2. Inicia sesión con usuario y contraseña.
3. En **Usuarios y permisos**, crea o edita la cuenta correspondiente.
4. En **Correo autorizado para Google**, indica el correo exacto que esa persona usará en Google y guarda los cambios. Puedes autorizar tu propia cuenta de administrador desde esta misma pantalla.
5. Cierra sesión y pulsa **Continuar con Google** en el acceso institucional.

Una cuenta Google no registrada por el administrador se rechaza. Nunca se crea una cuenta automáticamente ni se otorga el rol administrador por iniciar sesión con Google. Los permisos del usuario son los de su cuenta SIDOC-OCI.

El primer acceso vincula el identificador estable de Google (`sub`) a la cuenta autorizada. Si el mismo correo aparece después con otro identificador de Google, el acceso se rechaza para evitar reasignaciones de identidad. Cambiar o borrar el correo autorizado desvincula Google y revoca las otras sesiones de esa cuenta. Desactivar la cuenta también bloquea el acceso.

Si configuras `GOOGLE_WORKSPACE_DOMAIN`, se comprueba el atributo verificado `hd` de Google; no basta con que un correo termine en ese dominio. El administrador debe seguir autorizando cada correo individualmente.

## Seguridad y pruebas

- Authlib valida `state`, PKCE S256, firma RS256, emisor, audiencia, expiración y `nonce` del ID token.
- Se exige un correo verificado y un flujo iniciado en ese navegador hace menos de diez minutos.
- El inicio se lleva al dominio canónico antes de generar el estado de OAuth, para conservar la cookie de retorno.
- Los tokens de Google no se guardan en la base de datos ni en las cookies de la aplicación. La sesión conserva solo la referencia al usuario, la versión de autorización y la protección CSRF.
- No se solicitan permisos de Drive, Gmail ni lectura de documentos.
- Las pruebas usan tokens RSA firmados y endpoints de Google simulados. Comprueban firmas inválidas, nonce/state incorrectos, emisor/audiencia/expiración, correo no verificado, cuentas desconocidas/desactivadas, roles y revocación.

La última comprobación debe realizarse con las credenciales y cuentas de prueba reales en el dominio desplegado. Todavía no se ha realizado esa comprobación externa.

## Documentación oficial

- Google OpenID Connect: https://developers.google.com/identity/openid-connect/openid-connect
- Identidad y marca de Google: https://developers.google.com/identity/branding-guidelines
- Authlib: https://docs.authlib.org/

## Apariencia

La pantalla de acceso utiliza la imagen original aportada por el usuario en el panel izquierdo de escritorio, sin deformarla ni duplicar su texto. El formulario conserva su adaptación para celular. El botón superior muestra Modo oscuro/Modo claro (Oscuro/Claro en celular), cambia el tema y conserva la preferencia al recargar el navegador.
