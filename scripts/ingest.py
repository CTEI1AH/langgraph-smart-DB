import os
import hashlib
import json
import asyncio
from openai import AsyncOpenAI
import asyncpg
from dotenv import load_dotenv

load_dotenv()
client = AsyncOpenAI(base_url=os.getenv("OPENAI_API_BASE"), api_key=os.getenv("OPENAI_API_KEY", "dummy"))
TARGET_DIR = os.path.join(os.getcwd(), "RAG", "processed")
CHUNK_SIZE = 1000

def chunk_text(text, size):
    return [text[i:i+size] for i in range(0, len(text), size)]

async def init_db(conn):
    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            filename TEXT,
            chunk_index INTEGER,
            content TEXT,
            embedding VECTOR,
            -- ДОБАВЛЯЕМ КОЛОНКУ ДЛЯ ТЕКСТОВОГО ПОИСКА FTS (АВТОМАТИЧЕСКИ ЗАПОЛНЯЕТСЯ)
            fts_vector tsvector GENERATED ALWAYS AS (to_tsvector('russian', content)) STORED
        );
        -- Создаем индекс для молниеносного текстового поиска
        CREATE INDEX IF NOT EXISTS fts_idx ON documents USING GIN (fts_vector);
        
        CREATE TABLE IF NOT EXISTS file_sync_state (
            filepath TEXT PRIMARY KEY,
            file_hash TEXT
        );
    """)

async def run():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    await init_db(conn)

    for root, _, files in os.walk(TARGET_DIR):
        for file in files:
            if not file.endswith(".txt") or file in [".folder_hash", ".info"]: 
                continue
            
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, TARGET_DIR)
            
            original_filename = rel_path
            if original_filename.endswith(".txt"):
                base_name = original_filename[:-4]
                _, ext = os.path.splitext(base_name)
                if ext.lower() in ['.pdf', '.docx', '.xlsx', '.csv', '.md']:
                    original_filename = base_name

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            file_hash = hashlib.md5(content.encode()).hexdigest()
            db_hash = await conn.fetchval("SELECT file_hash FROM file_sync_state WHERE filepath = $1", rel_path)

            if db_hash == file_hash:
                print(f"⏭️ Пропущен: {original_filename}")
                continue

            print(f"🔄 Векторизация: {original_filename}")
            await conn.execute("DELETE FROM documents WHERE filename = $1", original_filename)

            chunks = chunk_text(content, CHUNK_SIZE)
            for i, chunk in enumerate(chunks):
                resp = await client.embeddings.create(model=os.getenv("EMBEDDING_MODEL_NAME"), input=chunk)
                vec = json.dumps(resp.data[0].embedding)
                await conn.execute(
                    "INSERT INTO documents (filename, chunk_index, content, embedding) VALUES ($1, $2, $3, $4::vector)",
                    original_filename, i, chunk, vec
                )
            
            await conn.execute("""
                INSERT INTO file_sync_state (filepath, file_hash) VALUES ($1, $2)
                ON CONFLICT (filepath) DO UPDATE SET file_hash = $2
            """, rel_path, file_hash)

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())