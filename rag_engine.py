# -*- coding: utf-8 -*-
"""rag_engine — Retrieval-Augmented Generation: ИИ пишет по реальным текстам статей.

Как это работает:
1. По DOI из списка литературы скачиваем полные тексты (PDF)
2. Разбиваем на смысловые фрагменты (chunk'и)
3. Для каждого абзаца ищем релевантные chunk'и
4. ИИ генерирует текст строго на основе найденных фрагментов
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import aiohttp
import fitz  # PyMuPDF

try:
    from error_logger import log_error
except ImportError:
    def log_error(*args, **kwargs):
        pass

# Кэш загруженных текстов (чтобы не качать одно и то же)
_TEXT_CACHE: dict[str, str] = {}
_CACHE_FILE = "rag_cache.json"
_CACHE_MAX_SIZE = 100  # храним последние 100 статей


def _load_cache():
    global _TEXT_CACHE
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _TEXT_CACHE = json.load(f)
                print(f"[RAG] Загружен кэш: {len(_TEXT_CACHE)} статей")
    except Exception as e:
        print(f"[RAG] Не удалось загрузить кэш: {e}")


def _save_cache():
    global _TEXT_CACHE
    try:
        # Оставляем только последние _CACHE_MAX_SIZE записей
        if len(_TEXT_CACHE) > _CACHE_MAX_SIZE:
            items = list(_TEXT_CACHE.items())
            _TEXT_CACHE = dict(items[-_CACHE_MAX_SIZE:])
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_TEXT_CACHE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[RAG] Не удалось сохранить кэш: {e}")


_load_cache()


@dataclass
class Chunk:
    """Смысловой фрагмент текста из источника."""
    text: str
    source: str  # DOI или URL
    page: int
    score: float = 0.0  # релевантность для текущего запроса


async def fetch_pdf_by_doi(session: aiohttp.ClientSession, doi: str) -> bytes | None:
    """Скачивает PDF по DOI через Unpaywall (Официальный Open Access API)."""
    if not doi:
        return None
    
    # Проверяем кэш текста
    cache_key = f"doi:{doi}"
    if cache_key in _TEXT_CACHE:
        return None  # уже есть текст, не нужно качать PDF
    
    try:
        url = f"https://api.unpaywall.org/v2/{doi}?email=rag@example.com"
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                oa_url = data.get("best_oa_location", {}).get("url")
                if oa_url:
                    async with session.get(oa_url, timeout=30) as pdf_resp:
                        if pdf_resp.status == 200:
                            return await pdf_resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log_error(stage="rag_fetch_pdf", message=f"Unpaywall error for {doi}: {e}", exc_info=e)
        print(f"[RAG] Unpaywall error for {doi}: {e}")
    except Exception as e:
        log_error(stage="rag_fetch_pdf", message=f"Unexpected error for {doi}: {e}", exc_info=e)
        print(f"[RAG] Error fetching PDF for {doi}: {e}")
    
    return None


def extract_text_from_pdf(pdf_bytes: bytes) -> dict[str, str | list[dict]]:
    """Извлекает текст из PDF с помощью PyMuPDF (fitz)."""
    result = {
        "full_text": "",
        "pages": [],
    }
    
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(pdf)):
            page_text = pdf[page_num].get_text("text")
            if page_text.strip():
                result["pages"].append({
                    "num": page_num + 1,
                    "text": page_text.strip()
                })
                result["full_text"] += "\n\n" + page_text
        pdf.close()
        return result
    except Exception as e:
        log_error(stage="rag_pdf_extract", message=f"PyMuPDF extraction error: {e}", exc_info=e)
        print(f"[RAG] PDF extraction error: {e}")
        return result


async def download_and_extract_text(
    session: aiohttp.ClientSession, 
    doi: str,
    force: bool = False
) -> str | None:
    """Скачивает PDF по DOI и извлекает текст."""
    cache_key = f"doi:{doi}"
    
    # Проверяем кэш
    if not force and cache_key in _TEXT_CACHE:
        print(f"[RAG] Текст для {doi} взят из кэша")
        return _TEXT_CACHE[cache_key]
    
    pdf_bytes = await fetch_pdf_by_doi(session, doi)
    if not pdf_bytes:
        return None
    
    result = extract_text_from_pdf(pdf_bytes)
    if not result["full_text"].strip():
        return None
    
    # Сохраняем в кэш
    _TEXT_CACHE[cache_key] = result["full_text"]
    _save_cache()
    
    print(f"[RAG] Загружен текст для {doi}: {len(result['full_text'])} символов")
    return result["full_text"]


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Разбивает текст на перекрывающиеся chunk'и."""
    if not text:
        return []
    
    chunks = []
    words = text.split()
    
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks


