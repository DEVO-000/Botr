"""
post_processor.py - Quality post-processing, semantic expansion/compression, humanization, and quality gates.
"""

from typing import Dict, Any, List, Tuple, Optional
import re
import os
import text_utils
import citation_utils
import gost_utils


class PostProcessor:
    """
    Класс обработки и подгонки результатов генерации.
    Смещает акцент с механического добора символов на смысловую подгонку текста.
    """

    @staticmethod
    def clean_and_format_parts(parts: Dict[str, str]) -> Dict[str, str]:
        """Очищает и форматирует все блоки текста."""
        cleaned = {}
        for key, text in parts.items():
            if key == "literature":
                cleaned[key] = text
                continue
            if isinstance(text, str):
                t = text_utils.sanitize_llm_text(text)
                t = text_utils.remove_ai_marker_phrases(t)
                t = text_utils.remove_duplicate_phrases(t)
                t = text_utils.normalize_typography(t)
                t = citation_utils.repair_broken_citations(t)
                cleaned[key] = t
            else:
                cleaned[key] = text

        cleaned = citation_utils.final_citation_check(cleaned)
        return cleaned

    @staticmethod
    def build_semantic_expansion_prompt(text: str, topic: str, target_added_chars: int) -> str:
        """Промпт для смыслового расширения текста без генерирования «воды»."""
        return (
            f"Перепиши и расширь следующий научный текст по теме «{topic}».\n\n"
            f"ИСХОДНЫЙ ТЕКСТ:\n{text}\n\n"
            f"ТРЕБОВАНИЯ:\n"
            f"1. Добавь {target_added_chars} знаков осмысленного текста.\n"
            f"2. Добавь 2 новых научных аргумента, факта или статистических примера.\n"
            f"3. СОХРАНИ ВСЕ СУЩЕСТВУЮЩИЕ ССЫЛКИ вида [N, с. X].\n"
            f"4. Не используй воду, клише и вводные слова (сегодня, в современном мире).\n"
            f"5. Каждое новое предложение должно нести научную ценность.\n"
        )

    @staticmethod
    def build_semantic_compression_prompt(text: str, topic: str, target_removed_chars: int) -> str:
        """Промпт для смыслового сжатия текста без потери фактов и ссылок."""
        return (
            f"Сократи следующий научный текст по теме «{topic}».\n\n"
            f"ИСХОДНЫЙ ТЕКСТ:\n{text}\n\n"
            f"ТРЕБОВАНИЯ:\n"
            f"1. Сократи текст примерно на {target_removed_chars} знаков.\n"
            f"2. Убери повторы, водность и слишком длинные пояснения.\n"
            f"3. СОХРАНИ ВСЕ ФАКТЫ И ССЫЛКИ вида [N, с. X].\n"
            f"4. Сохрани академический стиль и логическую связность.\n"
        )
