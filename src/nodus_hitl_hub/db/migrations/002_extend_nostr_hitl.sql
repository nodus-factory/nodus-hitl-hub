-- Migration 002: reconcile hub schema with the shared llibreta-v2 table.
--
-- The hub shares nodus_db with llibreta-v2, whose migration 017 created
-- nostr_hitl first (id uuid PK + 13 columns). Migration 001 of the hub is a
-- CREATE TABLE IF NOT EXISTS, so it never applied there. This migration adds
-- the hub-only columns additively — llibreta rows and code are unaffected.

ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS pubkey TEXT DEFAULT 'hitl-hub';
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS reference_id TEXT;
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'default';
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb;
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS sig TEXT;
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS verified BOOLEAN DEFAULT false;
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS relay_url TEXT;
-- Producer-supplied idempotency key: a retry returns the existing request
-- instead of creating a duplicate.
ALTER TABLE nostr_hitl ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS nostr_hitl_idem_idx
  ON nostr_hitl (idempotency_key) WHERE idempotency_key IS NOT NULL;

-- reference_id holds the Nostr event id of the published kind:10020, so the
-- kind:10021 resolution listener can map relay events back to hub rows.
CREATE INDEX IF NOT EXISTS nostr_hitl_reference_idx
  ON nostr_hitl (reference_id) WHERE reference_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS nostr_hitl_user_status_idx
  ON nostr_hitl (user_id, status);
