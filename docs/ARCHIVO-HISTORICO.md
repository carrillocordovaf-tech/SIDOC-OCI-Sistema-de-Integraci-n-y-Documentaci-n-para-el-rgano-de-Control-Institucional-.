# Inventario físico y digitalización del OCI

Migración: `supabase/migrations/0003_archivo_historico.sql`. Ejecutar una sola vez después de 0001 y 0002 en el SQL Editor del proyecto Supabase. No contiene archivos ni registros personales reales. No elimina ni reemplaza documentos existentes.

La migración 0003 prepara la base de datos. La actualización 0004 y `workflow.py` incorporan formularios, búsqueda, vinculación de PDF e historial. Ver `PROBLEMATICA-SOLUCION-OCI.md` para instalación y permisos. El esquema `sidoc` sigue privado, con RLS y sin acceso directo para anon/authenticated. La clasificación Público es un dato descriptivo y no publica el PDF ni sustituye los permisos del aplicativo.

## Tablas

- `document_types`: 14 tipos iniciales editables por futura administración del catálogo. Los ocho primeros proceden de publicaciones verificadas del OCI; los seis administrativos son categorías propuestas para su archivo, que deberá validar el área.
- `physical_locations`: código, sede, ambiente, estante, nivel, caja, carpeta y observaciones. Crear ubicaciones reales antes de registrar originales físicos.
- `archive_items`: inventario de documentos y expedientes físicos, número original, años inicial/final, oficina productora, ubicación, folios, conservación, responsable y estado de digitalización. No exige que exista un PDF. Un expediente puede abarcar varios años.
- `archive_item_documents`: relaciona el inventario con los PDFs existentes en `documents`; admite varios tomos o anexos. Impide borrar un PDF vinculado sin retirar antes su relación de archivo.
- `documents`: conserva la carga actual y añade tipo específico, fecha de emisión, emisor y destinatario opcionales. `created` continúa siendo la fecha de carga, no la fecha del original.

## Ejemplo ficticio de registro

| Campo | Ejemplo |
|---|---|
| Código de inventario | HIST-2018-0001 |
| Clase | Expediente |
| Asunto | Documentación de control de obra |
| Años | 2018–2019 |
| Ubicación | Sede central / Archivo OCI / Estante E02 / Nivel 3 / Caja C018 / Carpeta 04 |
| Conservación | Regular |
| Digitalización | Pendiente |
| Acceso | Interno |

Registrar primero la ubicación y el inventario. Escanear después, cargar los PDFs mediante el aplicativo y vincular sus identificadores con el inventario. Comprobar integridad, legibilidad, orden y folios antes de cambiar a Revisado. El cambio de estado debe realizarlo el flujo de aplicación autorizado: el SQL no inspecciona imágenes ni verifica por sí solo que un escaneo esté completo. Los estados de digitalización son independientes de Pendiente/En revisión/Archivado de la gestión documental actual.

## Fuentes del catálogo

- Hito: https://www.gob.pe/institucion/contraloria/noticias/1219120-contraloria-alerta-sobrecostos-y-deficiencias-en-expediente-tecnico-de-proyecto-vial-en-luya
- Visita: https://www.gob.pe/institucion/contraloria/noticias/1410965-contraloria-identifica-que-obra-de-agua-potable-de-la-peca-no-cumple-con-parametros-de-calidad
- Orientación: https://apps8.contraloria.gob.pe/SPIC/srvDownload/ViewPDF?CRES_CODIGO=2020CSI533100006&TIPOARCHIVO=IS
- Auditoría: https://www.gob.pe/institucion/contraloria/noticias/495968-702-2018-cg-funcionarios-generaron-perjuicio-economico-por-mas-de-200-mil-soles-a-la-gerencia-subregional-bagua-en-amazonas
- Informe del jefe: https://www.gob.pe/institucion/regionamazonas/informes-publicaciones/7020596-informe-servicio-relacionado-n-2-5331-2025-010
- Seguimiento, denuncias y sinceramiento: https://www.gob.pe/institucion/regionamazonas/colecciones/2126-informes-y-recomendaciones-contraloria-oci
