# SIDOC-OCI

Aplicativo local de gestión documental con Flask, SQLite y almacenamiento de PDF en disco. Interfaz adaptable basada en las cinco pantallas del archivo Figma del usuario. Preparado para Vercel + Supabase; despliegue real pendiente de autorizar las cuentas. Consulta [la guía de nube](docs/VERCEL-SUPABASE.md). El escudo original proporcionado por el usuario está incorporado. La reproducción visual completa está pendiente de los demás recursos de Figma cuya descarga bloquea el proxy; consulta [el inventario](docs/FIGMA.md).

## Abrir el aplicativo

Requiere Python 3.12 o posterior.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app app:create_app run --host 127.0.0.1 --port 5000
```

Abre http://127.0.0.1:5000/login en el equipo donde ejecutas el servidor. En un entorno remoto, localhost corresponde al entorno, no a tu computadora; necesitas una vista previa o reenvío de puerto privado del entorno. No se creó una dirección pública.

El administrador también puede cargar el escudo original desde **Configuración → Escudo institucional** (PNG/JPG de hasta 2 MB). Se conserva la imagen original y sus proporciones en las cabeceras de escritorio y celular.

Si aún no existen cuentas, pulsa **Primera vez: crear cuenta de administrador**, elige tu usuario/correo y una contraseña de al menos 12 caracteres. El formulario inicial desaparece al crear la primera cuenta. No hay contraseñas predeterminadas. Solo iniciar en un entorno local controlado mientras esté disponible la configuración inicial.

También puedes crear un administrador desde la terminal:

```sh
.venv/bin/flask --app app:create_app create-admin administrador
```

La contraseña se solicita de forma oculta con confirmación. Una cuenta puede usar un correo o un nombre de usuario; el rótulo de correo en el inicio corresponde a Figma. No se comprueba pertenencia a Google ni se envían correos. Para detener el servidor: Ctrl+C.

## Funciones y permisos

| Función | Administrador | Personal |
|---|---|---|
| Cargar PDF hasta 10 MB | Sí | Sí |
| Consultar, buscar, descargar, exportar | Todos los documentos | Sus propios documentos |
| Favoritos | Por cuenta | Por cuenta |
| Editar metadatos, revisar, archivar y eliminar | Sí | No |
| Crear expedientes y registrar préstamos/devoluciones | Sí | No |
| Crear cuentas, cambiar permisos, restablecer contraseña, desactivar | Sí | No |
| Configuración institucional | Sí | No |
| Cambiar su contraseña y tema | Sí | Sí |
| Consultar auditoría | Toda | Sus operaciones |

Los expedientes están asociados a un responsable. La consulta del personal se limita a los expedientes que tiene asignados. Un documento con historial de préstamos se conserva; su eliminación se bloquea para preservar la trazabilidad. El personal no modifica el código fuente, la configuración ni los permisos del aplicativo.

## Datos y seguridad local

La base de datos se crea y migra automáticamente conservando las cuentas/documentos anteriores. Se almacenan datos en `instance/sidoc.sqlite`, PDF con nombres aleatorios en `instance/pdfs` y la clave de sesión en `instance/session.key`. La carpeta `instance` está excluida de Git. Respalda la carpeta completa con el servidor detenido y mantén sus permisos restringidos.

Contraseñas mediante scrypt; protección CSRF; sesiones HTTP-only y SameSite=Lax con duración de 8 horas; límite de 10 fallos de acceso por IP en 15 minutos; permisos comprobados en el servidor; desactivación que invalida el acceso de sesiones existentes; auditoría de operaciones. Las fechas de auditoría están en UTC y la fecha de la cabecera en America/Lima. Recordar usuario conserva únicamente el nombre en el navegador, nunca la contraseña.

Validación básica de PDF: extensión, cabecera, marcador final y límite de tamaño. No sustituye un analizador PDF ni un antivirus. Descargas como adjuntos. Los folios son declarados por el usuario. La exportación CSV neutraliza fórmulas comunes de hojas de cálculo.

## Verificación

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Se comprueban autenticación, CSRF, aislamiento entre usuarios, roles, PDF, búsqueda, favoritos, archivo, expedientes, préstamos/devoluciones, exportación, paginación, bloqueo de acceso, configuración inicial y migración de datos. Las pruebas utilizan bases de datos temporales.

## Figma y servicios pendientes

- [Inventario de las cinco pantallas y bloqueo de recursos](docs/FIGMA.md).
- [Pasos para Google, correo y respaldos](docs/SERVICIOS.md).

La navegación hacia módulos sin pantallas propias se implementó siguiendo el estilo general y requiere revisión del usuario. Google OAuth, recuperación por correo y respaldos automáticos no están habilitados; la interfaz explica su estado.

La configuración para Vercel incluye HTTPS, cookies Secure y cabeceras de seguridad. Antes de usar documentos reales falta comprobar el despliegue con Supabase, configurar respaldo/restauración, análisis de PDF y revisar los permisos institucionales. El cambio o restablecimiento de contraseña, la desactivación y los cambios de permisos revocan las sesiones anteriores de esa cuenta. No usar datos sensibles reales mientras no se complete esa preparación. No se ha elegido alojamiento ni contratado servicios.

## Nube: Vercel + Supabase

[Instrucciones de despliegue, variables y activación del administrador](docs/VERCEL-SUPABASE.md). `wsgi.py` es el punto de entrada; `supabase/migrations/0001_sidoc.sql` contiene el esquema PostgreSQL privado y `supabase/storage.sql` el bucket privado. La carga directa conserva el límite de PDF de 10 MB sin pasar archivos grandes por Vercel. La versión local sigue usando SQLite y disco sin servicios externos.
