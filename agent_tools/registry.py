import os
from langchain_core.tools import tool

# Импортируем инструменты RAG
from .rag.search import search_knowledge_base, trigger_rag_update, browse_knowledge_map

# Импортируем инструмент управления памятью
from .memory.manager import save_summary_and_clear_memory

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))

@tool("update_tool_catalog")
def update_tool_catalog() -> str:
    """
    Сканирует все твои доступные инструменты в коде, актуализирует локальные .info файлы в папках 
    и собирает общий master.info с подсказками по всем категориям.
    Вызывай этот инструмент, если добавились или удалились функции.
    """
    folders = {}
    
    for t in AGENT_TOOLS:
        mod = t.__module__  
        parts = mod.split('.')
        
        if len(parts) >= 2 and parts[0] == "agent_tools":
            folder_name = parts[1]
        else:
            folder_name = "system"
            
        if folder_name not in folders:
            folders[folder_name] = []
        folders[folder_name].append(t)
        
    master_content = "📚 ГЛОБАЛЬНЫЙ КАТАЛОГ ИНСТРУМЕНТОВ АГЕНТА\n"
    master_content += "Здесь описано, какие функции тебе доступны и в каких модулях они находятся.\n\n"
    
    for folder, t_list in folders.items():
        folder_path = os.path.join(TOOLS_DIR, folder)
        os.makedirs(folder_path, exist_ok=True)
        
        local_info = f"📂 КАТЕГОРИЯ: {folder.upper()}\n\nДоступные инструменты в этой папке:\n"
        master_content += f"## 📂 Модуль: {folder}\n"
        
        for t in t_list:
            tool_desc = f"- {t.name}: {t.description}\n"
            local_info += tool_desc
            master_content += f"  - `{t.name}`: {t.description}\n"
            
        master_content += "\n"
        
        with open(os.path.join(folder_path, ".info"), "w", encoding="utf-8") as f:
            f.write(local_info)
            
    with open(os.path.join(TOOLS_DIR, "master.info"), "w", encoding="utf-8") as f:
        f.write(master_content)
        
    return "Документация по инструментам успешно актуализирована!"

@tool("browse_tool_catalog")
def browse_tool_catalog() -> str:
    """
    Читает глобальный справочник инструментов (master.info). 
    Используй это ПЕРВЫМ делом, чтобы узнать, какие функции тебе доступны.
    """
    master_path = os.path.join(TOOLS_DIR, "master.info")
    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return "Справочник пуст. Вызови 'update_tool_catalog' для генерации."

# Главный список инструментов
AGENT_TOOLS = [
    browse_tool_catalog,
    update_tool_catalog,
    search_knowledge_base,
    trigger_rag_update,
    browse_knowledge_map,
    save_summary_and_clear_memory
]