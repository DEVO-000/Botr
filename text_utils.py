"""
text_utils.py - Text processing, cleaning, cliche removal, and safety utilities.
"""

import re

# AI markers and cliches replacements
_AI_MARKER_REPLACEMENTS = [
    (r"(?i)\bв\s+современном\s+мире\b", "сегодня"),
    (r"(?i)\bв\s+настоящее\s+время\b", "сейчас"),
    (r"(?i)\bследует\s+отметить,?\s+что\b", ""),
    (r"(?i)\bнеобходимо\s+отметить,?\s+что\b", ""),
    (r"(?i)\bважно\s+отметить,?\s+что\b", ""),
    (r"(?i)\bстоит\s+отметить,?\s+что\b", ""),
    (r"(?i)\bнельзя\s+не\s+отметить,?\s+что\b", ""),
    (r"(?i)\bтаким\s+образом,?\s*", "Итак, "),
    (r"(?i)\bбезусловно,?\s*", ""),
    (r"(?i)\bнесомненно,?\s*", ""),
    (r"(?i)\bкак\s+известно,?\s*", ""),
    (r"(?i)\bиграет\s+важную\s+роль\b", "имеет значение"),
    (r"(?i)\bиграют\s+важную\s+роль\b", "имеют значение"),
    (r"(?i)\bзанимает\s+важное\s+место\b", "важен"),
    (r"(?i)\bзанимают\s+важное\s+место\b", "важны"),
    (r"(?i)\bзанимает\s+особое\s+место\b", "важна"),
    (r"(?i)\bв\s+ходе\s+проведённого\s+исследования\b", "в ходе исследования"),
    (r"(?i)\bв\s+ходе\s+проведенного\s+исследования\b", "в ходе исследования"),
    (r"(?i)\bв\s+процессе\s+исследования\b", "в процессе работы"),
    (r"(?i)\bв\s+рамках\s+настоящего\s+исследования\b", "в этой работе"),
    (r"(?i)\bв\s+рамках\s+настоящей\s+работы\b", "в этой работе"),
    (r"(?i)\bцель\s+работы\s+заключается\s+в\s+том,?\s+чтобы\b", "цель работы —"),
    (r"(?i)\bобъектом\s+исследования\s+выступает\b", "объект исследования —"),
    (r"(?i)\bобъектом\s+исследования\s+является\b", "объект исследования —"),
    (r"(?i)\bпредметом\s+исследования\s+выступает\b", "предмет исследования —"),
    (r"(?i)\bпредметом\s+исследования\s+является\b", "предмет исследования —"),
    (r"(?i)\bследует\s+отметить\s+тот\s+факт,?\s+что\b", ""),
    (r"(?i)\bотмечается\s+тот\s+факт,?\s+что\b", ""),
    (r"(?i)\bважно\s+отметить\s+тот\s+факт,?\s+что\b", ""),
    (r"(?i)\bнеобходимо\s+учитывать\s+тот\s+факт,?\s+что\b", ""),
    (r"(?i)\bисходя\s+из\s+вышесказанного\s+можно\s+сделать\s+вывод,?\s+что\b", ""),
]


def strip_markdown_markers(text: str) -> str:
    """Очищает текст от служебной разметки markdown."""
    if not text:
        return ""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    return text.strip()


def remove_ai_marker_phrases(text: str) -> str:
    """Удаляет служебные и шаблонные фразы-маркеры ИИ без добавления опечаток."""
    if not text:
        return ""
    out = text
    for pattern, repl in _AI_MARKER_REPLACEMENTS:
        out = re.sub(pattern, repl, out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"(?m)^\s+", "", out)
    return out.strip()


def remove_duplicate_phrases(text: str) -> str:
    """Срезает повторяющиеся фразы / тавтологии в одном предложении."""
    if not text:
        return text

    for n in (6, 5, 4, 3):
        pattern = re.compile(
            r"(\b(?:[А-Яа-яЁё]+(?:\s+|,\s+|\s+что\s+)){" + str(n) + r"})\1",
            flags=re.IGNORECASE,
        )
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(r"\1", text)

    intros = [
        "итак", "таким образом", "следовательно", "кроме того",
        "помимо этого", "более того", "в заключение",
    ]
    for intro in intros:
        pat = re.compile(rf"\b({re.escape(intro)})\s*,?\s+\1\b\s*,?", flags=re.IGNORECASE)
        text = pat.sub(r"\1,", text)

    text = re.sub(
        r"(\bпроведён(?:н)?ый\s+анализ\b[^.]*?)(\s+(?:что|и|который|где)\s+)?\bпроведён(?:н)?ый\s+анализ\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r",([А-Яа-яЁёA-Za-z])", r", \1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def sanitize_llm_text(raw: str) -> str:
    """Чистит мусор от LLM: markdown-разметку, тройные переводы строк."""
    if not raw:
        return ""
    text = strip_markdown_markers(raw.strip())
    text = re.sub(r"```[^\n]*\n?", "", text)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r'([а-яё])([А-ЯЁ])', r'\1 \2', text)
    return text.strip()


def normalize_typography(text: str) -> str:
    """Нормализует кавычки («»), тире (—), убирает двойные пробелы."""
    if not text:
        return ""
    text = re.sub(r'"([^"]+)"', r'«\1»', text)
    text = re.sub(r'(\s)-(\s)', r'\1—\2', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text


def split_sentences_safe(text: str) -> list[str]:
    """Разбивает текст на предложения по границам, не ломая ссылки и инициалы."""
    if not text:
        return []
    pattern = re.compile(r'(?<!\b[А-ЯA-Z])(?<!\b[а-яa-z]\.[а-яa-z])(?<=[.!?])\s+(?=[А-ЯA-Z«"])')
    return [s.strip() for s in pattern.split(text) if s.strip()]


def is_garbage(text: str) -> bool:
    """Проверяет, является ли текст мусором или ошибкой генерации LLM."""
    if not text or len(text.strip()) < 10:
        return True
    t = text.lower()
    bad_markers = [
        "as an ai", "я языковая модель", "произошла ошибка",
        "invalid request", "404 not found", "cannot fulfill this request"
    ]
    return any(m in t for m in bad_markers)
