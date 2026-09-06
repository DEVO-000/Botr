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
            # FIX (ГОСТ): раньше весь основной текст сваливался в один блок
            # «ОСНОВНАЯ ЧАСТЬ» — работа не выглядела сдаваемой. Теперь —
            # два пронумерованных раздела по теме (ГОСТ 7.32-2017), названия
            # приходят от ИИ (_generate_flat_section_titles).
            main1 = (parts.get("main1") or "").strip()
            main2 = (parts.get("main2") or "").strip()
            t1, t2 = "", ""
            if chapter_titles:
                titles = [str(c.get("title") or "").strip() for c in chapter_titles]
                titles = [t for t in titles if t]
                if len(titles) >= 2:
                    t1, t2 = titles[0], titles[1]
                elif len(titles) == 1:
                    t1 = titles[0]
            if not t1:
                t1 = f"1 Постановка проблемы «{topic}» и первый аргумент"
            if not t2:
                t2 = "2 Второй аргумент, контраргументы и авторская позиция"
            blocks: List[Tuple[str, int, str, List[Tuple[str, str]]]] = [
                ("ВВЕДЕНИЕ", 1, parts.get("intro", ""), []),
            ]
            if main1:
                blocks.append((t1, 1, main1, []))
            if main2:
                blocks.append((t2, 1, main2, []))
            blocks.extend([
                ("ЗАКЛЮЧЕНИЕ", 1, parts.get("conclusion", ""), []),
                ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, parts.get("literature", ""), []),
            ])
            return blocks

        if doc_type == "doklad":
            part1 = (parts.get("part1") or "").strip()
            part2 = (parts.get("part2") or "").strip()
            t1, t2 = "", ""
            if chapter_titles:
                titles = [str(c.get("title") or "").strip() for c in chapter_titles]
                titles = [t for t in titles if t]
                if len(titles) >= 2:
                    t1, t2 = titles[0], titles[1]
                elif len(titles) == 1:
                    t1 = titles[0]
            if not t1:
                t1 = f"1 Ключевые понятия и теоретические основы темы «{topic}»"
            if not t2:
                t2 = f"2 Факты, статистика и практические примеры по теме «{topic}»"
            blocks = [("ВВЕДЕНИЕ", 1, parts.get("intro", ""), [])]
            if part1:
                blocks.append((t1, 1, part1, []))
            if part2:
                blocks.append((t2, 1, part2, []))
            blocks.extend([
                ("ЗАКЛЮЧЕНИЕ", 1, parts.get("conclusion", ""), []),
                ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, parts.get("literature", ""), []),
            ])
            return blocks

        if doc_type == "article":
            # ГОСТ Р 7.0.7-2021: аннотация и ключевые слова на русском
            # (двуязычный заголовок «/ ABSTRACT AND KEYWORDS» в оглавлении
            # выглядел неряшливо и не соответствует оформлению заголовков).
            return [
                ("АННОТАЦИЯ И КЛЮЧЕВЫЕ СЛОВА", 1, parts.get("abstract", ""), []),
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
