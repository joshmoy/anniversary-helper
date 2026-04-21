-- Migration: Add owner_user_id tenancy columns
-- Description: Attaches every row of tenant data to the user that owns it so the
-- API can enforce per-user isolation. Backfills existing global rows to the
-- legacy operator account (obodaij+fg@gmail.com) so nothing orphans. Operators
-- can override the backfill target by setting app.backfill_owner_user_id before
-- running the migration, e.g.
--     SET LOCAL app.backfill_owner_user_id = '7';

-- 1. Add nullable owner_user_id on tenant tables (nullable first so backfill
--    can run without a DEFAULT that would silently attribute to the wrong user
--    on any future insert).

ALTER TABLE people
    ADD COLUMN IF NOT EXISTS owner_user_id INTEGER
        REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE message_logs
    ADD COLUMN IF NOT EXISTS owner_user_id INTEGER
        REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE csv_uploads
    ADD COLUMN IF NOT EXISTS owner_user_id INTEGER
        REFERENCES users(id) ON DELETE CASCADE;

-- ai_wish_audit_logs stays nullable: the public /api/anniversary-wish endpoints
-- accept unauthenticated callers whose rows have no owner. Authenticated calls
-- stamp it; unauthenticated calls leave it NULL and those rows are not
-- returned to any user through the authenticated audit-log endpoints.
ALTER TABLE ai_wish_audit_logs
    ADD COLUMN IF NOT EXISTS owner_user_id INTEGER
        REFERENCES users(id) ON DELETE SET NULL;

-- 2. Backfill existing data to the specified owner.

DO $$
DECLARE
    backfill_user_id INTEGER := NULLIF(current_setting('app.backfill_owner_user_id', true), '')::int;
BEGIN
    -- Explicit override wins; otherwise use the documented default operator.
    IF backfill_user_id IS NULL THEN
        SELECT id INTO backfill_user_id
        FROM users
        WHERE email = 'obodaij+fg@gmail.com'
        LIMIT 1;
    END IF;

    -- Fall back to the earliest admin if the documented default isn't present
    -- (useful for dev/staging DBs that were seeded differently).
    IF backfill_user_id IS NULL THEN
        SELECT id INTO backfill_user_id
        FROM users
        WHERE role = 'admin'
        ORDER BY created_at ASC
        LIMIT 1;
    END IF;

    -- Final fallback: the earliest user of any role.
    IF backfill_user_id IS NULL THEN
        SELECT id INTO backfill_user_id
        FROM users
        ORDER BY created_at ASC
        LIMIT 1;
    END IF;

    IF backfill_user_id IS NULL THEN
        RAISE EXCEPTION
            'Cannot backfill owner_user_id: no users in the users table. Create the operator user first, then rerun this migration.';
    END IF;

    UPDATE people       SET owner_user_id = backfill_user_id WHERE owner_user_id IS NULL;
    UPDATE message_logs SET owner_user_id = backfill_user_id WHERE owner_user_id IS NULL;
    UPDATE csv_uploads  SET owner_user_id = backfill_user_id WHERE owner_user_id IS NULL;
    -- ai_wish_audit_logs intentionally not backfilled: historical anonymous
    -- wishes stay NULL and invisible through the per-user API.

    RAISE NOTICE 'Backfilled tenancy rows to user id %', backfill_user_id;
END
$$;

-- 3. Make the column NOT NULL on the tenant tables now that backfill is complete.

ALTER TABLE people       ALTER COLUMN owner_user_id SET NOT NULL;
ALTER TABLE message_logs ALTER COLUMN owner_user_id SET NOT NULL;
ALTER TABLE csv_uploads  ALTER COLUMN owner_user_id SET NOT NULL;

-- 4. Supporting indexes for the per-user access patterns.

CREATE INDEX IF NOT EXISTS idx_people_owner_user_id
    ON people(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_people_owner_user_event_date
    ON people(owner_user_id, event_date);

CREATE INDEX IF NOT EXISTS idx_message_logs_owner_user_id
    ON message_logs(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_message_logs_owner_user_sent_date
    ON message_logs(owner_user_id, sent_date);

CREATE INDEX IF NOT EXISTS idx_csv_uploads_owner_user_id
    ON csv_uploads(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_owner_user_id
    ON ai_wish_audit_logs(owner_user_id);

-- 5. De-duplicate legacy active rows so the partial unique index below can be
--    created. Before tenancy existed, nothing prevented the same person from
--    being entered twice (e.g. via repeated CSV uploads), so historical data
--    contains duplicate active (owner_user_id, name, event_type) triples.
--    We keep the freshest row (greatest updated_at, then greatest id) active
--    and soft-delete the older copies by flipping ``active = FALSE``; history
--    is preserved in case someone wants to audit what was there.

DO $$
DECLARE
    deactivated INTEGER;
BEGIN
    WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY owner_user_id, name, event_type
                   ORDER BY updated_at DESC NULLS LAST, id DESC
               ) AS rn
        FROM people
        WHERE active = TRUE
    )
    UPDATE people
    SET active = FALSE,
        updated_at = NOW()
    FROM ranked
    WHERE people.id = ranked.id
      AND ranked.rn > 1;

    GET DIAGNOSTICS deactivated = ROW_COUNT;
    IF deactivated > 0 THEN
        RAISE NOTICE
            'Soft-deleted % duplicate active people row(s) so the tenancy unique index can be created',
            deactivated;
    END IF;
END
$$;

-- 6. Enforce the new upsert key at the DB level: a given user may have only one
--    active record per (name, event_type). Two different users can each have a
--    "John Smith birthday" without colliding.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_people_owner_name_event_type_active
    ON people(owner_user_id, name, event_type)
    WHERE active = TRUE;

-- 7. Documentation.

COMMENT ON COLUMN people.owner_user_id IS 'Owning user; every API read/write is scoped by this column';
COMMENT ON COLUMN message_logs.owner_user_id IS 'Owning user (must match the owning user of the referenced person)';
COMMENT ON COLUMN csv_uploads.owner_user_id IS 'User who uploaded the CSV';
COMMENT ON COLUMN ai_wish_audit_logs.owner_user_id IS 'Authenticated user who generated the wish; NULL for anonymous callers';
