# SIDOC-OCI: problemática y solución implementada

## Problema que motiva el sistema

Según la descripción proporcionada por el usuario, el OCI del Gobierno Regional Amazonas gestiona documentos y expedientes de forma principalmente manual y dispersa. La búsqueda de originales, el seguimiento de solicitudes y el archivo generan demoras, copias repetidas y riesgo de pérdida de trazabilidad. Los requerimientos tienen plazos operativos de 1 a 3 días según su urgencia. También existe documentación física histórica que debe inventariarse y digitalizarse.

Esta descripción constituye el planteamiento del proyecto, no una medición independiente de los tiempos actuales del OCI.

## Solución y trazabilidad de requisitos

| Necesidad | Solución implementada | Dónde se usa |
|---|---|---|
| Localizar solicitudes rápidamente | Búsqueda por código, asunto y solicitante; filtro por estado | Requerimientos y plazos |
| Controlar plazos de 1 a 3 días | Recepción en horario de Lima, 24/48/72 horas calendario y vencimiento calculado | Registro de requerimiento |
| Detectar retrasos | Indicadores Vencido, Vence en 24 h y En plazo; atención dentro/fuera de plazo | Bandeja de seguimiento |
| Saber quién debe atender | Responsable activo asignado por administrador; derivación con motivo, sin reiniciar el plazo | Detalle de requerimiento |
| Mantener trazabilidad | Historial cronológico de registro, derivación, atención y archivo; control de versión contra actualizaciones simultáneas | Detalle de requerimiento |
| Registrar atención verificable | Nota obligatoria y PDF de respuesta opcional; fecha del servidor | Actualizar trámite |
| Centralizar originales históricos | Código único, número original, años inicial/final, tipo, oficina y conservación | Inventario físico |
| Ubicar el original en papel | Sede, ambiente, estante, nivel, caja y carpeta, con historial de cambios | Detalle de inventario |
| Digitalizar por etapas | Pendiente, En proceso, Digitalizado parcial, Digitalizado y Revisado | Detalle de inventario |
| Evitar copias repetidas | Código único de requerimiento/inventario y hash SHA-256 para nuevas cargas idénticas de una misma cuenta | Registro y carga PDF |
| Conservar evidencia | PDF vinculados a inventario o requerimiento no pueden eliminarse por la acción habitual de borrado | Gestión documental |
| Evaluar tiempos | Promedio de horas hasta registrar atención y exportación CSV del ámbito autorizado | Requerimientos |
| Acceso seguro | Administrador con alcance global; personal ve requerimientos asignados, inventario bajo su custodia y sus PDF | Servidor Flask |

## Uso de requerimientos

1. El administrador registra el código original, asunto, solicitante, responsable, fecha de recepción y plazo. Puede asociar un expediente y un documento de origen.
2. El responsable encuentra la solicitud en su bandeja y la pasa de Registrado a En trámite, dejando una nota.
3. Si se necesita otro responsable, el administrador deriva indicando el motivo. No modifica el vencimiento original.
4. Al responder, el responsable registra una descripción y puede asociar un PDF de su ámbito. El estado cambia a Atendido y se registra la hora del servidor.
5. El administrador verifica y cambia de Atendido a Archivado. La atención tardía continúa marcada fuera de plazo incluso después del archivo.

El personal no administra usuarios, no deriva a otros responsables y no archiva requerimientos. Una reasignación retira el acceso del responsable anterior. Las referencias a documentos no conceden permisos adicionales sobre sus PDF.

## Uso del inventario físico

1. El administrador registra ubicaciones identificadas con códigos únicos.
2. Registra el original aunque no exista un PDF: documento o expediente, años, oficina, tipo, responsable, ubicación y folios opcionales.
3. El personal puede cargar sus PDF mediante Gestión documental; el administrador vincula cada tomo/anexo al original correspondiente.
4. El administrador actualiza el estado de digitalización y deja una nota de verificación. Para Digitalizado parcial, Digitalizado o Revisado debe existir al menos un PDF vinculado.
5. Cada cambio de ubicación y digitalización queda en el historial del original, además de la actividad general.

Los cambios de inventario son administrativos. El personal consulta los originales bajo su custodia y descarga únicamente los PDF que ya tiene autorizados por propiedad. No se necesita escanear todo el archivo antes de empezar.

