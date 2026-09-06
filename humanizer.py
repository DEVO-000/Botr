# -*- coding: utf-8 -*-
"""Очеловечивание академического текста.

ГЛАВНЫЙ ПРИНЦИП ЭТОГО МОДУЛЯ
──────────────────────────────────
Неграмотный текст хуже шаблонного. Преподаватель простит клише, но не
простит «этая проблематика важен». Поэтому регулярками здесь разрешено
только то, что НЕ требует согласования по роду/числу/падежу:

  РАЗРЕШЕНО:
    1. Удаление вводных фраз-паразитов («Таким образом,») — удаление
       вводного члена всегда оставляет предложение грамотным.
    2. Удаление паразитных определений («данный», «рассматриваемый») —
       удаление прилагательного не ломает согласования остатка.
    3. Замена НЕИЗМЕНЯЕМЫХ обстоятельств («в современном мире» →
       «сегодня») — наречия ни с чем не согласуются.
    4. Замена союзных скреп («в связи с тем, что» → «поскольку»).
    5. Разбиение длинных периодов только по «;» и противительным союзам,
       где вторая часть — самостоятельное предложение.

  ЗАПРЕЩЕНО:
    — менять глаголы, существительные и сказуемые (требует согласования);
    — вставлять опечатки и намеренные ошибки;
    — добавлять новые утверждения и факты.

Глубокая переформулировка — задача модели, а не регулярок. См. `rewrite_prompt()`:
если `ai_score()` выше порога, вызывающий код должен прогнать текст
вторым проходом через LLM с этим промптом.
"""

from __future__ import annotations

import re
import unicodedata
from prompts import rewrite_to_human_style

# ──────────────────────────────────────────────────────────────────────
#  Защита служебных конструкций
# ──────────────────────────────────────────────────────────────────────

