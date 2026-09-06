"""
context_manager.py - Global Context Manager to maintain document state and chapter-to-chapter continuity.
"""

from typing import Dict, List, Optional
import re


class ContextManager:
    """
    Управляет глобальным контекстом документа во время пошаговой генерации.
    Сохраняет краткие резюме сгенерированных разделов, ключевые термины,
    сформулированные выводы и список использованных источников.
    """

    def __init__(self, topic: str, doc_type: str = "", subject: str = ""):
        self.topic = topic
        self.doc_type = doc_type
        self.subject = subject
        self.section_summaries: Dict[str, str] = {}
        self.key_concepts: Dict[str, str] = {}
        self.used_sources: List[str] = []

    def record_section_summary(self, section_id: str, title: str, text: str) -> str:
        """
        Извлекает 3-5 ключевых предложений из текста раздела и сохраняет резюме.
        """
        if not text:
            summary = "Раздел не содержит текста."
        else:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15]
            if len(sentences) <= 4:
                summary = " ".join(sentences)
            else:
                first = sentences[:2]
                mid = sentences[len(sentences) // 2]
                last = sentences[-1]
                summary = " ".join(first + [mid, last])
        
        self.section_summaries[section_id] = f"Раздел «{title}»: {summary}"
        return summary

    def get_global_context_prompt(self, current_section_id: str = "") -> str:
        """
        Формирует фрагмент промпта с информацией о предыдущих разделах работы.
        """
        if not self.section_summaries:
            return ""

        context_lines = [
            "\n╔══════════════════════════════════════════════════════════════════╗",
            "║  🌐 КОНТЕКСТ УЖЕ НАПИСАННЫХ РАЗДЕЛОВ (НЕ ПОВТОРЯЙ ИХ СОДЕРЖАНИЕ) ║",
            "╚══════════════════════════════════════════════════════════════════╝",
        ]

        for sec_id, summary in self.section_summaries.items():
            if sec_id != current_section_id:
                context_lines.append(f"• {summary}")

        if self.key_concepts:
            context_lines.append("\nКЛЮЧЕВЫЕ ОПРЕДЕЛЕНИЯ И КОНЦЕПЦИИ В РАБОТЕ:")
            for concept, defn in self.key_concepts.items():
                context_lines.append(f"• {concept}: {defn}")

        context_lines.append(
            "\n⚠️ ТРЕБОВАНИЕ СВЯЗНОСТИ: Учитывай вышеизложенное. Развивай мысль дальше, "
            "не дублируй вводные слова, выводы и аргументы из предыдущих разделов.\n"
        )

        return "\n".join(context_lines)

    def record_key_concept(self, concept: str, definition: str):
        """Сохраняет ключевое понятие и его определение."""
        if concept and definition:
            self.key_concepts[concept.strip()] = definition.strip()
