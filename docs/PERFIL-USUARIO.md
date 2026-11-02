# Perfil superior de usuario

El usuario se presenta en el encabezado superior derecho, en computadora y celular. Al pulsar el avatar se abre Datos del usuario con Nombre, Rol y Entidad. La entidad mostrada es Órgano de Control Institucional. El botón contiguo con una flecha permite cerrar la sesión mediante POST protegido con CSRF.

El perfil anterior del pie del menú se retira. El panel se cierra al pulsar fuera o presionar Escape, y respeta el tamaño de pantalla, incluido el teléfono en horizontal. Mi cuenta conserva el cambio de contraseña y añade la edición del nombre completo. El administrador también puede indicar nombres al crear/editar cuentas en Usuarios y permisos.

## Activación en Supabase

Aplicar una sola vez `supabase/migrations/0005_user_display_name.sql`, después de 0004. Añade únicamente `sidoc.users.display_name`, con valor inicial vacío y límite de 160 caracteres. No modifica cuentas, contraseñas, correos autorizados ni roles. No repetir la instalación inicial.

Antes de aplicar 0005, el aplicativo continúa funcionando: muestra el usuario/correo y oculta los campos de edición de nombre. Mi cuenta indica qué actualización falta. La detección de la columna se realiza al abrir los formularios; después de aplicar SQL no hacen falta nuevas variables.

Una vez aplicada la migración, ingresar en Mi cuenta → Datos del usuario → Nombre completo → Guardar nombre. En Google, el próximo ingreso autorizado copia el nombre del perfil solo si el nombre local sigue vacío. Los nombres elegidos por el usuario o administrador no se sobrescriben. El nombre es solo presentación; los permisos siguen basándose en el identificador interno y rol.

## Validación

74 pruebas aprobadas, incluidas pruebas con PostgreSQL local real. Se verificaron persistencia de nombres, edición personal limitada a su propia cuenta, rechazo de nombres largos y falta de CSRF, compatibilidad sin la nueva columna y captura de nombre desde un ID token de Google válido sin sobrescribir el nombre elegido.

Chromium local a 1440, 900, 390, 320 y 740 píxeles: nombre, rol y entidad, posición del panel, menú móvil, modo oscuro, Escape y cierre de sesión real. Capturas con datos ficticios en docs/previews.
