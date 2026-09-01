import asyncio, os, asyncpg
from dotenv import load_dotenv
load_dotenv()
async def main():
    conn = await asyncpg.connect(os.getenv("DATABASE_URL"))
    await conn.execute("DROP TABLE IF EXISTS documents CASCADE;")
    await conn.execute("DROP TABLE IF EXISTS file_sync_state CASCADE;")
    print("✅ База данных успешно очищена!")
    await conn.close()
asyncio.run(main())