_CITATION_RE = re.compile(r"\[\s*\d+(?:\s*[,;][^\]\n]*)?\]")
_FORMULA_RE = re.compile(r"\$[^$\n]{1,400}\$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_URL_RE = re.compile(r"https?://\S+|10\.\d{4,9}/\S+")

_PLACEHOLDER = "\ue000P{}\ue001"
_PLACEHOLDER_RE = re.compile(r"\ue000P(\d+)\ue001")


def _protect(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def _sub(m: re.Match) -> str:
        saved.append(m.group(0))
        return _PLACEHOLDER.format(len(saved) - 1)

    for pattern in (_TABLE_ROW_RE, _FORMULA_RE, _CITATION_RE, _URL_RE):
        text = pattern.sub(_sub, text)
    return text, saved


def _restore(text: str, saved: list[str]) -> str:
    def _sub(m: re.Match) -> str:
        idx = int(m.group(1))
        return saved[idx] if 0 <= idx < len(saved) else ""

    return _PLACEHOLDER_RE.sub(_sub, text)


# ──────────────────────────────────────────────────────────────────────
#  1. Вводные фразы-паразиты (удаляются целиком)
# ──────────────────────────────────────────────────────────────────────

# Группа A: «<фраза>, что ...» — удаляется вместе с союзом «что».
# Без удаления «что» остаётся обрубок «Что тема важна...».
_FILLER_THAT = [
    "следует отметить",
    "необходимо отметить",
    "стоит отметить",
    "важно отметить",
    "нельзя не отметить",
    "хочется отметить",
    "можно отметить",
    "следует подчеркнуть",
    "необходимо подчеркнуть",
    "важно подчеркнуть",
    "следует сказать",
    "следует указать",
    "следует добавить",
    "можно сказать",
    "можно сделать вывод",
    "не вызывает сомнений",
    "очевидно",
    "известно",
    "принято считать",
]

# Группа B: автономные вводные слова — удаляется только фраза + запятая.
_FILLER_PLAIN = [
    "таким образом",
    "следовательно",
    "в свою очередь",
    "в свою очередь, следует",
    "в то же время",
    "вместе с тем",
    "более того",
    "кроме того",
    "помимо этого",
    "помимо прочего",
    "безусловно",
    "несомненно",
    "разумеется",
    "бесспорно",
    "как известно",
    "как уже было сказано",
    "в целом",
    "в конечном итоге",
    "в конечном счёте",
    "в конечном счете",
    "в заключение",
    "в качестве заключения",
    "подводя итог",
    "подводя итоги",
    "резюмируя вышесказанное",
    "обобщая вышесказанное",
    "обобщая сказанное",
    "исходя из вышеизложенного",
    "в силу вышеизложенного",
    "на основании вышеизложенного",
    "учитывая вышесказанное",
    "в свете вышеизложенного",
    "стоит сказать",
    "стоит подчеркнуть",
    "надо отметить",
    "нужно отметить",
    "важно подчеркнуть",
    "в заключение хочется отметить",
    "хочется отметить",
]


def _drop_filler(text: str) -> str:
    """Удаляет вводные фразы в позиции начала предложения."""
    alt_that = "|".join(re.escape(p) for p in _FILLER_THAT)
    alt_plain = "|".join(re.escape(p) for p in _FILLER_PLAIN)

    # «Следует отметить, что X» → «X»  (союз «что» убирается тоже)
    text = re.sub(rf"(?im)^\s*(?:{alt_that})\s*,\s*что\s+(?=\S)", "", text)
    text = re.sub(rf"(?i)([.!?»]\s+)(?:{alt_that})\s*,\s*что\s+(?=\S)", r"\1", text)

    # «Таким образом, X» → «X»
    text = re.sub(rf"(?im)^\s*(?:{alt_plain})\s*,\s*(?=\S)", "", text)
    text = re.sub(rf"(?i)([.!?»]\s+)(?:{alt_plain})\s*,\s*(?=\S)", r"\1", text)
    return text


# ──────────────────────────────────────────────────────────────────────
#  2. Грамматически безопасные замены
# ──────────────────────────────────────────────────────────────────────

# Паразитные определения: УДАЛЯЕМ (не заменяем!).
# «данная проблематика» → «проблематика» (всегда грамотно),
# а НЕ «этая проблематика» (была ошибка в предыдущей версии).
_PARASITE_ADJ = re.compile(
    r"(?i)\b(?:данн|рассматриваем|изучаем|анализируем|исследуем|описываем)"
    r"(?:ый|ая|ое|ые|ого|ой|ых|ым|ому|ую|ыми|ом)\s+"
)

# Неизменяемые обстоятельства и союзные скрепы — согласование не требуется.
_SAFE_REWRITES: list[tuple[str, str]] = [
    (r"в современном мире", "сегодня"),
    (r"в современных условиях", "сейчас"),
    (r"в настоящее время", "сейчас"),
    (r"на современном этапе развития", "сейчас"),
    (r"на современном этапе", "сейчас"),
    (r"в рамках настоящего исследования", "в этой работе"),
    (r"в рамках настоящей работы", "в этой работе"),
    (r"в ходе проведённого исследования", "в ходе исследования"),
    (r"в ходе проведенного исследования", "в ходе исследования"),
    # Союзные скрепы: замена не требует согласования.
    (r"с целью того,? чтобы", "чтобы"),
    (r"в связи с тем,? что", "поскольку"),
    (r"по причине того,? что", "поскольку"),
    (r"ввиду того,? что", "поскольку"),
    (r"в силу того,? что", "поскольку"),
    (r"несмотря на то,? что", "хотя"),
    (r"в том случае,? если", "если"),
    (r"в связи с этим", "поэтому"),
    (r"в результате чего", "поэтому"),
    (r"целый ряд", "ряд"),
    (r"в целом ряде", "в ряде"),
    # Канцелярские связки в начале формулировок Цели/Объекта/Предмета:
    # замена на тире грамматически нейтральна.
    (r"цель работы заключается в том,? чтобы", "цель работы —"),
    (r"объектом исследования выступает", "объект исследования —"),
    (r"объектом исследования является", "объект исследования —"),
    (r"предметом исследования выступает", "предмет исследования —"),
    (r"предметом исследования является", "предмет исследования —"),
]

_SAFE_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _SAFE_REWRITES]


# ──────────────────────────────────────────────────────────────────────
#  3. Защитный контроль грамотности
# ──────────────────────────────────────────────────────────────────────

# Признаки того, что правка сломала предложение.
_BROKEN_PATTERNS = [
    re.compile(r"(?i)^\s*что\s"),              # обрубок «Что тема...»
    re.compile(r"(?i)^\s*(?:и|а|но|же|ли|бы)\s"),  # начало с союза/частицы
    re.compile(r"(?i)^\s*(?:чтобы|который|которая|которое|которые)\s"),
    re.compile(r"(?i)\bтак,? как и\b"),
    re.compile(r"(?i)\bэтая|этое|этыего|этойго\b"),  # следы бага v1
    re.compile(r"\s,|,,|—\s*—|\(\s*\)"),
    re.compile(r"(?i)\b(в|на|с|по|к|из|от|для|при|о|об|у|за)\s*[.!?]"),  # предлог перед точкой
]


def _looks_broken(sentence: str) -> bool:
    """Грубая проверка: похоже ли, что предложение стало неграмотным.

    ВАЖНО: служебные конструкции вырезаются перед проверкой. Без этого
    сокращение «с.» внутри ГОСТ-ссылки [1, с. 45] ловится как «предлог
    перед точкой», и тогда откатываются АБСОЛЮТНО все правки.
    """
    s = (sentence or "").strip()
    if not s:
        return True
    probe = _CITATION_RE.sub(" ", s)
    probe = _FORMULA_RE.sub(" ", probe)
    probe = _URL_RE.sub(" ", probe)
    probe = _PLACEHOLDER_RE.sub(" ", probe)
    for abbr in _ABBR + ("с.", "ст.", "г.", "в.", "изд.", "ред."):
        probe = probe.replace(abbr, " ")
    if not probe.strip():
        return False
    return any(rx.search(probe) for rx in _BROKEN_PATTERNS)


def _safe_apply(original: str, transform) -> str:
    """Применяет правку попредложно и ОТКАТЫВАЕТ там, где стало хуже.

    Это ключевой предохранитель: лучше оставить клише, чем выдать бред.
    """
    out_paras = []
    for para in re.split(r"\n\s*\n", original):
        if not para.strip():
            continue
        if _TABLE_ROW_RE.search(para) or para.strip().startswith("$"):
            out_paras.append(para.strip())
            continue
        rebuilt = []
        for sent in split_sentences(para):
            new = transform(sent)
            if not new.strip() or _looks_broken(new):
                rebuilt.append(sent)          # откат
            elif len(new) < len(sent) * 0.45:  # потерялось слишком много
                rebuilt.append(sent)
            else:
                rebuilt.append(new)
        out_paras.append(" ".join(rebuilt))
    return "\n\n".join(out_paras)


def _capitalize_sentences(text: str) -> str:
    def _up(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    text = re.sub(r"(?m)^(\s*)([а-яёa-z])", _up, text)
    text = re.sub(r"([.!?]\s+)([а-яёa-z])", _up, text)
    return text


def remove_cliches(text: str) -> str:
    """Убирает клише с откатом на сломанных предложениях."""
    if not text or not text.strip():
        return text or ""

    def _one(sent: str) -> str:
        body, saved = _protect(sent)
        body = _drop_filler(body)
        body = _PARASITE_ADJ.sub("", body)
        for rx, repl in _SAFE_COMPILED:
            body = rx.sub(repl, body)
        body = re.sub(r"\s+,", ",", body)
        body = re.sub(r",\s*,+", ",", body)
        body = re.sub(r"[ \t]{2,}", " ", body)
        body = re.sub(r"\s+([.!?;:])", r"\1", body)
        body = _capitalize_sentences(body.strip())
        return _restore(body, saved)

    return _safe_apply(text, _one)


# ──────────────────────────────────────────────────────────────────────
#  4. Разбиение на предложения и ритм
# ──────────────────────────────────────────────────────────────────────

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«—])")
_ABBR = ("т. д.", "т. п.", "т. е.", "и др.", "см.", "рис.", "табл.", "гг.", "вв.")


