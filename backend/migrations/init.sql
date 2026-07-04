-- Таблица документов
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_name TEXT NOT NULL,
    s3_key TEXT NOT NULL UNIQUE,
    file_size INTEGER NOT NULL DEFAULT 0,
    mime_type TEXT,
    
    -- Статусы: uploading, processing, ready, failed
    status TEXT NOT NULL DEFAULT 'uploading',
    error_message TEXT,
    
    -- Статистика
    chunks_count INTEGER NOT NULL DEFAULT 0,
    nodes_count INTEGER NOT NULL DEFAULT 0,
    edges_count INTEGER NOT NULL DEFAULT 0,
    
    -- Метаданные из файла
    file_metadata JSONB DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);

-- Триггер для updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();