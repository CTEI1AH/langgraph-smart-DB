def parse_text(file_path: str) -> str:
    """Парсит обычные текстовые файлы, пытаясь угадать кодировку"""
    try:
        # Сначала пробуем стандартный UTF-8
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        # Если не получилось, пробуем русскую Windows-1251
        try:
            with open(file_path, 'r', encoding='windows-1251') as f:
                return f.read()
        except Exception as e:
            print(f"❌ Ошибка кодировки в {file_path}: {e}")
            return None