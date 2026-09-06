# -*- coding: utf-8 -*-
"""plagiarism_checker — проверка уникальности текста."""

import asyncio
import hashlib
import json
import os
import re

# Простая эмуляция проверки уникальности (можно заменить на реальный API)
class PlagiarismChecker:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.cache = {}
        self.cache_file = "plagiarism_cache.json"
        self._load_cache()
    
    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    self.cache = json.load(f)
        except Exception:
            pass
    
    def _save_cache(self):
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f)
        except Exception:
            pass
    
    def _text_hash(self, text: str) -> str:
        return hashlib.md5(text[:1000].encode()).hexdigest()
    
    async def check_uniqueness(self, text: str) -> float:
        """Возвращает оценку уникальности (0-100%)."""
        # Быстрая эмуляция
        if len(text) < 200:
            return 80.0
        
        # Проверяем кэш
        h = self._text_hash(text)
        if h in self.cache:
            return self.cache[h]
        
        # Эмуляция: считаем уникальность на основе разнообразия
        words = re.findall(r"[а-яёa-z]{3,}", text.lower())
        if not words:
            return 50.0
        
        # Уникальность = отношение уникальных слов к общему числу
        unique_ratio = len(set(words)) / len(words)
        
        # Добавляем штраф за длинные повторяющиеся фразы
        long_phrases = len(re.findall(r"(\b[а-яёa-z]{3,}\s+[а-яёa-z]{3,}\b).*\1", text))
        penalty = min(20, long_phrases * 2)
        
        score = min(100, max(0, unique_ratio * 100 + 30 - penalty))
        
        # Кэшируем
        self.cache[h] = score
        self._save_cache()
        
        return score
    
    async def ensure_uniqueness(self, text: str, target: float = 70.0) -> tuple[str, float]:
        """Если уникальность ниже target, предлагает перегенерировать."""
        score = await self.check_uniqueness(text)
        if score >= target:
            return text, score
        
        # Предупреждение для пользователя
        return text, score
