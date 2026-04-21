# Supabase Migrations

All database schema changes live here and are applied through the
[Supabase CLI](https://supabase.com/docs/guides/cli). Files are named with the
CLI's required `YYYYMMDDHHMMSS_<description>.sql` pattern so `supabase db push`
can apply them in order.

## Current migrations

| Order | File | Purpose |
| ----- | ---- | ------- |
| 1 | `20260101000001_add_rate_limiting_table.sql` | API rate-limiting table. |
| 2 | `20260101000002_add_ai_wish_audit_logs_table.sql` | AI wish audit trail. |
| 3 | `20260421000001_create_users_table_and_migrate_admins.sql` | Introduces the `users` table and migrates any rows from the legacy `admins` table. |
| 4 | `20260421000002_add_user_phone_number.sql` | Adds `phone_number` to `users` so the logged-in coordinator can receive SMS/WhatsApp. |
| 5 | `20260421000003_create_user_notification_preferences_table.sql` | Extracts delivery preferences into the dedicated `user_notification_preferences` table and drops the legacy columns from `users`. |

## Running migrations

Migrations are run manually — there is no CI job that applies them
automatically. The project's [`Makefile`](../../Makefile) exposes convenient
targets so you can invoke them from the repo root without remembering CLI
flags. Run `make help` to see the full list.

### Locally

```bash
# One-time: install the CLI (https://supabase.com/docs/guides/cli#installation)
brew install supabase/tap/supabase

# Spin up a local Postgres + apply every migration from scratch
make db-start
make db-reset
```

### Against a remote Supabase project

Export your Supabase credentials, then run the migrate target. It links the
repo to the project (if needed) and pushes every pending migration.

```bash
export SUPABASE_ACCESS_TOKEN=...   # https://supabase.com/dashboard/account/tokens
export SUPABASE_PROJECT_REF=...    # e.g. abcdwxyz from https://abcdwxyz.supabase.co
export SUPABASE_DB_PASSWORD=...

make db-migrate
```

If you already have a direct Postgres connection string, set `SUPABASE_DB_URL`
instead and `make db-migrate` will use it directly (no link step needed).

## Adding a migration

```bash
make db-new NAME=add_foo_table
# edit the generated file in supabase/migrations/
make db-reset        # verify locally
git add supabase/migrations/*_add_foo_table.sql
```

When you're ready to apply it to production, run `make db-migrate`.
