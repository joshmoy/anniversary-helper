-- Secure Supabase Storage Setup for CSV Files
-- Run these commands in your Supabase SQL Editor

-- 1. Create/Update the storage bucket as PRIVATE
INSERT INTO storage.buckets (id, name, public)
VALUES ('anniversary-helper', 'anniversary-helper', false)
ON CONFLICT (id) DO UPDATE SET public = false;

-- 2. Remove any existing permissive policies
DROP POLICY IF EXISTS "Public read access" ON storage.objects;
DROP POLICY IF EXISTS "Allow all operations" ON storage.objects;

-- 3. Allow service role to upload files (for your API)
CREATE POLICY "Service role upload" ON storage.objects 
FOR INSERT 
WITH CHECK (bucket_id = 'anniversary-helper' AND auth.role() = 'service_role');

-- 4. Allow service role to read files (for processing)
CREATE POLICY "Service role read" ON storage.objects 
FOR SELECT 
USING (bucket_id = 'anniversary-helper' AND auth.role() = 'service_role');

-- 5. Allow service role to delete files (for cleanup)
CREATE POLICY "Service role delete" ON storage.objects 
FOR DELETE 
USING (bucket_id = 'anniversary-helper' AND auth.role() = 'service_role');

-- 6. Allow service role to update files (if needed)
CREATE POLICY "Service role update" ON storage.objects 
FOR UPDATE 
USING (bucket_id = 'anniversary-helper' AND auth.role() = 'service_role');

-- 7. Ensure storage_path column exists
ALTER TABLE csv_uploads 
ADD COLUMN IF NOT EXISTS storage_path TEXT;
