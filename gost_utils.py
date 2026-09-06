"""
gost_utils.py - GOST rules helpers, page mapping, page count estimators, and formatting helpers.
"""

import re

CHARS_PER_PAGE = 1800


def calculate_chars_per_page(page_count: int, doc_type: str = "") -> int:
    """Возвращает стандартное число символов на страницу (обычно 1800 по ГОСТ)."""
    if doc_type == "esse":
        return 1600
    elif doc_type == "doklad":
        return 1700
    return CHARS_PER_PAGE


def target_chars(pages: int, doc_type: str = "") -> int:
    """Рассчитывает целевое количество символов для заданного числа страниц."""
    cpp = calculate_chars_per_page(pages, doc_type)
    return max(500, pages * cpp)


def target_pages_from_chars(chars: int, doc_type: str = "") -> float:
    """Рассчитывает эквивалентное число страниц по символам."""
    cpp = calculate_chars_per_page(1, doc_type)
    return round(chars / cpp, 1)


def words_for_chars(chars: int) -> int:
    """Оценивает число слов по символам (среднее слово в рус. языке ~7.5 символов с пробелом)."""
    return max(1, round(chars / 7.5))


def sort_bibliography_by_gost(lines: list[str]) -> list[str]:
    """Сортирует список литературы по ГОСТ 7.32-2017 (кириллица, затем латиница)."""
    if not lines:
        return lines

    def _is_cyrillic(char: str) -> bool:
        return "\u0400" <= char <= "\u04FF"

    def _sort_key(line: str) -> tuple[int, str]:
        clean = re.sub(r"^\d+\.\s*", "", line)
        first_char = clean[0] if clean else " "

        if _is_cyrillic(first_char):
            return (0, line.lower())
        elif first_char.isalpha():
            return (1, line.lower())
        else:
            return (2, line.lower())

    return sorted(lines, key=_sort_key)


def build_page_map(parts: dict) -> dict[str, int]:
    """Строит карту страниц по блокам текста."""
    page_map = {}
    current_char = 0
    for key, text in parts.items():
        if key == "literature":
            continue
        page_map[key] = max(1, round(current_char / CHARS_PER_PAGE) + 1)
        current_char += len(text or "")
    return page_map


def estimate_docx_pages(chars: int) -> int:
    """Быстрая математическая оценка страниц по символам."""
    return max(1, round(chars / CHARS_PER_PAGE))
