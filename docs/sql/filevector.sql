-- FileVector: conversation-scoped embedded chunks for chat-attached documents.
-- Soft relation: conversation_id and file_id are UUIDs only (no FOREIGN KEY).
-- Requires: CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS "FileVector" (
  conversation_id UUID NOT NULL,
  file_id UUID NOT NULL,
  file_vector_chunk_id UUID NOT NULL,
  file_vector_chunk_order INTEGER,
  file_content_text_chunk TEXT,
  file_content_chunk_hash VARCHAR(255),
  embedding vector(1536),
  created_at TIMESTAMP,
  created_by UUID REFERENCES "Users"(user_id),
  updated_at TIMESTAMP,
  updated_by UUID REFERENCES "Users"(user_id),
  deleted_at TIMESTAMP,
  PRIMARY KEY (conversation_id, file_vector_chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_filevector_conversation_file
  ON "FileVector" (conversation_id, file_id)
  WHERE deleted_at IS NULL;
