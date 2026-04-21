-- Migration: Extract notification preferences into a dedicated table
-- Description: Delivery/reminder settings (notification_preference,
-- notification_channels, direct_message_channel) are split out of the users
-- table into user_notification_preferences so identity and delivery concerns
-- are isolated. Any values previously stored on users are migrated over and
-- then the legacy columns are dropped.

CREATE TABLE IF NOT EXISTS user_notification_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    notification_preference VARCHAR(50) NOT NULL DEFAULT 'personal_reminder',
    notification_channels VARCHAR(255) NOT NULL DEFAULT 'sms,email',
    direct_message_channel VARCHAR(50) NOT NULL DEFAULT 'sms',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_notification_preferences_user_id
    ON user_notification_preferences(user_id);

COMMENT ON TABLE user_notification_preferences IS
    'Per-user delivery settings controlling how celebration reminders are sent';
COMMENT ON COLUMN user_notification_preferences.notification_preference IS
    'Either personal_reminder (aggregated daily digest to the user) or direct_to_contacts';
COMMENT ON COLUMN user_notification_preferences.notification_channels IS
    'Comma-separated channels used for the personal daily reminder (e.g. sms,email)';
COMMENT ON COLUMN user_notification_preferences.direct_message_channel IS
    'Channel used when celebration messages are sent directly to contacts';

-- Backfill from any legacy columns on users, then drop them. Wrapped in a
-- single DO block so the migration is idempotent for databases that never
-- carried these columns in the first place.
DO $$
DECLARE
    has_pref boolean;
    has_channels boolean;
    has_direct boolean;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'notification_preference'
    ) INTO has_pref;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'notification_channels'
    ) INTO has_channels;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'direct_message_channel'
    ) INTO has_direct;

    IF has_pref OR has_channels OR has_direct THEN
        EXECUTE format(
            'INSERT INTO user_notification_preferences (
                user_id,
                notification_preference,
                notification_channels,
                direct_message_channel
            )
            SELECT
                u.id,
                %s,
                %s,
                %s
            FROM users u
            ON CONFLICT (user_id) DO NOTHING',
            CASE WHEN has_pref
                 THEN 'COALESCE(u.notification_preference, ''personal_reminder'')'
                 ELSE '''personal_reminder''' END,
            CASE WHEN has_channels
                 THEN 'COALESCE(u.notification_channels, ''sms,email'')'
                 ELSE '''sms,email''' END,
            CASE WHEN has_direct
                 THEN 'COALESCE(u.direct_message_channel, ''sms'')'
                 ELSE '''sms''' END
        );
    END IF;
END
$$;

ALTER TABLE users DROP COLUMN IF EXISTS notification_preference;
ALTER TABLE users DROP COLUMN IF EXISTS notification_channels;
ALTER TABLE users DROP COLUMN IF EXISTS direct_message_channel;
