-- Apply after 0001_sidoc.sql. Administrator-authorized Google identities only.
BEGIN;
ALTER TABLE sidoc.users ADD COLUMN google_email TEXT;
ALTER TABLE sidoc.users ADD COLUMN google_sub TEXT;
CREATE UNIQUE INDEX users_google_email ON sidoc.users(google_email) WHERE google_email IS NOT NULL;
CREATE UNIQUE INDEX users_google_sub ON sidoc.users(google_sub) WHERE google_sub IS NOT NULL;
COMMIT;
