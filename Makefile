# Convenience commands for operating the Supabase database.
# Run `make help` to see what's available.

.PHONY: help db-start db-stop db-status db-reset db-link db-push db-migrate db-new db-diff db-list test

help:
	@echo "Database (Supabase CLI) commands:"
	@echo "  make db-start            Start the local Supabase stack"
	@echo "  make db-stop             Stop the local Supabase stack"
	@echo "  make db-status           Show local stack status"
	@echo "  make db-reset            Re-apply every migration on the local stack"
	@echo "  make db-link             Link repo to remote project (uses \$$SUPABASE_PROJECT_REF)"
	@echo "  make db-push             Push migrations to the linked remote project"
	@echo "  make db-migrate          Link + push using SUPABASE_* env vars (scripts/migrate.sh)"
	@echo "  make db-new NAME=...     Create a new empty migration file"
	@echo "  make db-diff NAME=...    Generate a migration from local schema changes"
	@echo "  make db-list             Show local vs remote migration status"
	@echo ""
	@echo "Other:"
	@echo "  make test                Run the pytest suite"

db-start:
	supabase start

db-stop:
	supabase stop

db-status:
	supabase status

db-reset:
	supabase db reset

db-link:
	@if [ -z "$(SUPABASE_PROJECT_REF)" ]; then \
		echo "ERROR: SUPABASE_PROJECT_REF is not set"; exit 1; \
	fi
	supabase link --project-ref "$(SUPABASE_PROJECT_REF)"

db-push:
	supabase db push --include-all

db-migrate:
	./scripts/migrate.sh

db-new:
	@if [ -z "$(NAME)" ]; then echo "Usage: make db-new NAME=<description>"; exit 1; fi
	supabase migration new $(NAME)

db-diff:
	@if [ -z "$(NAME)" ]; then echo "Usage: make db-diff NAME=<description>"; exit 1; fi
	supabase db diff --file $(NAME)

db-list:
	supabase migration list

test:
	./.venv/bin/pytest -q