def split_sentences(text: str) -> list[str]:
    """Режет на предложения, не ломая `[1, с. 45]`, формулы и сокращения."""
    if not text:
        return []
    body, saved = _protect(text)
    for i, abbr in enumerate(_ABBR):
        body = body.replace(abbr, f"\ue010{i}\ue011")
    parts = [p.strip() for p in _SENT_SPLIT_RE.split(body) if p.strip()]
    out = []
    for p in parts:
        for i, abbr in enumerate(_ABBR):
            p = p.replace(f"\ue010{i}\ue011", abbr)
        out.append(_restore(p, saved))
    return out


def _word_count(sentence: str) -> int:
    return len(re.findall(r"[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z-]*", sentence))


# Только те границы, где вторая часть — полноценное предложение.
# «а также» СОЗНАТЕЛЬНО не включено: разрыв по нему оставляет однородные
# члены без подлежащего.
# Точка с запятой в русском академическом тексте почти всегда разделяет два
# самостоятельных предложения — разбиваем её без оглядки на длину.
_SPLIT_ALWAYS = [(re.compile(r";\s+(?=[а-яёА-ЯЁ])"), ". ")]

# Эти — только для переусложнённых периодов.
_SPLIT_IF_LONG = [
    (re.compile(r",\s+(однако)\s+", re.IGNORECASE), r". \1 "),
    (re.compile(r",\s+(но при этом)\s+", re.IGNORECASE), r". \1 "),
    (re.compile(r",\s+(тогда как)\s+", re.IGNORECASE), r". \1 "),
]

