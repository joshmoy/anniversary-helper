-- Admin Table Setup for Church Anniversary & Birthday Helper
-- Run this command in your Supabase SQL Editor

-- Create the admins table
CREATE TABLE IF NOT EXISTS admins (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE
);

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_admins_username ON admins(username);

-- Insert default admin user (only if it doesn't exist)
-- Username: fgAdmin
-- Password: @FGAnniversary25
INSERT INTO admins (username, password_hash, is_active)
SELECT 'fgAdmin', '$2b$12$lCZMcYNCSkgznWPxEtzUZ.37e/Zsiz9chejdGmWQjtTFNJzzFJAdC', TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM admins WHERE username = 'fgAdmin'
);

-- Add updated_at trigger (optional - for automatic timestamp updates)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_admins_updated_at BEFORE UPDATE
    ON admins FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
