import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Глобальная переменная для хранения пула
_pool = None

async def get_db_pool():
    global _pool
    if _pool is None:
        # Создаем пул при первом обращении (до 10 одновременных соединений)
        _pool = await asyncpg.create_pool(os.getenv("DATABASE_URL"), min_size=1, max_size=10)
    return _pool