_ANY_SENT_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _split_by_commas_fallback(sentence: str, max_words: int) -> list[str]:
    """Аварийное деление предложения-монолита (сбой модели: 100+ слов без точек).

    Режет по запятым вне защищённых зон (ссылки/формулы уже подменены
    _protect), группирует придаточные в куски ~10–25 слов. При любом
    признаке поломки откатывается к исходному предложению.
    """
    body, saved = _protect(sentence)
    parts = [p.strip(" ,") for p in re.split(r",", body) if p.strip(" ,")]
    if len(parts) < 3:
        return [sentence]

    # Придаточные, начинающиеся с союзных слов, нельзя отрывать от
    # предыдущей части: самостоятельное предложение «Которые требуют…»
    # неграмотно и честно отбраковывается _looks_broken. Склеиваем их
    # с предыдущей клаузой ДО группировки.
    _DEP_START = re.compile(
        r"(?i)^(?:котор\w*|чтобы|если|когда|хотя|потому что|так как|ибо|где|куда|откуда)\b"
    )
    merged: list[str] = []
    for p in parts:
        if merged and _DEP_START.match(p):
            merged[-1] += ", " + p
        else:
            merged.append(p)
    parts = merged
    if len(parts) < 2:
        return [sentence]

    target = max(8, min(max_words, 25))
    chunks: list[str] = []
    cur: list[str] = []
    cur_w = 0
    for p in parts:
        cur.append(p)
        cur_w += _word_count(p)
        if cur_w >= target:
            chunks.append(", ".join(cur))
            cur, cur_w = [], 0
    if cur:
        # FIX: объединяем хвост с предыдущим куском только когда он САМ
        # совсем короткий; раньше проверялось первое слово хвоста, и
        # здоровый кусок в 20+ слов вливался обратно — на выходе получался
        # исходный монолит.
        left = ", ".join(cur)
        if chunks and _word_count(left) < 6:
            chunks[-1] += ", " + left
        else:
            chunks.append(left)

    fixed = []
    for c in chunks:
        c = _restore(c.strip(" ,"), saved).strip()
        if not c:
            continue
        if c[0].islower():
            c = c[0].upper() + c[1:]
        if c[-1] not in ".!?":
            c += "."
        fixed.append(c)

    # Откат при поломке любого куска — неграмматичный текст хуже монолита.
    if len(fixed) < 2 or any(_looks_broken(p) or _word_count(p) < 4 for p in fixed):
        return [sentence]
    return fixed


