-- Private bucket; no anonymous/authenticated browser read/write policies.
-- Uploads use per-object signed tokens from the authenticated Flask server.
INSERT INTO storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
VALUES ('sidoc-documents','sidoc-documents',false,10485760,
        ARRAY['application/pdf','image/png','image/jpeg'])
ON CONFLICT(id) DO UPDATE SET public=false, file_size_limit=10485760,
 allowed_mime_types=ARRAY['application/pdf','image/png','image/jpeg'];
