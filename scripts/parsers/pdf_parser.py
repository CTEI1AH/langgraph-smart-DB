import fitz  # PyMuPDF

def parse_pdf(file_path: str) -> str:
    """Умный парсер PDF с проверкой на наличие текстового слоя"""
    try:
        doc = fitz.open(file_path)
        extracted_text = ""
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            extracted_text += page.get_text() + "\n"
            
        # Проверка на "Скан" (если реальных символов меньше 50 на весь документ)
        clean_text = extracted_text.strip().replace(" ", "").replace("\n", "")
        if len(clean_text) < 50:
            print(f"⚠️ {file_path} похож на скан. Отправляю в OCR...")
            return run_ocr_model(file_path)
            
        return extracted_text.strip()
        
    except Exception as e:
        print(f"❌ Ошибка при чтении PDF {file_path}: {e}")
        return None

def run_ocr_model(file_path: str) -> str:
    """Заглушка для корпоративной модели unlimited-ocr (bit)"""
    return "Текст со скана пока недоступен (Модель unlimited-ocr не подключена)."