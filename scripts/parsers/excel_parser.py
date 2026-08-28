import pandas as pd

def parse_excel(file_path: str) -> str:
    """Парсит таблицы Excel (.xlsx), превращая их в текстовые таблицы для LLM"""
    try:
        xls = pd.ExcelFile(file_path)
        text_parts = []
        
        # Проходимся по всем листам в файле Excel
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Удаляем полностью пустые строки и столбцы
            df.dropna(how='all', inplace=True)
            df.dropna(axis=1, how='all', inplace=True)
            
            if not df.empty:
                text_parts.append(f"--- Лист: {sheet_name} ---")
                # Превращаем DataFrame в текст с разделителем-табуляцией
                text_parts.append(df.to_csv(index=False, sep="\t"))
                
        return "\n\n".join(text_parts)
    except Exception as e:
        print(f"❌ Ошибка при чтении Excel {file_path}: {e}")
        return None