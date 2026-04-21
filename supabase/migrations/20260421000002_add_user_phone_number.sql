-- Migration: Add phone number to users
-- Description: Users act as coordinators and need a phone number for SMS
-- (and WhatsApp, later) delivery. Delivery preferences live in
-- user_notification_preferences (see 20260421000003_...).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS phone_number VARCHAR(30);

COMMENT ON COLUMN users.phone_number IS 'User phone number in E.164 format (used for SMS/WhatsApp delivery)';
