#!/usr/bin/env bash
# Apply all pending Supabase migrations in ./supabase/migrations to the linked
# project. Intended for CI/CD and local use.
#
# Required environment variables:
#   SUPABASE_ACCESS_TOKEN  - Personal access token from
#                            https://supabase.com/dashboard/account/tokens
#   SUPABASE_PROJECT_REF   - The project ref from your Supabase project URL
#                            (e.g. `abcdwxyz` for https://abcdwxyz.supabase.co)
#   SUPABASE_DB_PASSWORD   - Database password for the project
#
# Optional:
#   SUPABASE_DB_URL        - Direct connection string; if set it is used as-is
#                            via `supabase db push --db-url`.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v supabase >/dev/null 2>&1; then
    echo "ERROR: The Supabase CLI is not installed." >&2
    echo "Install it from https://supabase.com/docs/guides/cli#installation" >&2
    exit 1
fi

if [[ -n "${SUPABASE_DB_URL:-}" ]]; then
    echo ">> Applying migrations via SUPABASE_DB_URL..."
    supabase db push --db-url "$SUPABASE_DB_URL" --include-all
    exit 0
fi

: "${SUPABASE_ACCESS_TOKEN:?SUPABASE_ACCESS_TOKEN must be set}"
: "${SUPABASE_PROJECT_REF:?SUPABASE_PROJECT_REF must be set}"
: "${SUPABASE_DB_PASSWORD:?SUPABASE_DB_PASSWORD must be set}"

echo ">> Linking Supabase project $SUPABASE_PROJECT_REF..."
supabase link \
    --project-ref "$SUPABASE_PROJECT_REF" \
    --password "$SUPABASE_DB_PASSWORD"

echo ">> Pushing migrations..."
supabase db push --include-all --password "$SUPABASE_DB_PASSWORD"
