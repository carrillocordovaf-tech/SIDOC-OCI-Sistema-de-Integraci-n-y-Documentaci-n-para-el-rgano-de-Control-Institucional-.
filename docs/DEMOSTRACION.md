# Demostración navegable sin configurar Supabase

Esta opción permite recorrer SIDOC-OCI sin crear tablas, cuentas reales ni buckets. Usa exclusivamente ejemplos incluidos en el código. No abre SQLite, no conecta a PostgreSQL/Supabase y no escribe PDF en el servidor. Es adecuada para revisar pantallas y navegación, no para operar documentos reales.

## Activar en Vercel

1. Importa el repositorio con esta versión del código en la rama que Vercel va a desplegar.
2. Mantén **Application Preset: Flask** y **Root Directory: ./**.
3. Abre **Environment Variables**.
4. Añade **Name: `SIDOC_DEMO`**, **Value: `1`**. No necesita ser un secreto.
5. Pulsa **Deploy**. Cuando termine, pulsa **Visit** para abrir la dirección que Vercel asigne.

No se necesitan `DATABASE_URL`, claves de Supabase, `SECRET_KEY` ni `BOOTSTRAP_TOKEN` para esta demostración. Si el proyecto ya existía, configura la variable en su entorno de despliegue y vuelve a desplegar. No basta con guardar una variable para cambiar un despliegue ya publicado.

## Recorrer

La página principal abre la gestión documental con datos ficticios. La franja amarilla identifica la demostración y permite cambiar entre **Administrador**, **Personal** e **Inicio**.

Desde Inicio también puedes pulsar **Entrar como administrador** o **Entrar como personal**. No se introducen contraseñas. El selector de perfil es una preferencia del recorrido, no una cuenta ni un mecanismo de autenticación real.

Se pueden explorar documentos, filtros, favoritos de ejemplo, expedientes, archivo, préstamos, reportes, usuarios, configuración y cuenta. El tema claro/oscuro y el menú móvil funcionan. El perfil Personal muestra únicamente sus ejemplos y bloquea las pantallas administrativas. La descarga produce un PDF de demostración y la exportación contiene únicamente ejemplos.

Las altas, ediciones, eliminaciones y cargas están deshabilitadas tanto en el navegador como en el servidor. Los formularios muestran un aviso de demostración. No cargues información real en esta versión.

## Después: activar el aplicativo real

Completa las tablas, el bucket privado y las variables de [VERCEL-SUPABASE.md](VERCEL-SUPABASE.md). Luego elimina `SIDOC_DEMO` o cámbiala a `0` y vuelve a desplegar. La versión real exige todas sus credenciales; no cambia silenciosamente a demostración si falta alguna.

Los datos de ejemplo no se migran a Supabase. En el aplicativo real crearás tu administrador mediante el token de activación privado y registrarás tus propios documentos.

## Verificar localmente

```sh
.venv/bin/flask --app demo_app:create_demo_app run --host 127.0.0.1 --port 5003
.venv/bin/python -m unittest discover -s tests -v
```

Se añadieron seis pruebas de demostración: arranque con `VERCEL=1` sin credenciales ni conexiones de base de datos; apertura de módulos; filtros; separación de perfiles; rechazo de escrituras; y acceso sin formularios de contraseña. Se verificó en Chromium la navegación en escritorio/celular, el tema, los permisos y la desactivación de cargas/formularios.
