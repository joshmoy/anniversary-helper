-- Migration: Create users table and migrate legacy admins
-- Description: Introduces a proper users table with email, username, account_type, and role.
-- The legacy `admins` table is deprecated; every account is modelled as a user going forward.

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    account_type VARCHAR(50) NOT NULL DEFAULT 'personal',
    role VARCHAR(20) NOT NULL DEFAULT 'member',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_account_type ON users(account_type);

-- Backfill existing admins into users as admin-role accounts if the legacy
-- `admins` table is still present.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'admins'
    ) THEN
        INSERT INTO users (
            username,
            email,
            full_name,
            password_hash,
            account_type,
            role,
            is_active,
            created_at,
            updated_at,
            last_login
        )
        SELECT
            a.username,
            CASE
                WHEN a.username LIKE '%@%' THEN a.username
                ELSE NULL
            END AS email,
            a.username AS full_name,
            a.password_hash,
            'organization' AS account_type,
            'admin' AS role,
            a.is_active,
            a.created_at,
            a.updated_at,
            a.last_login
        FROM admins a
        WHERE NOT EXISTS (
            SELECT 1
            FROM users u
            WHERE u.username = a.username
        );
    END IF;
END
$$;

COMMENT ON TABLE users IS 'Application users with authentication identity and authorization role';
COMMENT ON COLUMN users.username IS 'Unique username used for login and display';
COMMENT ON COLUMN users.email IS 'Unique email address used for login and notifications';
COMMENT ON COLUMN users.full_name IS 'User full name';
COMMENT ON COLUMN users.account_type IS 'Business classification such as personal or organization';
COMMENT ON COLUMN users.role IS 'Authorization role such as member or admin';
