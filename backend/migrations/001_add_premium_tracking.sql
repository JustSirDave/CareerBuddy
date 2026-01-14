-- Add premium tracking fields to users table
-- Migration: 001_add_premium_tracking
-- Created: 2026-01-14
-- Author: Sir Dave

-- Add new columns for quota and premium tracking
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS quota_reset_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS premium_expires_at TIMESTAMP WITH TIME ZONE;

-- Update generation_count for existing users to new format
-- Old format: {"Data Analyst": 2, "Software Engineer": 1}
-- New format: {"resume": 1, "cv": 1, "cover_letter": 0, "revamp": 0}
UPDATE users 
SET generation_count = '{"resume": 0, "cv": 0, "cover_letter": 0, "revamp": 0}'
WHERE generation_count = '{}' OR generation_count IS NULL;

-- For existing users with old format, reset to new format
-- (This ensures clean migration)
UPDATE users 
SET generation_count = '{"resume": 0, "cv": 0, "cover_letter": 0, "revamp": 0}'
WHERE generation_count::text NOT LIKE '%resume%';

-- Set quota_reset_at for existing users (30 days from now)
UPDATE users 
SET quota_reset_at = NOW() + INTERVAL '30 days'
WHERE quota_reset_at IS NULL;

-- Set premium_expires_at for existing premium users (30 days from now)
UPDATE users 
SET premium_expires_at = NOW() + INTERVAL '30 days'
WHERE tier = 'pro' AND premium_expires_at IS NULL;

-- Create index for quota_reset_at for faster monthly reset checks
CREATE INDEX IF NOT EXISTS idx_users_quota_reset ON users(quota_reset_at);

-- Create index for premium_expires_at for faster expiry checks
CREATE INDEX IF NOT EXISTS idx_users_premium_expires ON users(premium_expires_at);