def _split_long_sentence(sentence: str, max_words: int = 30) -> list[str]:
    """Делит период только по границе, где вторая часть самостоятельна."""
    body, saved = _protect(sentence)
    changed = False
    rules = list(_SPLIT_ALWAYS)
    if _word_count(sentence) > max_words:
        rules += _SPLIT_IF_LONG
    for rx, repl in rules:
        new = rx.sub(repl, body, count=1)
        if new != body:
            body, changed = new, True
            break
    if not changed:
        # FIX: предложение-монолит без единой точки (сбой модели) не режется
        # обычными правилами — они ищут конкретные союзы. Для строк длиннее
        # нормы применяем аварийное деление по запятым.
        if _word_count(sentence) > max_words:
            return _split_by_commas_fallback(sentence, max_words)
        return [sentence]
    # Режем по любой точке: после замены «; » → «. » следует строчная буква,
    # поэтому _SENT_SPLIT_RE (требующий заглавной) здесь не годится.
    pieces = [_restore(p, saved).strip() for p in _ANY_SENT_BOUNDARY.split(body) if p.strip()]
    fixed = []
    for p in pieces:
        if p and p[0].islower():
            p = p[0].upper() + p[1:]
        if p and p[-1] not in ".!?":
            p += "."
        fixed.append(p)
    # Откат, если любой кусок выглядит сломанным.
    if any(_looks_broken(p) or _word_count(p) < 4 for p in fixed):
        return [sentence]
    return fixed or [sentence]


def vary_rhythm(text: str) -> str:
    """Разбивает предложения-монстры, чтобы длина фраз была неровной."""
    if not text:
        return ""
    out_paras = []
    for para in re.split(r"\n\s*\n", text):
        if not para.strip():
            continue
        if _TABLE_ROW_RE.search(para) or para.strip().startswith("$"):
            out_paras.append(para.strip())
            continue
        rebuilt: list[str] = []
        for s in split_sentences(para):
            rebuilt.extend(_split_long_sentence(s))
        out_paras.append(" ".join(rebuilt))
    return "\n\n".join(out_paras)


# ──────────────────────────────────────────────────────────────────────
#  5. Оценка «ИИшности»
# ──────────────────────────────────────────────────────────────────────

_AI_MARKERS = (
    [p.lower() for p in _FILLER_THAT]
    + [p.lower() for p in _FILLER_PLAIN]
    + [
        "в современном мире",
        "в настоящее время",
        "играет важную роль",
        "играет ключевую роль",
        "имеет важное значение",
        "представляет собой",
        "комплексный подход",
        "всесторонний анализ",
        "широкий спектр",
        "актуальность обусловлена",
        "степень разработанности",
        "данная работа посвящена",
        "требует дальнейшего изучения",
        "как отечественных, так и зарубежных",
        "вышеуказанн",
        "вышеперечисленн",
        "вышеназванн",
        "особую актуальность",
        "необходимо отметить",
        "следует отметить",
        "следует подчеркнуть",
        "важно отметить",
        "стоит отметить",
        "можно сделать вывод",
        "ряд исследователей отмечает",
        "ряд авторов отмечает",
        "многие исследователи",
        "в ходе проведённого исследования",
        "представляется важным",
        "представляется целесообразным",
        "представляет научный интерес",
        "особую значимость",
        "значимость исследования",
        "целью данной работы является",
        "целью настоящей работы является",
        "актуальность исследования обусловлена",
        "на сегодняшний день",
        "в наши дни",
        "необходимо рассмотреть",
        "рассмотрим подробнее",
        "стоит обратиться к",
        "данная тема является",
        "данное исследование посвящено",
    ]
)