def find_relevant_chunks(
    query: str,
    text: str,
    top_k: int = 5,
) -> list[Chunk]:
    """Находит наиболее релевантные chunk'и для запроса."""
    chunks = chunk_text(text)
    if not chunks:
        return []
    
    # Простой TF-IDF-подобный поиск
    query_words = set(re.findall(r"[а-яёa-z]{3,}", query.lower()))
    if not query_words:
        return []
    
    scored = []
    for i, chunk in enumerate(chunks):
        chunk_words = set(re.findall(r"[а-яёa-z]{3,}", chunk.lower()))
        if not chunk_words:
            continue
        
        intersection = len(query_words & chunk_words)
        union = len(query_words | chunk_words)
        score = intersection / union if union > 0 else 0
        
        scored.append((score, Chunk(
            text=chunk,
            source="",
            page=i + 1,
            score=score
        )))
    
    scored.sort(key=lambda x: x[0], reverse=True)
    return [chunk for score, chunk in scored[:top_k] if score > 0.1]


async def build_rag_context(
    model_key: str,
    topic: str,
    literature: str,
    session: aiohttp.ClientSession | None = None,
) -> dict[str, list[Chunk]]:
    """Строит RAG-контекст для всех разделов работы."""
    if not literature:
        return {}
    
    dois = re.findall(r"10\.\d{4,9}/\S+", literature)
    if not dois:
        print("[RAG] Не найдено DOI в списке литературы")
        return {}
    
    print(f"[RAG] Найдено {len(dois)} DOI: {', '.join(dois[:5])}...")
    
    own_session = False
    if session is None:
        session = aiohttp.ClientSession()
        own_session = True
    
    try:
        tasks = [download_and_extract_text(session, doi) for doi in dois[:5]]
        texts = await asyncio.gather(*tasks, return_exceptions=True)
        
        full_texts = []
        for doi, text in zip(dois, texts):
            if isinstance(text, str) and text.strip():
                full_texts.append(text)
        
        if not full_texts:
            print("[RAG] Не удалось загрузить ни одной статьи")
            return {}
        
        combined = "\n\n".join(full_texts)
        
        sections = {
            "intro": f"актуальность цель задачи объект предмет {topic}",
            "ch1": f"теоретические основы концепции термины {topic}",
            "ch2": f"анализ современное состояние тенденции {topic}",
            "ch3": f"практические аспекты решения рекомендации {topic}",
            "conclusion": f"выводы итоги результаты {topic}",
        }
        
        context = {}
        for section, query in sections.items():
            chunks = find_relevant_chunks(query, combined, top_k=3)
            if chunks:
                context[section] = chunks
        
        print(f"[RAG] Найдено контекстов: {sum(len(v) for v in context.values())}")
        return context
        
    finally:
        if own_session and session:
            await session.close()


def format_rag_context(chunks: list[Chunk]) -> str:
    """Форматирует chunk'и для вставки в промпт."""
    if not chunks:
        return ""
    
    lines = ["[ИЗ НАУЧНЫХ ИСТОЧНИКОВ:]\n"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"ФРАГМЕНТ {i}:")
        lines.append(chunk.text)
        lines.append("")
    
    return "\n".join(lines)
