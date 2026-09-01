import sys
import os
import json
import asyncio
import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

# Импортируем наш глобальный пул из db.py (путь может немного отличаться в зависимости от вашей структуры)
from database import get_db_pool
from config import settings, logger

client = AsyncOpenAI(base_url=settings.OPENAI_API_BASE, api_key=settings.OPENAI_API_KEY)

class SearchInput(BaseModel):
    query: str = Field(description="Поисковый запрос для фактов в базе знаний.")

@tool("search_knowledge_base", args_schema=SearchInput)
async def search_knowledge_base(query: str) -> str:
    """Ищет информацию в векторной БД (RAG) с использованием гибридного поиска (Вектор + Текст) и реранкинга."""
    logger.info(f"RAG Search: {query}")
    try:
        # 1. Получаем вектор вопроса
        emb_resp = await client.embeddings.create(model=settings.EMBEDDING_MODEL_NAME, input=query)
        query_vector = emb_resp.data[0].embedding
        
        # 2. ГИБРИДНЫЙ ПОИСК (Вектор + FTS) с использованием пула соединений
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            hybrid_query = """
            WITH semantic_search AS (
                SELECT id, filename, content, 
                       row_number() OVER (ORDER BY embedding <=> $1::vector) as rank
                FROM documents
                ORDER BY embedding <=> $1::vector LIMIT 20
            ),
            keyword_search AS (
                SELECT id, filename, content,
                       row_number() OVER (ORDER BY ts_rank_cd(fts_vector, plainto_tsquery('russian', $2)) DESC) as rank
                FROM documents
                WHERE fts_vector @@ plainto_tsquery('russian', $2)
                ORDER BY rank LIMIT 20
            )
            SELECT 
                COALESCE(s.filename, k.filename) as filename,
                COALESCE(s.content, k.content) as content,
                -- Формула Reciprocal Rank Fusion (RRF)
                COALESCE(1.0 / (60 + s.rank), 0.0) + COALESCE(1.0 / (60 + k.rank), 0.0) as rrf_score
            FROM semantic_search s
            FULL OUTER JOIN keyword_search k ON s.id = k.id
            ORDER BY rrf_score DESC
            LIMIT 15;
            """
            rows = await conn.fetch(hybrid_query, json.dumps(query_vector), query)

        if not rows: return "Ничего не найдено."

        # 3. РЕРАНКИНГ
        if settings.RERANKER_MODEL_NAME:
            logger.info(f"Реранкинг 15 документов через {settings.RERANKER_MODEL_NAME}...")
            docs_texts = [r['content'] for r in rows]
            
            async with httpx.AsyncClient() as http_client:
                rerank_url = f"{settings.OPENAI_API_BASE}/rerank" 
                
                resp = await http_client.post(
                    rerank_url,
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": settings.RERANKER_MODEL_NAME,
                        "query": query,
                        "documents": docs_texts,
                        "top_n": 5
                    }
                )
                
            if resp.status_code == 200:
                rerank_data = resp.json()
                best_indices = [item["index"] for item in rerank_data.get("results", [])]
                top_5_rows = [rows[i] for i in best_indices]
            else:
                logger.error(f"Ошибка реранкера {resp.status_code}: {resp.text}")
                top_5_rows = rows[:5]
        else:
            top_5_rows = rows[:5]

        # 4. Формируем ответ
        return "\n---\n".join([f"(Источник: {r['filename']})\n{r['content']}" for r in top_5_rows])
    except Exception as e:
        logger.error(f"Ошибка RAG: {e}", exc_info=True)
        return f"Ошибка БД: {str(e)}"


class RAGUpdateInput(BaseModel): 
    confirm: bool = Field(default=True, description="Подтверждение запуска. Всегда передавай true.")

@tool("trigger_rag_update", args_schema=RAGUpdateInput)
async def trigger_rag_update(confirm: bool = True) -> str:
    """Запускает парсинг сырых файлов, обновляет векторы и генерирует .info файлы базы знаний."""
    # Получаем абсолютный путь к корню проекта
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    
    # Пути к скриптам
    parser_script = os.path.join(project_root, "scripts", "parser.py")
    ingest_script = os.path.join(project_root, "scripts", "ingest.py")
    
    # Используем Python из нашего виртуального окружения (.venv)
    python_exe = sys.executable 
    
    try:
        # Шаг 1: Запускаем парсер
        logger.info(f"Запуск парсера: {python_exe} {parser_script}")
        proc1 = await asyncio.create_subprocess_exec(
            python_exe, parser_script,
            cwd=project_root, 
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout1, stderr1 = await proc1.communicate()
        if proc1.returncode != 0:
            return f"Ошибка при парсинге файлов:\n{stderr1.decode('utf-8')}"
            
        # Шаг 2: Запускаем векторизацию
        logger.info(f"Запуск ingest: {python_exe} {ingest_script}")
        proc2 = await asyncio.create_subprocess_exec(
            python_exe, ingest_script,
            cwd=project_root, 
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout2, stderr2 = await proc2.communicate()
        if proc2.returncode != 0:
            return f"Ошибка при векторизации БД:\n{stderr2.decode('utf-8')}"
            
        return "База знаний успешно обновлена! Папки сгенерированы, векторы залиты."
        
    except Exception as e:
        logger.error(f"Ошибка при вызове сабпроцессов RAG: {e}")
        return f"Критическая ошибка запуска скриптов: {e}"

@tool("browse_knowledge_map")
def browse_knowledge_map() -> str:
    """Показывает структуру базы знаний (оглавление)."""
    processed_dir = os.path.join(os.getcwd(), "RAG", "processed")
    if not os.path.exists(processed_dir):
        return "База знаний пуста (папка processed не найдена)."
        
    map_result = "📂 СТРУКТУРА БАЗЫ ЗНАНИЙ (RAG):\n\n"
    has_info = False
    
    for root, dirs, files in os.walk(processed_dir):
        if ".info" in files:
            has_info = True
            info_path = os.path.join(root, ".info")
            rel_path = os.path.relpath(root, processed_dir)
            folder_name = "Корень RAG" if rel_path == "." else rel_path
            with open(info_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            map_result += f"📁 ПАПКА: {folder_name}\n📝 Содержимое:\n{content}\n{'-'*40}\n"
            
    if not has_info:
        return "Карта базы пока пуста. Вызови 'trigger_rag_update'."
    return map_result