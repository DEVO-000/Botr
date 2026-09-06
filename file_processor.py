# -*- coding: utf-8 -*-
"""file_processor.py — обработка загруженных файлов (PDF, TXT) как единственного источника."""

from __future__ import annotations

import io
import re
from typing import Tuple, List, Dict, Any

import fitz  # PyMuPDF


class FileProcessor:
    """Обрабатывает загруженные пользователем файлы как единственный источник."""

    @staticmethod
    async def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 50000) -> Tuple[str, List[Dict]]:
        """Извлекает текст и изображения из PDF."""
        text_parts = []
        images = []
        
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page_num, page in enumerate(doc):
                # Извлекаем текст
                page_text = page.get_text("text")
                if page_text.strip():
                    text_parts.append(page_text.strip())
                
                # Извлекаем изображения
                for img_info in page.get_images(full=True):
                    try:
                        base = doc.extract_image(img_info[0])
                        img_bytes = base.get("image")
                        if img_bytes and len(img_bytes) > 2000:
                            images.append({
                                "bytes": img_bytes,
                                "page": page_num + 1,
                                "caption": f"Иллюстрация со стр. {page_num + 1}"
                            })
                    except Exception:
                        continue
            
            doc.close()
            
            full_text = "\n\n".join(text_parts)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)
            
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars].rsplit(" ", 1)[0] + "…"
            
            return full_text, images
            
        except Exception as e:
            print(f"[FILE_PROCESSOR] Ошибка извлечения из PDF: {e}")
            return "", []

    @staticmethod
    async def extract_text_from_txt(txt_bytes: bytes, max_chars: int = 50000) -> str:
        """Извлекает текст из TXT файла."""
        try:
            text = txt_bytes.decode("utf-8", errors="replace")
            text = re.sub(r"\n{3,}", "\n\n", text)
            
            if len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + "…"
            
            return text
        except Exception as e:
            print(f"[FILE_PROCESSOR] Ошибка извлечения из TXT: {e}")
            return ""

    @staticmethod
    def validate_user_literature(content: str) -> Tuple[bool, str]:
        """Проверяет пользовательский список литературы."""
        if not content or not content.strip():
            return False, "❌ Список литературы пуст."
        
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        
        if len(lines) < 3:
            return False, "❌ Слишком мало источников. Введите минимум 3."
        
        has_content = any(re.search(r"[А-Яа-яёA-Za-z]{4,}", l) for l in lines)
        if not has_content:
            return False, "❌ Список похож на мусор. Введите реальные источники."
        
        return True, ""

    @staticmethod
    def detect_file_type(file_name: str, mime_type: str) -> str:
        """Определяет тип файла."""
        file_name = (file_name or "").lower()
        mime_type = (mime_type or "").lower()
        
        if file_name.endswith(".pdf") or mime_type == "application/pdf":
            return "pdf"
        if file_name.endswith(".txt") or mime_type == "text/plain":
            return "txt"
        if file_name.endswith((".docx", ".doc")) or "wordprocessingml" in mime_type:
            return "docx"
        
        return "unknown"
