import docx

def parse_docx(file_path: str) -> str:
    """Парсит документы Microsoft Word (.docx)"""
    try:
        doc = docx.Document(file_path)
        # Собираем все параграфы, игнорируя пустые строки
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        print(f"❌ Ошибка при чтении DOCX {file_path}: {e}")
        return None