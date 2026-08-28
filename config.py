from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

class Settings(BaseSettings):
    OPENAI_API_BASE: str
    OPENAI_API_KEY: str
    LLM_MODEL_NAME: str
    LLM_TEMPERATURE: float = 0.1
    EMBEDDING_MODEL_NAME: str
    RERANKER_MODEL_NAME: str
    DATABASE_URL: str
    SYSTEM_PROMPT: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# Настройка прозрачного логирования (По ТЗ п.9)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AgentOS")