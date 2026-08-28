import os
import shutil
import hashlib
from openai import OpenAI
from dotenv import load_dotenv

# Импортируем все наши изолированные парсеры
from parsers.text_parser import parse_text
from parsers.pdf_parser import parse_pdf
from parsers.word_parser import parse_docx
from parsers.excel_parser import parse_excel

load_dotenv()

client = OpenAI(base_url=os.getenv("OPENAI_API_BASE"), api_key=os.getenv("OPENAI_API_KEY", "dummy"))
RAW_DIR = os.path.join(os.getcwd(), "RAG", "raw")
PROCESSED_DIR = os.path.join(os.getcwd(), "RAG", "processed")

# ========================================================
# РЕЕСТР ПАРСЕРОВ (Словарь: "расширение" -> "функция")
# ========================================================
PARSER_REGISTRY = {
    '.txt': parse_text,
    '.md': parse_text,
    '.csv': parse_text,
    '.pdf': parse_pdf,
    '.docx': parse_docx,
    '.xlsx': parse_excel
}

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def parse_file_to_text(raw_path: str) -> str:
    """УНИВЕРСАЛЬНЫЙ РОУТЕР"""
    ext = os.path.splitext(raw_path)[1].lower()
    
    parser_func = PARSER_REGISTRY.get(ext)
    if not parser_func:
        print(f"⚠️ Игнорирую неизвестный формат: {raw_path}")
        return None
        
    try:
        return parser_func(raw_path)
    except Exception as e:
        print(f"❌ Ошибка парсинга {raw_path}: {e}")
        return None

def process_directory(current_raw: str, current_processed: str):
    os.makedirs(current_processed, exist_ok=True)
    
    raw_items = os.listdir(current_raw) if os.path.exists(current_raw) else []
    processed_items = os.listdir(current_processed)
    
    expected_processed = {".info", ".folder_hash"}
    for item in raw_items:
        raw_path = os.path.join(current_raw, item)
        if os.path.isdir(raw_path):
            expected_processed.add(item)
        else:
            expected_processed.add(item + ".txt" if not item.endswith(".txt") else item)

    for p_item in processed_items:
        if p_item not in expected_processed:
            p_path = os.path.join(current_processed, p_item)
            if os.path.isfile(p_path): 
                os.remove(p_path)
            elif os.path.isdir(p_path):
                shutil.rmtree(p_path)
            print(f"🗑️ Удален неактуальный элемент: {p_item}")

    folder_content = ""
    has_text = False

    for item in raw_items:
        raw_path = os.path.join(current_raw, item)
        if os.path.isdir(raw_path):
            process_directory(raw_path, os.path.join(current_processed, item))
        else:
            text = parse_file_to_text(raw_path)
            if text:
                has_text = True
                proc_name = item if item.endswith(".txt") else item + ".txt"
                proc_path = os.path.join(current_processed, proc_name)
                with open(proc_path, 'w', encoding='utf-8') as f:
                    f.write(text)
                folder_content += f"\n--- Файл: {item} ---\n{text[:500]}...\n"

    if has_text:
        current_hash = get_hash(folder_content)
        hash_path = os.path.join(current_processed, ".folder_hash")
        old_hash = open(hash_path).read() if os.path.exists(hash_path) else ""
        
        if current_hash != old_hash:
            print(f"🧠 ИИ анализирует папку: {os.path.basename(current_raw)}...")
            resp = client.chat.completions.create(
                model=os.getenv("LLM_MODEL_NAME"),
                messages=[
                    {"role": "system", "content": "Ты архивариус. Составь краткое оглавление папки."},
                    {"role": "user", "content": f"Отрывки:\n{folder_content}"}
                ],
                temperature=0.1
            )
            with open(os.path.join(current_processed, ".info"), "w", encoding="utf-8") as f:
                f.write(resp.choices[0].message.content)
            with open(hash_path, "w") as f:
                f.write(current_hash)
    else:
        info_path = os.path.join(current_processed, ".info")
        if os.path.exists(info_path): os.remove(info_path)

if __name__ == "__main__":
    print("🔄 Начинаю парсинг...")
    process_directory(RAW_DIR, PROCESSED_DIR)
    print("✅ Готово!")