## Alcances que deben entenderse correctamente

- Se usan **días calendario completos desde la hora de recepción**, no días hábiles, feriados ni fecha de cierre de oficina. Es una regla operativa basada en el requerimiento del usuario, pendiente de confirmación institucional; no se presenta como plazo legal.
- Los avisos se calculan al abrir o recargar la bandeja; no se han programado correos, SMS o notificaciones externas.
- Atendido mide el registro de atención en el sistema. No certifica automáticamente el envío o recepción externa de una respuesta.
- La búsqueda usa metadatos. No se ha incorporado OCR ni búsqueda dentro del texto de los PDF escaneados.
- La comprobación de duplicados compara bytes exactos de nuevas cargas de una misma cuenta. No detecta escaneos visualmente iguales con bytes distintos ni PDF históricos cargados antes de calcular hashes. No cruza cuentas para evitar revelar documentos ajenos.
- Un estado Revisado requiere verificación humana de integridad, legibilidad y folios; el sistema no certifica solo la digitalización.
- La finalidad de encontrar/tramitar en pocos minutos es un objetivo a evaluar con usuarios y volumen real, no un rendimiento garantizado por la implementación.

## Evaluación sugerida para la sustentación

Medir antes y después los mismos casos de búsqueda y seguimiento, con un conjunto representativo de expedientes y participantes. Registrar tiempos de localización, solicitudes respondidas dentro del plazo, expedientes localizados correctamente y duplicados identificados. Comparar medianas y porcentajes, sin afirmar mejoras cuantitativas antes del piloto. El promedio de horas de atención del módulo es un indicador adicional, no reemplaza el estudio de búsqueda.

## Instalación de esta actualización

Las tablas iniciales y el inventario ya se crearon en Supabase según los resultados compartidos por el usuario. **No repetir 0001, 0002, 0003 ni CREAR-TABLAS-SIDOC.sql en ese proyecto.**

1. Respaldar la base según el procedimiento institucional.
2. Ejecutar una sola vez `supabase/migrations/0004_tramite_oci.sql` en el SQL Editor. Añade requerimientos, sus eventos, historial del inventario, códigos normalizados únicos y hash de nuevos PDF.
3. Integrar el cambio del aplicativo y desplegarlo en Vercel. No requiere nuevas variables, contraseñas ni servicios externos.
4. Comprobar acceso con administrador y personal, crear un requerimiento de prueba, registrar atención, inventariar un original y vincular un PDF no sensible.

Si la migración detecta códigos históricos que se repiten al ignorar espacios o mayúsculas, la transacción se cancela: revisar esos códigos antes de repetir. No eliminar registros reales para resolverlo sin revisión del responsable.

En instalaciones locales de desarrollo, las migraciones son aditivas y automáticas. En producción son explícitas: las rutas nuevas muestran instrucciones de actualización (HTTP 503) si falta el esquema; los módulos anteriores continúan disponibles. Las instalaciones nuevas deben ejecutar 0001, 0002, 0003 y 0004 en orden.

## Validación de esta versión

- 70 pruebas aprobadas, incluidas SQLite, carga de nube con almacenamiento simulado y PostgreSQL real local con las cuatro migraciones.
- Se comprobaron plazos, vencidos y próximas 24 horas, derivación sin reiniciar plazo, alcance por usuario, respuestas, bloqueo de archivo por personal, formularios obsoletos, búsqueda histórica, cambio de ubicación, PDF vinculados y duplicados de nueva carga.
- Navegador Chromium: bandeja, detalle, inventario y detalle del original en escritorio y celular, modo oscuro y transición de trámite. Sin desbordamiento horizontal de la página ni errores JavaScript. Las tablas anchas se desplazan dentro de su contenedor.
- Construcción de recursos estáticos para Vercel y compilación Python verificadas. No se probó esta actualización con los documentos reales ni se aplicó 0004 en Supabase de producción.

Capturas: `docs/previews/requerimientos-escritorio.png`, `requerimientos-celular.png`, `inventario-escritorio.png` e `inventario-celular.png`. UML actualizado en `docs/uml/`, incluido el seguimiento de requerimientos.
