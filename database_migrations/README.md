# Database Migrations

This directory contains SQL migration scripts for the Church Anniversary & Birthday Helper database.

## How to Apply Migrations

### For Supabase (Recommended)

1. Go to your Supabase project dashboard
2. Navigate to the SQL Editor
3. Copy and paste the contents of each migration file
4. Execute the SQL script

### Migration Files

- `001_add_rate_limiting_table.sql` - Creates the rate_limiting table for API rate limiting functionality
- `002_add_ai_wish_audit_logs_table.sql` - Creates the ai_wish_audit_logs table for AI wish generation audit trail

## Migration Order

Always apply migrations in numerical order (001, 002, etc.) to ensure proper database schema evolution.

## Backup Recommendation

Before applying any migration, it's recommended to:

1. Create a backup of your database
2. Test the migration on a development environment first
3. Apply to production during low-traffic periods
