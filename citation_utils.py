"""
citation_utils.py - Citation parsing, validation, citation-source matching, and page repair functions.
"""

import re


def validate_user_literature(content: str) -> tuple[bool, str]:
    """Проверяет пользовательский список литературы."""
    if not content:
        return False, "❌ Список литературы пуст."

    lines = [l.strip() for l in content.split("\n") if l.strip()]

    if len(lines) < 3:
        return False, "❌ Слишком мало источников. Введите минимум 3."

    has_content = any(re.search(r"[А-Яа-яёA-Za-z]{4,}", l) for l in lines)
    if not has_content:
        return False, "❌ Список похож на мусор. Введите реальные источники."

    return True, ""


def match_citations_to_sources(
    text: str,
    literature: str,
    min_confidence: float = 0.15,
) -> str:
    """Привязывает ссылки к источникам по ключевым словам."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if not isinstance(literature, str):
        literature = str(literature) if literature is not None else ""

    if not text or not literature:
        return text

    sources = []
    for line in literature.split("\n"):
        if re.match(r"^\d+\.\s+", line.strip()):
            body = re.sub(r"^\d+\.\s*", "", line.strip())
            sources.append(body)

    if not sources:
        return text

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    for para_idx, para in enumerate(paragraphs):
        if re.search(r"\[\d+\s*,\s*[сСcC]\.\s*\d+\]", para):
            continue

        stopwords = {
            "этот", "этого", "этом", "этой", "эти", "этих", "этим",
            "также", "более", "менее", "самый", "очень", "может", "могут",
            "который", "которая", "которые", "которых", "если", "чтобы",
            "однако", "поэтому", "между", "через", "после", "перед",
            "всех", "все", "всё", "всей", "всём", "всеми",
            "является", "являются", "представляет", "представляют",
        }
        words = re.findall(r"[а-яёa-z]{4,}", para.lower())
        keywords = [w for w in words if w not in stopwords and len(w) >= 4]

        if not keywords:
            continue

        scores = []
        for idx, source in enumerate(sources, start=1):
            source_lower = source.lower()
            score = sum(1 for w in keywords if w in source_lower)
            if score > 0:
                scores.append((idx, score, source))

        if not scores:
            continue

        scores.sort(key=lambda x: x[1], reverse=True)
        best_idx, best_score, best_source = scores[0]

        if best_score >= 2:
            if not re.search(r"\[\d+\s*,\s*[сСcC]\.\s*\d+\]", para):
                # НЕ придумываем номер страницы — ставим ссылку без страницы [N].
                # Выдуманная страница — основание снять работу.
                if para.endswith("."):
                    para = para[:-1] + f" [{best_idx}]."
                else:
                    para = para + f" [{best_idx}]."
                paragraphs[para_idx] = para

    return "\n\n".join(paragraphs)


def final_citation_check(parts: dict) -> dict:
    """Проверяет, что все ссылки имеют формат [N, с. X]."""
    if not isinstance(parts, dict):
        return parts
    for key, text in parts.items():
        if key == "literature" or not isinstance(text, str):
            continue
        bare_citations = re.findall(r"\[\s*(\d+)\s*\]", text)
        if bare_citations:
            page_map = {}
            for n in bare_citations:
                if n not in page_map:
                    m = re.search(rf"\[\s*{n}\s*,\s*[сСcC]\.\s*(\d+)\]", text)
                    if m:
                        page_map[n] = m.group(1)

            def _fix_bare(m: re.Match) -> str:
                n = m.group(1)
                if n in page_map:
                    return f"[{n}, с. {page_map[n]}]"
                return f"[{n}]"

            parts[key] = re.sub(r"\[\s*(\d+)\s*\]", _fix_bare, text)

    return parts


def validate_no_broken_citations(text: str) -> tuple[bool, str]:
    """Проверяет отсутствие обломанных/незавершённых ссылок в тексте."""
    if not text:
        return True, ""

    broken_patterns = [
        (r"\[\d+\s*,\s*[сСcC]\.\s*\]", "Ссылка без номера страницы [N, с.]"),
        (r"\[\d+\s*,\s*\]", "Незавершённая ссылка [N,]"),
        (r"\[\s*,\s*[сСcC]\.\s*\d+\]", "Ссылка без номера источника [, с. X]"),
    ]

    for pattern, err_msg in broken_patterns:
        if re.search(pattern, text):
            return False, err_msg

    return True, ""


def repair_broken_citations(text: str) -> str:
    """Чинит оборванные ссылки вида [1, с.] или [1,] или [ 1, с. 15].

    ФИКС (v3.4): раньше функция подставляла ВЫДУМАННЫЕ страницы
    «с. 15» / «с. 12» из воздуха — это гарантированный провал при проверке
    работы преподавателем. Теперь обрывы сворачиваются в честную ссылку [N]:
    по ГОСТ Р 7.0.5-2008 ссылка без страницы допустима, а несуществующая
    страница — нет.
    """
    if not text:
        return ""
    text = re.sub(r"\[\s*(\d+)\s*,\s*[сСcC]\.\s*\]", r"[\1]", text)
    text = re.sub(r"\[\s*(\d+)\s*,\s*\]", r"[\1]", text)
    text = re.sub(r"\[\s*,\s*[сСcC]\.\s*(\d+)\s*\]", r"[\1]", text)
    return text
