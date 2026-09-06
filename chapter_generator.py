"""
chapter_generator.py - Independent context-aware chapter generator module.
"""

from typing import Dict, Any, List, Optional
from gost_utils import words_for_chars, calculate_chars_per_page
from gost_rules import gost_text_rules_prompt
from context_manager import ContextManager
import re


class ChapterGenerator:
    """
    Генератор отдельных глав и подразделов с глубоким контекстным управлением.
    """

    @staticmethod
    def _style_instruction(writing_style: str = "classic", doc_type: str = "") -> str:
        if writing_style == "simple":
            return (
                "Пиши простым, понятным языком, избегай слишком громоздких академических деепричастных "
                "оборотов и 'канцелярита'. Объясняй термины простыми словами, но сохраняй научную точность."
            )
        elif writing_style == "deep":
            return (
                "Пиши глубоким академическим языком: используй развитый категориально-понятийный аппарат, "
                "историографический и методологический анализ, ссылки на научные школы и дискуссии."
            )
        return (
            "Пиши классическим академическим стилем: строго, объективно, с логичной аргументацией "
            "и безличным изложением."
        )

    @classmethod
    def strict_prompt(
        cls,
        task: str,
        chars: int,
        writing_style: str = "classic",
        doc_type: str = "",
        context_manager: Optional[ContextManager] = None,
        section_id: str = "",
    ) -> str:
        """
        Формирует строгий промпт с учетом глобального контекста предыдущих глав.
        """
        style_instr = cls._style_instruction(writing_style, doc_type)

        chars_min = max(200, int(chars * 0.90))
        chars_max = int(chars * 1.05)
        est_pages = max(1, round(chars / calculate_chars_per_page(1, doc_type), 1))
        words_target = words_for_chars(chars)
        words_min = words_for_chars(chars_min)
        words_max = words_for_chars(chars_max)
        paragraphs_target = max(3, round(chars / 600))

        global_ctx = ""
        if context_manager:
            global_ctx = context_manager.get_global_context_prompt(section_id)

        base = (
            f"{task}\n\n"
            f"{global_ctx}"
            "╔══════════════════════════════════════════════════════════════════╗\n"
            "║  ❗ ЭТОТ БЛОК ДОЛЖЕН БЫТЬ НАПИСАН СТРОГО ПО ПРАВИЛАМ НИЖЕ     ║\n"
            "╚══════════════════════════════════════════════════════════════════╝\n\n"
            "1️⃣ ССЫЛКИ (САМОЕ ВАЖНОЕ!):\n"
            "   📌 КАЖДАЯ ссылка — ТОЛЬКО [N, с. X] или [N, с. X–Y].\n"
            "   ❌ ЗАПРЕЩЕНО: [N], [N, с. ], [N, c. X], [N, с. без цифры.\n"
            "   📌 Если не знаешь страницу — НЕ СТАВЬ ССЫЛКУ.\n\n"
            "2️⃣ ОБЪЁМ И СОДЕРЖАНИЕ:\n"
            f"   • ЦЕЛЬ: {words_target} слов ({chars} знаков, ~{est_pages} стр.)\n"
            f"   • ДОПУСТИМО: {words_min}–{words_max} слов\n"
            f"   • АБЗАЦЕВ: {paragraphs_target} (±1)\n"
            "   • ЗАПРЕЩЕНО писать «развёрнуто», «подробно» без содержания.\n"
            "   • ЗАПРЕЩЕНО добивать объём повторами и водой.\n\n"
            "3️⃣ СТИЛЬ И ТРЕБОВАНИЯ К ФАКТАМ:\n"
            f"   {style_instr}\n"
            "   • СТРОГО ЗАПРЕЩЕНЫ клише: «в современном мире», «необходимо отметить»,\n"
            "     «таким образом», «следует подчеркнуть», «играет важную роль».\n"
            "   • ТРЕБУЮТСЯ: конкретные статистические данные, даты, законодательные акты,\n"
            "     конкретные фамилии авторов и результаты исследований.\n\n"
            "4️⃣ ЗАГОЛОВКИ И СТРУКТУРА:\n"
            "   • БЕЗ точки после номера: «1 Название», «1.1 Название».\n"
            "   • БЕЗ точки в конце заголовка.\n\n"
            "5️⃣ ФОРМАТИРОВАНИЕ:\n"
            "   • ЗАПРЕЩЕН markdown (#, **, *, ```).\n"
            "   • Кавычки — только «ёлочки».\n"
            "   • Тире — длинное (—) с пробелами.\n\n"
            + gost_text_rules_prompt(doc_type)
        )

        return base
