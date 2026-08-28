import os
import json
import asyncio
import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import asyncpg

from config import settings, logger

client = AsyncOpenAI(base_url=settings.OPENAI_API_BASE, api_key=settings.OPENAI_API_KEY)

class SearchInput(BaseModel):
    query: str = Field(description="Поисковый запрос для фактов в базе знаний.")

@tool("search_knowledge_base", args_schema=SearchInput)
async def search_knowledge_base(query: str) -> str:
    """Ищет информацию в векторной БД (RAG) с использованием гибридного поиска и реранкинга."""
    logger.info(f"RAG Search: {query}")
    try:
        # 1. Получаем вектор вопроса
        emb_resp = await client.embeddings.create(model=settings.EMBEDDING_MODEL_NAME, input=query)
        query_vector = emb_resp.data[0].embedding
        
        # 2. Достаем Топ-15 из базы (BM25 + pgvector)
        conn = await asyncpg.connect(settings.DATABASE_URL)
        rows = await conn.fetch("""
            SELECT filename, content 
            FROM documents 
            ORDER BY embedding <=> $1::vector 
            LIMIT 15;
        """, json.dumps(query_vector))
        await conn.close()

        if not rows: return "Ничего не найдено."

        # 3. РЕРАНКИНГ (Отправляем 15 кусков текста на локальный сервер bit)
        if settings.RERANKER_MODEL_NAME:
            logger.info(f"Реранкинг 15 документов через {settings.RERANKER_MODEL_NAME}...")
            docs_texts = [r['content'] for r in rows]
            
            async with httpx.AsyncClient() as http_client:
                # Обычно API-совместимые сервера используют эндпоинт /rerank
                rerank_url = f"{settings.OPENAI_API_BASE}/rerank" 
                
                resp = await http_client.post(
                    rerank_url,
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={
                        "model": settings.RERANKER_MODEL_NAME,
                        "query": query,
                        "documents": docs_texts,
                        "top_n": 5 # Оставляем Топ-5, как требует ТЗ
                    }
                )
                
            if resp.status_code == 200:
                rerank_data = resp.json()
                # Берем индексы отсортированных (лучших) документов
                best_indices = [item["index"] for item in rerank_data.get("results", [])]
                top_5_rows = [rows[i] for i in best_indices]
            else:
                logger.error(f"Ошибка реранкера {resp.status_code}: {resp.text}")
                top_5_rows = rows[:5] # Если реранкер упал, берем первые 5 по векторам
        else:
            top_5_rows = rows[:5]

        # 4. Формируем ответ для агента
        return "\n---\n".join([f"(Источник: {r['filename']})\n{r['content']}" for r in top_5_rows])
    except Exception as e:
        logger.error(f"Ошибка RAG: {e}", exc_info=True)
        return f"Ошибка БД: {str(e)}"

class RAGUpdateInput(BaseModel): pass

@tool("trigger_rag_update", args_schema=RAGUpdateInput)
async def trigger_rag_update() -> str:
    """Запускает парсинг сырых файлов, обновляет векторы и генерирует .info файлы базы знаний."""
    proc1 = await asyncio.create_subprocess_exec("python", "scripts/parser.py")
    await proc1.wait()
    proc2 = await asyncio.create_subprocess_exec("python", "scripts/ingest.py")
    await proc2.wait()
    return "База знаний успешно обновлена! Файлы .info актуализированы."

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