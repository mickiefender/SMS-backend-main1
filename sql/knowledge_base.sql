-- Knowledge base for school administrators.
-- Run after the schools and users tables have been created.
CREATE TABLE IF NOT EXISTS knowledge_category (
    id BIGSERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    parent_id BIGINT REFERENCES knowledge_category(id) ON DELETE SET NULL,
    image_url TEXT,
    meta_title VARCHAR(255) NOT NULL DEFAULT '',
    meta_description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, slug)
);

CREATE TABLE IF NOT EXISTS knowledge_article (
    id BIGSERIAL PRIMARY KEY,
    school_id BIGINT NOT NULL REFERENCES schools_school(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    slug VARCHAR(500) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    thumbnail_url TEXT,
    meta_title VARCHAR(500) NOT NULL DEFAULT '',
    meta_description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'trash')),
    created_by_id BIGINT REFERENCES users_user(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, slug)
);

CREATE TABLE IF NOT EXISTS knowledge_article_category (
    article_id BIGINT NOT NULL REFERENCES knowledge_article(id) ON DELETE CASCADE,
    category_id BIGINT NOT NULL REFERENCES knowledge_category(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, category_id)
);

CREATE TABLE IF NOT EXISTS knowledge_article_tag (
    article_id BIGINT NOT NULL REFERENCES knowledge_article(id) ON DELETE CASCADE,
    tag VARCHAR(100) NOT NULL,
    PRIMARY KEY (article_id, tag)
);

CREATE INDEX IF NOT EXISTS knowledge_category_school_status_idx ON knowledge_category (school_id, status);
CREATE INDEX IF NOT EXISTS knowledge_article_school_status_created_idx ON knowledge_article (school_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS knowledge_article_search_idx ON knowledge_article USING GIN (to_tsvector('simple', title || ' ' || description || ' ' || content));
