-- Migration 002: notification log + per-user channel preferences.

CREATE TABLE IF NOT EXISTS notification_log (
    notification_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'default',
    title TEXT,
    body TEXT,
    priority TEXT DEFAULT 'normal',
    url TEXT,
    channels_attempted JSONB DEFAULT '[]'::jsonb,
    channels_succeeded JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    acked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notification_log_user_created
    ON notification_log (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notification_preferences (
    user_id TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'default',
    channel TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    address TEXT,
    min_priority TEXT DEFAULT 'normal',
    quiet_hours_start SMALLINT,
    quiet_hours_end SMALLINT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, channel)
);
