-- Aplicar una sola vez después de 0004. Conserva usuarios, roles y accesos Google.
BEGIN;
ALTER TABLE sidoc.users ADD COLUMN display_name TEXT NOT NULL DEFAULT ''
 CHECK(length(display_name)<=160);
COMMIT;