def ai_score(text: str) -> float:
    """Оценка «машинности», 0–100. Цель для готового текста — ниже 25.

    Главный вес у коэффициента вариации длины предложений: именно по нему
    детекторы отличают LLM от человека лучше всего.
    """
    if not text or len(text) < 200:
        return 0.0
    low = text.lower()
    score = 0.0

    hits = sum(low.count(m) for m in _AI_MARKERS)
    score += min(35.0, hits / (len(text) / 1000.0) * 9.0)

    sentences = split_sentences(text)
    lengths = [_word_count(s) for s in sentences if _word_count(s) > 2]
    if len(lengths) >= 5:
        avg = sum(lengths) / len(lengths)
        if avg > 0:
            var = sum((x - avg) ** 2 for x in lengths) / len(lengths)
            cv = (var ** 0.5) / avg
            if cv < 0.45:
                score += min(30.0, (0.45 - cv) * 90.0)

    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) >= 3:
        plen = [len(p) for p in paras]
        pavg = sum(plen) / len(plen)
        if pavg > 0:
            pvar = sum((x - pavg) ** 2 for x in plen) / len(plen)
            pcv = (pvar ** 0.5) / pavg
            if pcv < 0.25:
                score += min(20.0, (0.25 - pcv) * 80.0)

    starts = [p.strip().split()[0].lower() for p in paras if p.strip().split()]
    if len(starts) >= 3:
        ratio = len(set(starts)) / len(starts)
        if ratio < 0.8:
            score += min(15.0, (0.8 - ratio) * 50.0)

    return round(min(100.0, score), 1)


def report(text: str) -> dict:
    """Диагностика для логов."""
    low = (text or "").lower()
    sentences = split_sentences(text or "")
    lengths = [_word_count(s) for s in sentences if _word_count(s) > 2]
    cv = 0.0
    if len(lengths) >= 2:
        avg = sum(lengths) / len(lengths)
        if avg:
            var = sum((x - avg) ** 2 for x in lengths) / len(lengths)
            cv = round((var ** 0.5) / avg, 3)
    return {
        "score": ai_score(text or ""),
        "cliches": sorted({m for m in _AI_MARKERS if m in low}),
        "sentences": len(sentences),
        "sentence_cv": cv,
    }


# ──────────────────────────────────────────────────────────────────────
#  6. Второй проход через модель (главный инструмент!)
# ──────────────────────────────────────────────────────────────────────

