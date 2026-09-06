# -*- coding: utf-8 -*-
"""rag_full — загрузка ПОЛНЫХ текстов статей и генерация на их основе.

Это ключевой модуль для борьбы с галлюцинациями.
ИИ пишет текст, ОПИРАЯСЬ ТОЛЬКО на реальные тексты источников.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp
import fitz  # PyMuPDF

try:
    from error_logger import log_error
except ImportError:
    def log_error(*args, **kwargs):
        pass


class FullTextRAG:
    """Загружает полные тексты статей и использует их для генерации."""
    
    def __init__(self):
        self.cache = {}
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def fetch_full_text(self, doi: str) -> str | None:
        """Скачивает полный текст статьи по DOI."""
        if doi in self.cache:
            return self.cache[doi]
        
        # Пробуем Unpaywall (Официальный Open Access API)
        text = await self._fetch_via_unpaywall(doi)
        if text:
            self.cache[doi] = text
            return text
        
        return None
    
    async def _fetch_via_unpaywall(self, doi: str) -> str | None:
        """Скачивает через Unpaywall (бесплатный API)."""
        try:
            url = f"https://api.unpaywall.org/v2/{doi}?email=rag@example.com"
            async with self.session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                oa_url = data.get("best_oa_location", {}).get("url")
                if not oa_url:
                    return None
                
                # Скачиваем PDF
                async with self.session.get(oa_url, timeout=30) as pdf_resp:
                    if pdf_resp.status != 200:
                        return None
                    pdf_bytes = await pdf_resp.read()
                    return self._extract_text_from_pdf(pdf_bytes)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log_error(stage="rag_full_unpaywall", message=f"Unpaywall error for {doi}: {e}", exc_info=e)
            print(f"[RAG-FULL] Unpaywall error: {e}")
            return None
        except Exception as e:
            log_error(stage="rag_full_unpaywall", message=f"Unexpected error for {doi}: {e}", exc_info=e)
            print(f"[RAG-FULL] Unexpected error: {e}")
            return None
    
    def _extract_text_from_pdf(self, pdf_bytes: bytes) -> str | None:
        """Извлекает полный текст из PDF с помощью PyMuPDF (fitz)."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text_parts = []
            for page in doc:
                text = page.get_text("text")
                if text.strip():
                    text_parts.append(text.strip())
            doc.close()
            
            if not text_parts:
                return None
            
            full_text = "\n\n".join(text_parts)
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)
            return full_text
        except Exception as e:
            log_error(stage="rag_full_pdf_extract", message=f"PDF extraction error: {e}", exc_info=e)
            print(f"[RAG-FULL] PDF extraction error: {e}")
            return None
    
    async def generate_with_sources(
        self,
        topic: str,
        literature: str,
        model_key: str,
        chat_fn: Any,
    ) -> str:
        """Генерирует текст, ОПИРАЯСЬ ТОЛЬКО на загруженные статьи."""
        
        dois = re.findall(r"10\.\d{4,9}/\S+", literature)
        if not dois:
            print("[RAG-FULL] Нет DOI для загрузки")
            return ""
        
        print(f"[RAG-FULL] Загружаю {len(dois[:3])} статей...")
        
        texts = []
        for doi in dois[:3]:  # максимум 3 статьи для скорости
            text = await self.fetch_full_text(doi)
            if text:
                texts.append(f"=== ИСТОЧНИК (DOI: {doi}) ===\n{text[:5000]}")
                print(f"[RAG-FULL] Загружена статья {doi} ({len(text)} символов)")
        
        if not texts:
            print("[RAG-FULL] Не удалось загрузить ни одной статьи")
            return ""
        
        source_text = "\n\n".join(texts)
        
        prompt = f"""
        Тема работы: {topic}
        
        НА ОСНОВЕ СЛЕДУЮЩИХ НАУЧНЫХ ИСТОЧНИКОВ НАПИШИ ТЕКСТ:
        
        {source_text[:15000]}
        
        ПРАВИЛА:
        1. Используй ТОЛЬКО информацию из этих источников
        2. Если информации нет — напиши "Данных недостаточно"
        3. Не выдумывай факты
        4. Сохраняй научный стиль
        5. Добавляй ссылки на источники [1, с. X]
        """
        
        messages = [
            {"role": "system", "content": "Ты академический автор. Пиши строго по предоставленным научным источникам. Не выдумывай факты."},
            {"role": "user", "content": prompt}
        ]
        
        text, _ = await chat_fn(model_key, messages, 8192)
        return text if text else ""
