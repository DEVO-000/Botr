"""
structure_generator.py - Generates JSON structure and formats document structure blocks.
"""

import json
import re
from typing import List, Dict, Any, Tuple


class StructureGenerator:
    """
    Класс для генерации структуры (плана) документа и построения блоков структуры.
    """

    @staticmethod
    def get_default_chapter_titles(doc_type: str, topic: str, num_chapters: int) -> List[Dict[str, Any]]:
        """Возвращает базовые названия глав и подглав в качестве фоллбэка."""
        if num_chapters <= 1:
            return [{
                "title": f"1 Основные аспекты исследования темы «{topic}»",
                "subs": [
                    f"1.1 Понятие и сущность изучаемой проблемы",
                    f"1.2 Современное состояние и практические примеры",
                ]
            }]
        elif num_chapters == 2:
            return [
                {
                    "title": f"1 Теоретические основы исследования проблемы «{topic}»",
                    "subs": [
                        "1.1 Понятие, сущность и ключевые категории",
                        "1.2 Нормативно-правовое и методологическое обеспечение",
                    ]
                },
                {
                    "title": f"2 Практический анализ и направления совершенствования",
                    "subs": [
                        "2.1 Анализ текущего состояния и ключевых показателей",
                        "2.2 Проблемы и перспективы развития",
                    ]
                }
            ]
        else:
            return [
                {
                    "title": f"1 Теоретико-методологические основы проблемы «{topic}»",
                    "subs": [
                        "1.1 Понятие, сущность и классификация",
                        "1.2 Методы и подходы к исследованию",
                    ]
                },
                {
                    "title": f"2 Анализ современного состояния изучаемого объекта",
                    "subs": [
                        "2.1 Общая характеристика и нормативное регулирование",
                        "2.2 Оценка основных показателей и практический опыт",
                    ]
                },
                {
                    "title": f"3 Перспективы и рекомендации по совершенствованию",
                    "subs": [
                        "3.1 Выявленные проблемы и пути их решения",
                        "3.2 Оценка эффективности предлагаемых мероприятий",
                    ]
                }
            ]

    @staticmethod
    def parse_structure_json(raw_text: str) -> List[Dict[str, Any]]:
        """Извлекает и валидирует JSON-структуру из ответа LLM."""
        if not raw_text:
            return []
        
        cleaned = raw_text.strip()
        m = re.search(r"\[.*\]", cleaned, flags=re.S)
        if m:
            cleaned = m.group(0)

        try:
            result = json.loads(cleaned)
            if isinstance(result, list) and all("title" in r for r in result):
                return result
        except Exception:
            pass

        return []

    @staticmethod
    def generate_docx_blocks(
        doc_type: str,
        parts: Dict[str, str],
        chapter_titles: List[Dict[str, Any]],
        topic: str = "",
    ) -> List[Tuple[str, int, str, List[Tuple[str, str]]]]:
        """
        Возвращает список блоков для DOCX:
        (заголовок, уровень_heading, текст_абзаца, список_подглав)
        """
        if doc_type == "esse":
            main_text = parts.get("main1", "") + "\n\n" + parts.get("main2", "")
            return [
                ("ВВЕДЕНИЕ", 1, parts.get("intro", ""), []),
                ("ОСНОВНАЯ ЧАСТЬ", 1, main_text, []),
                ("ЗАКЛЮЧЕНИЕ", 1, parts.get("conclusion", ""), []),
                ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, parts.get("literature", ""), []),
            ]

        if doc_type == "doklad":
            return [
                ("ВВЕДЕНИЕ", 1, parts.get("intro", ""), []),
                ("1. Теоретические основы и ключевые понятия", 1, parts.get("part1", ""), []),
                ("2. Факты, статистика и практические примеры", 1, parts.get("part2", ""), []),
                ("ЗАКЛЮЧЕНИЕ", 1, parts.get("conclusion", ""), []),
                ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, parts.get("literature", ""), []),
            ]

        if doc_type == "article":
            return [
                ("АННОТАЦИЯ И КЛЮЧЕВЫЕ СЛОВА / ABSTRACT AND KEYWORDS", 1, parts.get("abstract", ""), []),
                ("ВВЕДЕНИЕ", 1, parts.get("intro", ""), []),
                ("ОБЗОР ЛИТЕРАТУРЫ", 1, parts.get("lit_review", ""), []),
                ("МЕТОДОЛОГИЯ ИССЛЕДОВАНИЯ", 1, parts.get("methodology", ""), []),
                ("РЕЗУЛЬТАТЫ И ИХ ОБСУЖДЕНИЕ", 1, parts.get("results", ""), []),
                ("ЗАКЛЮЧЕНИЕ", 1, parts.get("conclusion", ""), []),
                ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, parts.get("literature", ""), []),
            ]

        blocks = [("ВВЕДЕНИЕ", 1, parts.get("intro", ""), [])]

        for i, ch in enumerate(chapter_titles, start=1):
            subs_data = []
            for j, sub_title in enumerate(ch.get("subs", []), start=1):
                sub_text = parts.get(f"ch{i}_s{j}", "")
                subs_data.append((sub_title, sub_text))
            
            ch_text = parts.get(f"ch{i}", "")
            blocks.append((ch.get("title", f"{i} Глава {i}"), 1, ch_text, subs_data))

        blocks.append(("ЗАКЛЮЧЕНИЕ", 1, parts.get("conclusion", ""), []))
        blocks.append(("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, parts.get("literature", ""), []))

        return blocks
