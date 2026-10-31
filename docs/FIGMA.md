# Inventario de Figma y estado de implementación

Fuente: https://www.figma.com/design/jY7TaQv24KflsnOkPjfJDL
Revisión: 31 de octubre de 2026. Se consultaron todas las páginas mediante metadatos y las cinco pantallas con get_design_context y sus capturas. El archivo tiene una página, `Page 1` (`0:1`).

| Pantalla | Nodo | Tamaño | Implementación |
|---|---|---|---|
| Acceso institucional · Escritorio | 10:7724 | 1440 × 1000 | /login; estructura de dos columnas, formulario conectado, recursos visuales pendientes |
| Acceso institucional · Celular | 10:7818 | 390 × 957 | /login; cabecera, banda institucional, formulario y pie adaptables |
| Gestión documental · Escritorio claro | 10:7249 | 1440 × 1224 | /; navegación lateral, indicadores, filtros, tabla y seguimiento |
| Gestión documental · Escritorio oscuro | 10:7878 | 1440 × 1224 | /; variables CSS y selector de tema persistente |
| Gestión documental · Celular | 10:7584 | 390 × 1246 | /; tarjetas, filtros, menú desplegable y navegación inferior |

Las cinco pantallas tienen contexto de diseño detallado, no solo metadatos. Se usa Flask/Jinja y CSS local; no React/Tailwind. La tipografía Inter se incluye localmente con su licencia OFL. No se modificó el archivo de Figma.

## Navegación adicional

La maqueta dibuja accesos a Resumen, Expedientes, Archivo central, Préstamos, Reportes, Usuarios y permisos, Configuración y Mi cuenta. No contiene pantallas independientes de estos módulos. Se crearon vistas funcionales con los mismos colores y componentes; esas vistas son una extensión de la interfaz y requieren validación del usuario, no son reproducciones de diseños inexistentes.

Se implementaron carga de PDF con código/tipo/asunto/dependencia/folios/expediente; descarga; revisión y archivo por administrador; favoritos por usuario; búsqueda/filtros/paginación; exportación CSV; expedientes; préstamos/devoluciones; usuarios/permisos/desactivación; cambio de contraseña; configuración institucional y auditoría.

Los números 1.248, 186, 32 y 94,6 % de la maqueta son ilustrativos. La aplicación muestra los valores de la base de datos. La cifra de digitalización indica únicamente documentos registrados con PDF, no porcentaje del archivo físico de la institución. Los folios se declaran manualmente, no se calculan a partir del PDF.

## Bloqueo de recursos visuales

El proxy del entorno devuelve HTTP 403 al descargar `https://www.figma.com/api/mcp/asset/...`. La lectura mediante el conector funciona, pero la descarga de recursos no. Se probó con una URL recién obtenida de contexto de diseño. No se desactivó el proxy ni se eludió la política de red.

`figma-assets.json` conserva la correspondencia de cada recurso original por pantalla; `scripts/download_figma_assets.py` descarga exactamente esos recursos a `static/figma`. Las URLs caducan; si vencen hay que regenerarlas desde Figma. No se utilizan como URLs de imágenes en tiempo de ejecución.

Hasta resolverlo, faltan el escudo, la fotografía de Kuélap y los iconos originales. Se reservan sus espacios sin inventar imágenes o iconos. La vista en desarrollo identifica los controles con texto cuando sus iconos faltan. La reproducción visual exacta y la comprobación de la geometría de cada imagen están PENDIENTES; no se considera validada la fidelidad completa a Figma.

Para desbloquearlos: habilitar la descarga HTTPS de www.figma.com en el entorno de ejecución mediante su configuración de red, o adjuntar los recursos originales exportados desde Figma. La configuración declara red sin restricciones, pero el proxy sigue devolviendo 403; puede requerir revisión de la plataforma. No se puede atribuir ese error a los permisos del archivo Figma sin evidencia adicional.

Al obtener los recursos ejecutar `python scripts/download_figma_assets.py`, comprobar todos los archivos y comparar de nuevo escritorio (1440 px), celular (390 px), tema claro y oscuro. El cambio automático al tema oscuro y los iconos de distintos tamaños deben comprobarse con los SVG originales disponibles.

## Funciones externas pendientes

Google OAuth, recuperación por correo y respaldo automático en nube no están habilitados. Los controles de Google/recuperación explican el estado actual. El panel de almacenamiento dice local; no simula una sincronización o un respaldo que no existen. La fotografía y los textos de patrimonio se mantienen como referencia de la maqueta, incluida su mención de nube, que es una capacidad futura. Consulta SERVICIOS.md antes de habilitar servicios.

## Escudo aportado por el usuario

El usuario compartió la imagen en el chat. No se recibió una ruta o un identificador de descarga para guardarla. Se implementó carga administrativa desde Configuración → Escudo institucional. Ese recurso original aportado por el usuario tendrá prioridad sobre el recurso de Figma en todas las cabeceras y se mostrará sin recorte ni deformación. Falta cargar el archivo; no se utilizó una recreación del escudo.

Actualización: se recibió `escudo.pgn.rar`, con la imagen `escudo.pgn.jpeg` (JPEG de 148 × 196). Se extrajeron y verificaron los bytes originales y se incorporaron como `static/branding/escudo-amazonas.jpg`, sin recorte, recomposición ni cambio de resolución. Es el escudo predeterminado de todas las cabeceras; una carga administrativa posterior conserva su prioridad. La descarga de los demás recursos de Figma sigue pendiente.
