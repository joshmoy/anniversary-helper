-- Migration: Add AI wish audit logs table for tracking AI wish generation requests
-- Created: 2024-12-19
-- Description: Creates the ai_wish_audit_logs table to track all AI wish generation requests, responses, and regenerations

-- Create ai_wish_audit_logs table
CREATE TABLE IF NOT EXISTS ai_wish_audit_logs (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(255) NOT NULL,
    original_request_id VARCHAR(255),
    ip_address VARCHAR(255) NOT NULL,
    request_data JSONB NOT NULL,
    response_data JSONB NOT NULL,
    ai_service_used VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_request_id ON ai_wish_audit_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_original_request_id ON ai_wish_audit_logs(original_request_id);
CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_created_at ON ai_wish_audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_ai_service ON ai_wish_audit_logs(ai_service_used);
CREATE INDEX IF NOT EXISTS idx_ai_wish_audit_ip_address ON ai_wish_audit_logs(ip_address);

-- Add comments for documentation
COMMENT ON TABLE ai_wish_audit_logs IS 'Audit trail for AI wish generation requests and responses';
COMMENT ON COLUMN ai_wish_audit_logs.request_id IS 'Unique identifier for this request (UUID)';
COMMENT ON COLUMN ai_wish_audit_logs.original_request_id IS 'ID of original request if this is a regeneration (UUID)';
COMMENT ON COLUMN ai_wish_audit_logs.ip_address IS 'Hashed client IP address for privacy';
COMMENT ON COLUMN ai_wish_audit_logs.request_data IS 'JSON data of the original AnniversaryWishRequest';
COMMENT ON COLUMN ai_wish_audit_logs.response_data IS 'JSON data of the generated response';
COMMENT ON COLUMN ai_wish_audit_logs.ai_service_used IS 'AI service used: groq, openai, or fallback';
COMMENT ON COLUMN ai_wish_audit_logs.created_at IS 'Timestamp when the request was processed';