STYLE_RULES = """ТРЕБОВАНИЯ К ЯЗЫКУ (самое важное):
Текст должен читаться как работа живого автора, а не как генерация.

1. ЗАПРЕЩЕННЫЕ ФРАЗЫ (не используй ни разу):
   «в современном мире», «в современных условиях», «в настоящее время»,
   «таким образом», «следует отметить», «необходимо отметить»,
   «следует подчеркнуть», «можно сделать вывод», «играет важную роль»,
   «имеет важное значение», «представляет собой», «комплексный подход»,
   «всесторонний анализ», «широкий спектр», «актуальность обусловлена»,
   «требует дальнейшего изучения», «как отечественных, так и зарубежных»,
   «вышеуказанный», «вышеперечисленный», «безусловно», «несомненно».
   «подводя итог», «в заключение хочется отметить», «важно отметить»,
   «стоит отметить», «целью данной работы является», «актуальность темы
   обусловлена», «ряд авторов отмечает», «многие исследователи считают»,
   «на сегодняшний день», «данное исследование посвящено».
   Слово «данный» в значении «этот» — не более одного раза на раздел.
   Слово «актуальность» можно использовать, но НЕ в связке «актуальность...
   обусловлена» и не чаще двух раз на раздел.

2. РИТМ. Главный признак машинного текста — все предложения одинаковой
   длины. Чередуй: длинное предложение (25–35 слов) — короткое (5–10 слов) —
   среднее — снова длинное. В каждом абзаце должно быть хотя бы одно короткое
   предложение на 5–10 слов, и оно должно попадаться ПОСЛЕ периода в 30+ слов,
   а не только в начале абзаца. Абзацы тоже разной длины (3–6 предложений),
   не под одну гребёнку.

3. КОНКРЕТИКА вместо обтекаемых формулировок. Не «ряд авторов отмечает»,
   а конкретная фамилия из списка литературы. Не «значительный рост», а цифра,
   если она есть в источниках. Ничего не выдумывай: лучше без цифры,
   чем с выдуманной.

4. НЕ НАЧИНАЙ абзацы одним и тем же словом и не строй их по одной схеме.
   Разные абзацы раздела должны начинаться по-разному: факт, имя исследователя,
   вопрос, возражение («однако», «в отличие от»), уточнение термина, цифра.
   Не повторяй подряд одинаковые зачины («В исследовании...», «Автор считает...»).

5. Допускается академическая осторожность и спор: «спорно», «данных недостаточно»,
   «здесь мнения расходятся». Живой автор сомневается, генератор — нет.

6. ГРАМОТНОСТЬ выше всего. Опечатки, рассогласованные падежи и намеренные
   ошибки СТРОГО ЗАПРЕЩЕНЫ. Очеловечивание — это живой ритм и конкретика,
   а НЕ ошибки.

7. ДОПУСТИМОЕ «непричёсанное»: изредка более простое выражение, оборот из
   разговорно-академической речи («более сложный вопрос», «здесь важно
   понимать»), присоединительное короткое предложение («Это важно.», «Спорно.»).
   Текст не должен выглядеть как отполированный пресс-релиз."""


def rewrite_prompt(text: str, *, topic: str = "") -> list[dict]:
    """Сообщения для второго прохода: модель переписывает свой темный текст.

    Глубокая переформулировка возможна только так — регулярки на это
    принципиально не способны без разрушения грамматики.
    """
    diag = report(text)
    found = ", ".join(f"«{c}»" for c in diag["cliches"][:12]) or "—"
    return [
        {
            "role": "system",
            "content": (
                "Ты редактор научных текстов. Ты переписываешь текст, чтобы он читался "
                "как работа человека. Содержание, факты и все ссылки вида [1, с. 45] "
                "сохраняются без изменений — меняется только форма.\n"
                "СТРОГО: не добавляй новых ссылок и не удаляй существующие; "
                "формат [N] без страницы запрещён — если ссылка была без страницы, "
                "оставь её как есть.\n\n" + STYLE_RULES
            ),
        },
        {
            "role": "user",
            "content": (
                f"Тема работы: {topic or 'не указана'}\n"
                f"Оценка машинности: {diag['score']}/100 (цель — ниже 25).\n"
                f"Найденные клише: {found}\n"
                f"Разброс длины предложений (CV): {diag['sentence_cv']} "
                f"(у человека 0.45–0.75, у машины 0.20–0.35. Если CV ниже 0.40 — "
                f"обязательно разбей длинные периоды и добавь коротких предложений).\n\n"
                "Перепиши текст ниже. Объём сохрани таким же (±5 %). Верни ТОЛЬКО "
                "переписанный текст без комментариев и пояснений.\n\n"
                "─── ТЕКСТ ───\n" + text
            ),
        },
    ]


