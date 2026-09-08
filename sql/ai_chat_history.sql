CREATE TABLE IF NOT EXISTS ai_chat_sessions (
    id VARCHAR(120) PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users_user(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS ai_chat_sessions_user_updated_idx
    ON ai_chat_sessions (user_id, updated_at DESC);

COMMENT ON TABLE ai_chat_sessions IS
    'Persistent AI chat history for authenticated students and teachers.';
