# Verificación local

31 de octubre de 2026. No se publicó, desplegó ni envió código a GitHub.

- 12 pruebas de unittest aprobadas. Incluyen aislamiento documental entre cuentas, bloqueo de rutas administrativas, CSRF, inicio/cierre de sesión, carga/descarga, favoritos, filtros, exportación CSV, paginación, archivo, expedientes asignados, préstamos/devoluciones, cuentas desactivadas, cambio de contraseña, límite de intentos, configuración inicial, migración de la primera base de datos y carga del escudo con preservación de bytes y permiso exclusivo de administrador.
- Chromium con Playwright: apertura de `/`, `/upload`, `/expedients`, `/archive`, `/loans`, `/reports`, `/users`, `/settings` y `/account` a 1440 y 390 px, sin desbordamiento horizontal.
- Navegador: inicio/cierre de sesión, carga de PDF desde formulario, selector de tema, menú móvil, mostrar contraseña y explicación de Google pendiente.
- Servidor de desarrollo real en 127.0.0.1:5000: `/login` respondió HTTP 200.
- Capturas en `docs/previews` de las cinco variantes: acceso escritorio/celular y gestión escritorio claro/oscuro/celular. Muestran datos ficticios de una base temporal separada en `/tmp`; no se insertaron cuentas ni PDF de prueba en la base real del aplicativo.
- Tipografía Inter servida localmente con licencia.

## Pendiente de verificación visual completa

El verificador `python scripts/check_figma_assets.py` detecta 0 de 110 referencias de recursos originales disponibles localmente. Son referencias por variante, con imágenes/iconos repetidos entre pantallas. El proxy responde 403 al descargarlas. Se mantiene esta verificación como PENDIENTE, no como prueba aprobada.

Se compararon las capturas de Figma con la estructura implementada. La fotografía, el escudo y los SVG originales faltan y por tanto sus colores, geometría y colocación final no se pueden validar. Las capturas locales son una vista parcial funcional, no evidencia de reproducción exacta. Hay etiquetas de texto temporales para que los botones afectados por iconos ausentes sigan siendo utilizables.

Google OAuth, recuperación por correo y respaldos automáticos en nube no fueron habilitados ni probados. El diseño visual de los módulos adicionales se deriva del estilo de las cinco pantallas existentes y debe ser revisado con el usuario.

El usuario compartió una imagen del escudo en el chat, pero no está expuesta como archivo ni tiene un identificador de descarga accesible a las herramientas. No se incorporó esa imagen al repositorio. Se añadió Configuración → Escudo institucional para cargar el PNG/JPG original (máximo 2 MB), conservar sus bytes y mostrarlo completo sin deformación. La prueba utiliza una imagen mínima temporal, no el escudo del usuario.

Actualización: se recibió `escudo.pgn.rar`, con la imagen `escudo.pgn.jpeg` (JPEG de 148 × 196). Se extrajeron y verificaron los bytes originales y se incorporaron como `static/branding/escudo-amazonas.jpg`, sin recorte, recomposición ni cambio de resolución. Es el escudo predeterminado de todas las cabeceras; una carga administrativa posterior conserva su prioridad. La descarga de los demás recursos de Figma sigue pendiente.

Comprobación del escudo en Chromium: fuente original de 148 × 196; caja de escritorio de 64 × 52 y de celular de 48 × 40, ambas con object-fit: contain. La copia en el repositorio conserva el mismo SHA-256 que el archivo extraído. Se actualizaron las capturas de acceso de escritorio y celular.

## Preparación Vercel + Supabase

Se ejecutaron 33 pruebas aprobadas: 22 de aplicación/adaptadores con SQLite temporal y 11 contra PostgreSQL 17 real en un contenedor local con TLS. La migración PostgreSQL se aplicó sobre ese contenedor; no se aplicó sobre una cuenta real de Supabase. Se verificó también que el rol anónimo no pueda leer el esquema privado.

Se añadió prueba de PDF de 6 MB mediante reserva, subida y finalización; finalización idempotente; propietarios/vencimiento de tickets; descargas firmadas; eliminación con cola de reintento; revocación de sesiones; configuración de producción; HTTPS; cookies Secure/HttpOnly y token de activación del administrador. El transporte de Supabase Storage se simula en estas pruebas; su conexión real queda pendiente de autorizar el proyecto.

El build de assets de Vercel pasó. Las credenciales de Vercel/Supabase no están configuradas y no existe una URL de despliegue confirmada. El proyecto falla si faltan credenciales en modo nube, en vez de crear datos en disco efímero.

Prueba adicional en Chromium: inicio de sesión, formulario móvil, carga directa de PDF de 6 MB con 1.013 bytes de metadatos enviados al backend, finalización y consulta sobre PostgreSQL real; navegación por expedientes, reportes, usuarios, configuración y cuenta, sin errores de JavaScript/CSP. El destino de Storage se simuló en loopback y no constituye una prueba de conectividad con Supabase real.

## Demostración sin Supabase

Se añadieron seis pruebas aprobadas del modo de demostración. La suite local aprobó 28 pruebas; las 11 pruebas PostgreSQL optativas se omitieron porque el contenedor de QA estaba detenido (su ejecución anterior se conserva arriba). Chromium verificó el recorrido de los nueve módulos principales en administrador, la navegación móvil, el cambio de tema, el bloqueo de pantallas administrativas para personal y los avisos de solo lectura. No se modificaron las cuentas ni el proyecto Supabase del usuario.

## Google OAuth, imagen y tema

Se implementó OpenID Connect con Authlib 1.9.1 y se aplicaron las migraciones 0001 y 0002 a un PostgreSQL 17 de QA. La ejecución completa aprobó 47 pruebas. Ocho pruebas específicas de Google verifican tokens RS256 firmados de prueba, state, nonce, PKCE, emisor/audiencia/expiración, correo verificado, cuentas autorizadas/activas, roles y revocación de vinculación. La verificación local posterior a los cambios visuales aprobó 36 pruebas y omitió las 11 PostgreSQL optativas, previamente aprobadas.

Chromium comprobó el enlace de Google en la pantalla real configurada con credenciales ficticias, la autorización administrativa de correos, el logotipo local y la imagen original de 567 × 548, además de la vista móvil sin desbordamientos. También comprobó el cambio de modo oscuro/claro, su etiqueta y la conservación al recargar. No se probó una cuenta real ni se crearon credenciales de Google. La activación en producción requiere completar la base de datos y las variables privadas.
