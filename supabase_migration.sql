-- ═══════════════════════════════════════════════════════
-- WhatsApp Agentic Support Bot — Supabase Migration
-- À exécuter dans le SQL Editor de Supabase
-- ═══════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────
-- Table : conversations
-- Une ligne par session de support client
-- ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_phone    TEXT NOT NULL,
    client_name     TEXT NOT NULL DEFAULT '',
    client_language TEXT NOT NULL DEFAULT 'fr',
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'escalated', 'resolved')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index pour retrouver rapidement la conversation active d'un client
CREATE INDEX IF NOT EXISTS idx_conversations_phone_status
    ON conversations (client_phone, status);

-- ──────────────────────────────────────────────────
-- Table : messages
-- Historique complet de chaque conversation
-- ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS messages (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id   UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role              TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content           TEXT NOT NULL,
    
    -- Métadonnées agent (remplies uniquement pour role='assistant')
    model_used        TEXT,
    tokens_used       INTEGER,
    self_check_result TEXT,
    self_check_notes  TEXT,
    
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages (conversation_id, created_at);

-- ──────────────────────────────────────────────────
-- Table : unanswered_questions
-- Self-Improvement Loop : questions auxquelles le bot
-- n'a pas su répondre → à analyser pour enrichir knowledge.md
-- ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS unanswered_questions (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    question          TEXT NOT NULL,
    client_phone      TEXT,
    conversation_id   UUID REFERENCES conversations(id),
    detected_intent   TEXT,
    context           TEXT,           -- Les derniers messages pour comprendre le contexte
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'reviewed', 'added_to_kb', 'ignored')),
    admin_notes       TEXT,           -- Notes de l'admin après review
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_unanswered_status
    ON unanswered_questions (status, created_at DESC);

-- ──────────────────────────────────────────────────
-- Table : agent_logs
-- Logs structurés de chaque action de l'agent
-- ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_logs (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id   UUID REFERENCES conversations(id),
    action            TEXT NOT NULL,   -- 'response_sent', 'escalation', 'self_check_fail', etc.
    status            TEXT NOT NULL DEFAULT 'success'
                      CHECK (status IN ('success', 'error', 'escalated')),
    details           JSONB,           -- Détails supplémentaires (flexible)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_conversation
    ON agent_logs (conversation_id, created_at);

-- ──────────────────────────────────────────────────
-- Trigger : auto-update updated_at sur conversations
-- ──────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ──────────────────────────────────────────────────
-- Row Level Security (RLS)
-- Pour le PoC, on autorise tout via la service_role key
-- En production, ajouter des policies granulaires
-- ──────────────────────────────────────────────────

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE unanswered_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_logs ENABLE ROW LEVEL SECURITY;

-- Policy : le service backend a accès total
CREATE POLICY "Service full access" ON conversations
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service full access" ON messages
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service full access" ON unanswered_questions
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service full access" ON agent_logs
    FOR ALL USING (true) WITH CHECK (true);
