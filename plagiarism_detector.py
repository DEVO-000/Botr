# -*- coding: utf-8 -*-
"""plagiarism_detector — детектирует и исправляет плагиат в тексте."""

from __future__ import annotations

import hashlib
import re
from collections import Counter


class PlagiarismDetector:
    """Обнаруживает и исправляет плагиат."""
    
    def __init__(self, db_path: str = "plagiarism_db.json"):
        self.db_path = db_path
        self.db = self._load_db()
        self.fingerprints = {}
    
    def _load_db(self) -> dict:
        """Загружает базу известных фраз."""
        # В реальности здесь загружается база из файла
        return {
            "common_phrases": [
                "актуальность темы обусловлена",
                "степень разработанности проблемы",
                "цель работы заключается",
                "объектом исследования является",
                "предметом исследования выступает",
                "в современных условиях",
                "необходимо отметить что",
                "следует отметить что",
                "таким образом можно сделать вывод",
                "проведенный анализ показал",
            ]
        }
    
    def detect_plagiarism(self, text: str) -> list[dict]:
        """Находит потенциальный плагиат в тексте."""
        matches = []
        text_lower = text.lower()
        
        # Проверяем наличие общих фраз
        for phrase in self.db.get("common_phrases", []):
            if phrase in text_lower:
                matches.append({
                    "phrase": phrase,
                    "type": "common_template",
                    "severity": "warning",
                })
        
        # Проверяем повторяющиеся фразы внутри текста
        sentences = re.split(r"[.!?]+\s+", text)
        if len(sentences) > 10:
            counter = Counter(sentences)
            for sent, count in counter.items():
                if count > 1 and len(sent) > 30:
                    matches.append({
                        "phrase": sent[:100],
                        "type": "self_plagiarism",
                        "severity": "error",
                        "count": count,
                    })
        
        return matches
    
    async def fix_plagiarism(
        self,
        text: str,
        model_key: str,
        chat_fn: Any,
    ) -> str:
        """Исправляет найденный плагиат."""
        matches = self.detect_plagiarism(text)
        if not matches:
            return text
        
        print(f"[PLAGIARISM] Найдено {len(matches)} проблемных мест")
        
        # Переписываем каждый фрагмент
        for match in matches[:3]:
            if match["severity"] == "error":
                phrase = match["phrase"]
                prompt = f"""
                Перепиши следующий фрагмент, чтобы он был оригинальным:
                "{phrase}"
                
                Сохрани смысл, но измени формулировку.
                Верни только переписанный фрагмент.
                """
                messages = [
                    {"role": "system", "content": "Ты редактор. Переписывай текст, сохраняя смысл."},
                    {"role": "user", "content": prompt}
                ]
                fixed, _ = await chat_fn(model_key, messages, 1024)
                if fixed:
                    text = text.replace(phrase, fixed.strip())
        
        return text
