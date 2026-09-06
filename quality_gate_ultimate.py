# -*- coding: utf-8 -*-
"""quality_gate_ultimate — финальный контроль качества с автоправками."""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable


class UltimateQualityGate:
    """Финальная проверка с автоматическими правками."""
    
    def __init__(self):
        self.issues = []
        self.fixes = []
    
    async def check_and_fix(
        self,
        parts: dict[str, str],
        topic: str,
        subject: str,
        model_key: str,
        chat_fn: Callable[..., Awaitable[tuple[str, str]]],
        max_attempts: int = 3,
    ) -> tuple[dict[str, str], list[str]]:
        """Проверяет и исправляет ВСЕ проблемы."""
        
        for attempt in range(max_attempts):
            self.issues = []
            
            # Проверяем каждый раздел
            for key, text in parts.items():
                if key == "literature":
                    continue
                self._analyze_section(key, text, topic, subject)
            
            if not self.issues:
                print(f"[QUALITY] ✅ Все проверки пройдены (попытка {attempt+1})")
                return parts, self.fixes
            
            print(f"[QUALITY] ⚠️ Найдено {len(self.issues)} проблем (попытка {attempt+1})")
            
            # Исправляем проблемы
            for issue in self.issues[:5]:  # максимум 5 правок за раз
                await self._fix_issue(parts, issue, model_key, chat_fn)
        
        return parts, self.fixes
    
    def _analyze_section(self, key: str, text: str, topic: str, subject: str):
        """Анализирует один раздел."""
        
        # 1. Объём
        words = len(text.split())
        if words < 50 and key not in ("literature",):
            self.issues.append({
                "section": key,
                "type": "volume",
                "severity": "critical",
                "description": f"Слишком коротко ({words} слов)",
                "text": text,
            })
        
        # 2. Ссылки
        citations = re.findall(r"\[\d+,\s*с\.\s*\d+\]", text)
        if len(citations) < 2 and key not in ("literature", "conclusion"):
            self.issues.append({
                "section": key,
                "type": "citations",
                "severity": "critical",
                "description": f"Мало ссылок ({len(citations)})",
                "text": text,
            })
        
        # 3. Клише
        cliches = [
            "в современном мире", "необходимо отметить", "следует отметить",
            "таким образом", "играет важную роль", "имеет важное значение",
            "комплексный подход", "широкий спектр", "актуальность обусловлена",
        ]
        found = [c for c in cliches if c in text.lower()]
        if found:
            self.issues.append({
                "section": key,
                "type": "cliches",
                "severity": "medium",
                "description": f"Клише: {', '.join(found[:3])}",
                "text": text,
            })
        
        # 4. Соответствие теме (токенный подход).
        # ФИКС: старая проверка `topic[:20] in text` давала ложные «critical»
        # на склонениях («рынок труда» ≠ «рынка труда») и на коротких темах.
        # Теперь: хотя бы одно ЗНАЧИМОЕ слово темы (не предлог, не стоп-слово)
        # должно присутствовать в разделе; для заключения/аннотации проверка
        # не применяется — там повторение темы необязательно по ГОСТ.
        if topic and key not in ("conclusion", "abstract"):
            topic_words = {
                w for w in re.findall(r"[а-яёa-z]{5,}", topic.lower())
                if w not in ("котор", "также", "каков", "почему")
            }
            text_low = text.lower()
            if topic_words and not any(w[:5] in text_low for w in topic_words):
                self.issues.append({
                    "section": key,
                    "type": "relevance",
                    "severity": "critical",
                    "description": "Не соответствует теме (нет значимых слов темы)",
                    "text": text,
                })
        
        # 5. Оборванные ссылки
        if re.search(r"\[\d+,\s*с\.\s*$", text):
            self.issues.append({
                "section": key,
                "type": "broken_citation",
                "severity": "critical",
                "description": "Оборванная ссылка",
                "text": text,
            })
    
    async def _fix_issue(
        self,
        parts: dict[str, str],
        issue: dict,
        model_key: str,
        chat_fn: Callable[..., Awaitable[tuple[str, str]]],
    ):
        """Исправляет конкретную проблему."""
        
        key = issue["section"]
        text = parts.get(key, "")
        
        if issue["type"] == "volume":
            # Дополняем текст
            prompt = f"""
            Дополни следующий текст, раскрой тему:
            
            {text}
            
            Добавь 3-5 предложений, раскрывающих тему.
            Верни только дополненный текст.
            """
            messages = [
                {"role": "system", "content": "Ты академический автор. Дописывай текст содержательно."},
                {"role": "user", "content": prompt}
            ]
            fixed, _ = await chat_fn(model_key, messages, 2048)
            if fixed and len(fixed.split()) > len(text.split()):
                parts[key] = fixed
                self.fixes.append(f"Дополнен раздел {key}")
        
        elif issue["type"] == "citations":
            # ЧЕСТНАЯ ПОЛИТИКА (v3.4): просьба «добавь ссылки [N, с. X]»
            # заставляла модель ВЫДУМЫВАТЬ страницы — это нарушало главный
            # принцип бота «никаких несуществующих источников». Ссылки
            # проставляются на этапе генерации из проверенного списка
            # литературы; здесь только диагностика.
            print(
                f"[QUALITY] {key}: мало ссылок ({len(re.findall(r'\[\d+,\s*с\.\s*\d+\]', text))}) — "
                "авто-добавление отключено, чтобы не фабриковать страницы"
            )
        
        elif issue["type"] == "cliches":
            # Убираем клише
            from humanizer import remove_cliches
            fixed = remove_cliches(text)
            if fixed != text:
                parts[key] = fixed
                self.fixes.append(f"Убраны клише из {key}")
        
        elif issue["type"] == "broken_citation":
            # Исправляем оборванные ссылки
            fixed = re.sub(r"\[\d+,\s*с\.\s*$", "", text)
            if fixed != text:
                parts[key] = fixed
                self.fixes.append(f"Исправлены ссылки в {key}")
