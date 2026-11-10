-- ============================================================================
-- Crop Doctor on WhatsApp - Database Schema (Supabase / PostgreSQL + pgvector)
-- ============================================================================

-- 1. Enable pgvector extension for similarity search on crop guide chunks
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Farmers Table
-- Note: As per privacy guidelines, we store wa_phone and location info only; no personal names needed.
CREATE TABLE IF NOT EXISTS farmers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wa_phone VARCHAR(32) NOT NULL UNIQUE,
    language VARCHAR(16) DEFAULT 'te', -- 'te' (Telugu), 'mr' (Marathi), 'pa' (Punjabi)
    state VARCHAR(64),
    district VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_farmers_wa_phone ON farmers(wa_phone);

-- 3. Banned Inputs Table
-- Chemicals or formulations that must NEVER be recommended under any circumstances
CREATE TABLE IF NOT EXISTS banned_inputs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed banned / restricted agricultural chemicals in India
INSERT INTO banned_inputs (name, note) VALUES
    ('Endosulfan', 'Banned across India by Supreme Court directive due to severe toxicity and birth defects.'),
    ('Monocrotophos', 'Banned for use on vegetables and banned in multiple states due to extreme human toxicity.'),
    ('Paraquat dichloride', 'Highly toxic herbicide banned or severely restricted for domestic non-certified application.'),
    ('Phorate', 'Extremely hazardous Class Ia organophosphate restricted/banned on crops.'),
    ('Methyl Parathion', 'Banned in India due to high acute mammalian toxicity.'),
    ('Phosphamidon', 'Banned in India for general agricultural spraying.'),
    ('DDT', 'Banned in agriculture in India since 1989.'),
    ('Diazinon', 'Banned for use in agriculture in India.')
ON CONFLICT (name) DO NOTHING;

-- 4. Crop Guide Chunks (for RAG with vector search)
CREATE TABLE IF NOT EXISTS guide_chunks (
    id SERIAL PRIMARY KEY,
    source_title VARCHAR(256) NOT NULL,
    publisher VARCHAR(256) NOT NULL, -- e.g. 'ICAR', 'PJTSAU', 'MPKV Rahuri', 'PAU Ludhiana'
    state VARCHAR(64) NOT NULL,      -- e.g. 'Telangana', 'Andhra Pradesh', 'Maharashtra', 'Punjab'
    crop VARCHAR(64) NOT NULL,       -- e.g. 'chilli', 'cotton', 'paddy', 'tomato'
    section VARCHAR(128) NOT NULL,   -- e.g. 'Pest Management', 'Leaf Curl Disease', 'Blast'
    page INT,
    text TEXT NOT NULL,
    embedding vector(1536),          -- Default dimension for standard embedding models (can adjust to 768 / 1536)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guide_chunks_crop_state ON guide_chunks(crop, state);

-- 5. Cases Table
-- Records each consultation lifecycle: incoming photo + audio -> transcription -> vision -> RAG -> answer
CREATE TABLE IF NOT EXISTS cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    farmer_id UUID REFERENCES farmers(id) ON DELETE CASCADE,
    wa_message_id VARCHAR(128),
    crop VARCHAR(64),
    crop_age_days INT,
    photo_path TEXT,
    voice_path TEXT,
    transcript TEXT,
    vision_obs JSONB,
    retrieved_chunk_ids INT[],
    likely_problems JSONB,
    answer_text TEXT,
    answer_audio_path TEXT,
    confidence NUMERIC(4, 3), -- 0.000 to 1.000
    escalated BOOLEAN DEFAULT FALSE,
    escalation_reason TEXT,
    status VARCHAR(32) DEFAULT 'received', -- 'received', 'processing', 'completed', 'failed', 'clarification_needed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cases_farmer_id ON cases(farmer_id);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at DESC);

-- 6. Reviews Table
-- Allows agriculture students / KVK experts to audit AI diagnoses and citations
CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE,
    reviewer VARCHAR(128) NOT NULL,
    verdict VARCHAR(16) NOT NULL CHECK (verdict IN ('correct', 'partly', 'wrong')),
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reviews_case_id ON reviews(case_id);

-- 7. Helper search function for crop guide RAG
CREATE OR REPLACE FUNCTION match_guide_chunks(
    query_embedding vector(1536),
    filter_crop TEXT,
    filter_state TEXT,
    match_count INT DEFAULT 6
)
RETURNS TABLE (
    id INT,
    source_title VARCHAR,
    publisher VARCHAR,
    state VARCHAR,
    crop VARCHAR,
    section VARCHAR,
    page INT,
    text TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        gc.id,
        gc.source_title,
        gc.publisher,
        gc.state,
        gc.crop,
        gc.section,
        gc.page,
        gc.text,
        1 - (gc.embedding <=> query_embedding) AS similarity
    FROM guide_chunks gc
    WHERE
        (filter_crop IS NULL OR LOWER(gc.crop) = LOWER(filter_crop))
        AND (filter_state IS NULL OR LOWER(gc.state) = LOWER(filter_state))
    ORDER BY gc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

