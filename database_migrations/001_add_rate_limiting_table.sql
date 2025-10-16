-- Migration: Add rate limiting table for API rate limiting
-- Created: 2024-01-XX
-- Description: Creates the rate_limiting table to track API request rates per IP address

-- Create rate_limiting table
CREATE TABLE IF NOT EXISTS rate_limiting (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL,
    request_count INTEGER DEFAULT 1,
    window_start TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_request_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(ip_address)
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_rate_limiting_ip_address ON rate_limiting(ip_address);
CREATE INDEX IF NOT EXISTS idx_rate_limiting_window_start ON rate_limiting(window_start);
CREATE INDEX IF NOT EXISTS idx_rate_limiting_created_at ON rate_limiting(created_at);

-- Add comments for documentation
COMMENT ON TABLE rate_limiting IS 'Tracks API request rates per IP address for rate limiting';
COMMENT ON COLUMN rate_limiting.ip_address IS 'Client IP address (supports IPv4 and IPv6)';
COMMENT ON COLUMN rate_limiting.request_count IS 'Number of requests in current window';
COMMENT ON COLUMN rate_limiting.window_start IS 'Start time of current rate limit window';
COMMENT ON COLUMN rate_limiting.last_request_time IS 'Timestamp of most recent request';