def citations_preserved(before: str, after: str) -> bool:
    """Проверяет, что второй проход не потерял и не выдумал ссылки.

    Обязательная проверка перед тем, как принять результат LLM-рерайта.
    """
    nums = lambda t: sorted(re.findall(r"\[\s*(\d+)", t or ""))
    return nums(before) == nums(after)


# ──────────────────────────────────────────────────────────────────────
#  7. Типографика и основной вход
# ──────────────────────────────────────────────────────────────────────


def normalize_typography(text: str) -> str:
    """Russian typography: dashes, quotes, spaces, non-breaking spaces."""
    if not text:
        return ""
    body, saved = _protect(text)
    body = unicodedata.normalize("NFC", body)
    body = re.sub(r"(?<=\s)--?(?=\s)", "\u2014", body)
    body = re.sub(r"(\d)\s*[-\u2014]\s*(\d)", "\\1\u2013\\2", body)
    body = re.sub(r'"([^"\n]{1,200})"', "\u00ab\\1\u00bb", body)
    body = re.sub(r"\s+([,.;:!?])", r"\1", body)
    body = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"(\d)\s+(%|\u20bd)", "\\1\u00a0\\2", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return _restore(body, saved).strip()


def humanize(text: str, *, aggressive: bool = True) -> str:
    """Full pass: cliches -> rhythm -> typography. Idempotent and grammar-safe.

    This only performs SAFE deletions and invariant substitutions. Deep
    rephrasing must be done by the model via rewrite_prompt().
    """
    if not text or not text.strip():
        return text or ""
    out = remove_cliches(text)
    if aggressive:
        out = vary_rhythm(out)
    return normalize_typography(out)


async def rewrite_with_model(text: str, topic: str, model_key: str, chat_fn) -> str:
    """Переписывает текст в человеческом стиле через модель."""
    if not text or len(text) < 200:
        return text
    
    score = ai_score(text)
    if score < 20:
        return text
    
    messages = [
        {"role": "system", "content": "You are an editor. Rewrite the text in a natural human style."},
        {"role": "user", "content": rewrite_to_human_style(text)}
    ]
    
    new_text, _ = await chat_fn(model_key, messages, max_tokens=4096)
    
    if not new_text or len(new_text) < len(text) * 0.6:
        return text
    
    if not citations_preserved(text, new_text):
        return text
    
    new_score = ai_score(new_text)
    if new_score > score - 5:
        return text
    
    print(f"[HUMANIZER] Рерайт улучшил текст: {score} → {new_score}")
    return new_text


def apply_human_style_safe(text: str) -> str:
    """Применяет человеческий стиль ТОЛЬКО через безопасные замены (без модели)."""
    if not text:
        return text
    
    text = remove_cliches(text)
    text = vary_rhythm(text)
    text = normalize_typography(text)
    
    text = text.replace("—", " - ")
    text = re.sub(r"\s+-\s+", " - ", text)
    
    forbidden_words = [
        "can", "may", "just", "that", "very", "really", "literally", "actually",
        "certainly", "probably", "basically", "could", "maybe", "delve", "embark",
        "enlightening", "esteemed", "shed light", "craft", "crafting", "imagine",
        "realm", "game-changer", "unlock", "discover", "skyrocket", "abyss",
        "not alone", "in a world where", "revolutionize", "disruptive", "utilize",
        "utilizing", "dive deep", "tapestry", "illuminate", "unveil", "pivotal",
        "intricate", "elucidate", "hence", "furthermore", "however", "harness",
        "exciting", "groundbreaking", "cutting-edge", "remarkable", "glimpse into",
        "navigating", "landscape", "stark", "testament", "in summary", "in conclusion",
        "moreover", "boost", "skyrocketing", "opened up", "powerful", "inquiries",
        "ever-evolving"
    ]
    
    for word in forbidden_words:
        text = re.sub(rf"\b{word}\b", "", text, flags=re.IGNORECASE)
    
    text = re.sub(r"\s+", " ", text)
    
    return text.strip()
