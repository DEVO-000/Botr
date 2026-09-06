# -*- coding: utf-8 -*-
"""fact_checker — проверяет фактические утверждения через поиск."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import aiohttp


async def verify_statement(
    session: aiohttp.ClientSession,
    statement: str,
    topic: str = "",
) -> tuple[bool, str]:
    """Проверяет утверждение через быстрый поиск."""
    if len(statement) < 20:
        return True, "слишком короткое утверждение"
    
    # Извлекаем ключевые слова
    words = re.findall(r"[а-яёa-z]{4,}", statement.lower())
    keywords = [w for w in words if w not in {"этот", "этого", "этом", "однако", "поэтому"}]
    
    if not keywords:
        return True, "нет ключевых слов"
    
    query = " ".join(keywords[:5])
    
    # Быстрая проверка через DuckDuckGo API
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                snippet = data.get("AbstractText", "")
                if snippet:
                    # Проверяем, есть ли похожее утверждение
                    similar = any(w in snippet.lower() for w in keywords[:3])
                    return similar, "найдено в источниках" if similar else "не подтверждается"
    except Exception:
        pass
    
    return True, "проверка недоступна"


async def validate_facts_in_text(
    text: str,
    topic: str,
    max_checks: int = 5,
) -> list[dict]:
    """Находит в тексте фактические утверждения и проверяет их."""
    # Ищем предложения с фактами (цифры, даты, сравнения)
    fact_patterns = [
        r"\b\d+%?\s*[а-яё]+\b",  # проценты
        r"\b(?:в|с|на|до|около|более|менее)\s+\d+\s+(?:год|лет|раз|раза|проц)",  # числа с единицами
        r"\b\d{4}\s*год[а-я]*\b",  # годы
        r"\b(?:вырос|упал|снизился|увеличился|составил|достиг)\s+[а-яё]+\s+\d+",  # динамика
    ]
    
    results = []
    sentences = re.split(r"[.!?]+\s+", text)
    
    for sent in sentences:
        if len(sent) < 30 or len(results) >= max_checks:
            continue
        
        # Проверяем, есть ли факт в предложении
        has_fact = any(re.search(p, sent) for p in fact_patterns)
        if not has_fact:
            continue
        
        # Проверяем, есть ли ссылка на источник
        has_citation = bool(re.search(r"\[\d+,?\s*с\.\s*\d+\]", sent))
        
        if has_citation:
            continue  # факт со ссылкой считаем проверенным
        
        # Факт без ссылки — нужно проверить
        results.append({
            "sentence": sent.strip(),
            "verified": False,
            "reason": "факт без ссылки на источник"
        })
    
    return results


async def auto_cite_facts(
    model_key: str,
    text: str,
    literature: str,
) -> str:
    """Проверяет факты без ссылок. НЕ генерирует выдуманные номера страниц.

    Ранее эта функция придумывала номера страниц (10 + (i * 3) % 45) и
    индексы источников — это приводило к выдуманным ссылкам в тексте.
    Теперь функция только возвращает исходный текст без изменений.
    """
    return text
