import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def get_db_pool():
    return await asyncpg.create_pool(os.getenv("DATABASE_URL"))