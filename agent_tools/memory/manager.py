from langchain_core.tools import tool
from pydantic import BaseModel, Field

class MemoryInput(BaseModel):
    new_summary: str = Field(description="Подробная выжимка всех ключевых фактов, имен и деталей из текущего диалога.")

@tool("save_summary_and_clear_memory", args_schema=MemoryInput)
async def save_summary_and_clear_memory(new_summary: str) -> str:
    """
    Вызывай этот инструмент ТОЛЬКО если пользователь дал согласие на очистку памяти.
    Собери всю суть диалога в параметр new_summary.
    Система автоматически удалит старые сообщения и сохранит эту выжимку.
    """
    return f"Память успешно сжата. Применено саммари длиной {len(new_summary)} символов."