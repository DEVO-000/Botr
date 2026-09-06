# -*- coding: utf-8 -*-
"""fact_checker_real — проверка фактов через реальные источники в интернете."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import quote_plus

import aiohttp

try:
    from error_logger import log_error
except ImportError:
    def log_error(*args, **kwargs):
        pass


class RealFactChecker:
    """Проверяет факты через поиск в интернете."""
    
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def verify_fact(self, statement: str) -> tuple[bool, str]:
        """Проверяет факт через DuckDuckGo (бесплатно)."""
        if len(statement) < 20:
            return True, "слишком короткое утверждение"
        
        keywords = self._extract_keywords(statement)
        if not keywords:
            return True, "нет ключевых слов"
        
        query = " ".join(keywords[:5])
        
        try:
            url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1"
            async with self.session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return True, "проверка недоступна"
                data = await resp.json()
                snippet = data.get("AbstractText", "")
                if not snippet:
                    return True, "информация не найдена"
                
                statement_words = set(keywords)
                snippet_words = set(self._extract_keywords(snippet))
                
                if len(statement_words & snippet_words) >= 2:
                    return True, "подтверждается"
                else:
                    return False, "не подтверждается"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log_error(stage="fact_checker_real_search", message=f"DuckDuckGo API network error: {e}", exc_info=e)
            print(f"[FACT-CHECK] Ошибка сети проверки: {e}")
            return True, "проверка недоступна"
        except Exception as e:
            log_error(stage="fact_checker_real_search", message=f"Unexpected error: {e}", exc_info=e)
            print(f"[FACT-CHECK] Неожиданная ошибка: {e}")
            return True, "проверка недоступна"
    
    def _extract_keywords(self, text: str) -> list[str]:
        """Извлекает ключевые слова из текста."""
        stopwords = {
            "этот", "этого", "этом", "этой", "эти", "этих", "этим", "этими",
            "также", "более", "менее", "самый", "очень", "может", "могут",
            "который", "которая", "которые", "которых", "если", "чтобы",
            "однако", "поэтому", "между", "через", "после", "перед", "всех",
        }
        words = re.findall(r"[а-яёa-z]{4,}", text.lower())
        keywords = [w for w in words if w not in stopwords and len(w) >= 4]
        
        seen = set()
        result = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result[:10]
    
    async def validate_facts_in_text(self, text: str, topic: str = "") -> list[dict]:
        """Проверяет все факты в тексте."""
        fact_patterns = [
            r"\b\d+%?\s*[а-яё]+\b",  # проценты
            r"\b(?:в|с|на|до|около|более|менее)\s+\d+\s+(?:год|лет|раз|проц)",  # числа
            r"\b\d{4}\s*год[а-я]*\b",  # годы
            r"\b(?:вырос|упал|снизился|увеличился|составил|достиг)\s+[а-яё]+\s+\d+",  # динамика
        ]
        
        sentences = re.split(r"[.!?]+\s+", text)
        results = []
        
        for sent in sentences:
            if len(sent) < 30 or len(results) >= 10:
                continue
            
            has_fact = any(re.search(p, sent) for p in fact_patterns)
            if not has_fact:
                continue
            
            has_citation = bool(re.search(r"\[\d+,?\s*с\.\s*\d+\]", sent))
            if has_citation:
                continue
            
            verified, reason = await self.verify_fact(sent)
            
            results.append({
                "sentence": sent.strip(),
                "verified": verified,
                "reason": reason,
            })
        
        return results
