# -*- coding: utf-8 -*-
"""Строгий инспектор соответствия DOCX ГОСТ 7.32-2017 (по факту файла)."""
import re, sys
from docx import Document
from docx.shared import Mm, Pt, Cm

def mm(v): return round(v / 36000, 1) if v else None

def inspect(path):
    doc = Document(path)
    problems = []
    warns = []

    def style_name(p):
        try: return p.style.name or ""
        except Exception: return ""

    sec = doc.sections[0]
    # ── 1. Страница ──
    if abs(sec.page_width - Mm(210)) > Mm(2) or abs(sec.page_height - Mm(297)) > Mm(2):
        problems.append(f"Формат не A4: {mm(sec.page_width)}x{mm(sec.page_height)} мм")
    exp = {"left": 30, "right": 15, "top": 20, "bottom": 20}
    act = {"left": sec.left_margin, "right": sec.right_margin,
           "top": sec.top_margin, "bottom": sec.bottom_margin}
    for k in exp:
        if act[k] is None or abs(int(act[k]) - int(Mm(exp[k]))) > int(Mm(1)):
            problems.append(f"Поле «{k}»: {mm(act[k])} мм вместо {exp[k]} мм (ГОСТ 7.32 п.6.1.1)")

    # ── 2. Нумерация страниц ──
    # different first page + PAGE field в нижнем колонтитуле
    if not sec.different_first_page_header_footer:
        problems.append("На титульном листе будет виден номер страницы (нужно different_first_page)")
    footer_xml = sec.footer._element.xml if sec.footer is not None else ""
    if "PAGE" not in footer_xml:
        problems.append("Нет поля PAGE в нижнем колонтитуле")
    ftr_paras = sec.footer.paragraphs if sec.footer is not None else []
    if ftr_paras and ftr_paras[0].alignment is not None and "CENTER" not in str(ftr_paras[0].alignment):
        warns.append(f"Номер страницы не по центру: {ftr_paras[0].alignment}")

    # ── 3. Тело документа ──
    # Зоны: [0..toc_title) титул; [toc_title..first Heading 1 после него) содержание;
    # далее основное тело. ГОСТ-проверки выравнивания/отступа/шрифта — только тело.
    body = [p for p in doc.paragraphs if (p.text or "").strip()]
    STRUCT = ("СОДЕРЖАНИЕ", "ВВЕДЕНИЕ", "ЗАКЛЮЧЕНИЕ")
    BIB = ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", "СПИСОК ЛИТЕРАТУРЫ")

    toc_idx = next((i for i, p in enumerate(body) if p.text.strip().upper().startswith("СОДЕРЖАНИЕ")), None)
    if toc_idx is None:
        problems.append("Не найден заголовок «СОДЕРЖАНИЕ»")
        return len(problems), len(warns)
    body_start = toc_idx + 1
    while body_start < len(body):
        p = body[body_start]
        s = style_name(p)
        if s == "Heading 1" or p.text.strip() == "ВВЕДЕНИЕ":
            break
        body_start += 1
    body_pars = body[body_start:]

    def is_h1(p):
        return style_name(p) == "Heading 1"
    def is_heading(p):
        s = style_name(p).lower()
        return s.startswith("heading") or (p.text.strip().upper() in STRUCT or any(b in p.text.upper() for b in BIB))

    n_body = n_bad_align = n_noindent = n_smallfont = n_other_font = n_tight = 0
    for p in body_pars:
        t = p.text.strip()
        if is_heading(p):
            continue
        # Легитимные исключения из правил тела: подписи рисунков/источники,
        # формулы с номером, надписи таблиц (кегль/выравнивание там свои).
        if t.startswith(("Рисунок ", "Источник:", "Таблица ")) or re.search(r"\(\d+\)\s*$", t):
            continue
        n_body += 1
        pf = p.paragraph_format
        al = str(pf.alignment)
        if "JUSTIFY" not in al:
            n_bad_align += 1
        fi = pf.first_line_indent
        if fi is None or fi < Cm(0.8):
            n_noindent += 1
        for r in p.runs:
            if not (r.text or "").strip(): continue
            if r.font.size and r.font.size < Pt(13.5):
                n_smallfont += 1
            if r.font.name and r.font.name != "Times New Roman":
                n_other_font += 1
        ls = pf.line_spacing
        if ls is not None and abs(float(ls) - 1.5) > 0.06:
            n_tight += 1
    if n_bad_align: problems.append(f"Абзацев не по ширине: {n_bad_align}")
    if n_noindent: warns.append(f"Абзацев без красной строки 1,25 см: {n_noindent} (проверить: титул/содержание тоже считаются)")
    if n_smallfont: problems.append(f"Фрагментов текста мельче 14 pt: {n_smallfont}")
    if n_other_font: problems.append(f"Фрагментов не Times New Roman: {n_other_font}")
    if n_tight: warns.append(f"Абзацев с интервалом != 1.5: {n_tight}")

    # ── 4. Заголовки ──
    h1_list = [p for p in body if is_h1(p)]
    for p in h1_list:
        t = p.text.strip()
        pf = p.paragraph_format
        up_struct = t.isupper() or t.upper() in STRUCT
        if re.match(r"^\d+(\.\d+)*\.", t):
            problems.append(f"Точка после номера заголовка: «{t[:50]}»")
        if t.endswith("."):
            problems.append(f"Точка в конце заголовка: «{t[:50]}»")
        if not up_struct and re.match(r"^\d+\s", t):
            # раздел основной части: с абзацного отступа, слева
            fi = pf.first_line_indent
            if fi is None or fi < Cm(0.8):
                problems.append(f"Раздел без абзацного отступа: «{t[:50]}»")
        if up_struct and t.upper() in STRUCT or any(b in t.upper() for b in BIB):
            if "CENTER" not in str(pf.alignment):
                problems.append(f"Структурный элемент не по центру: «{t[:40]}»")
        if not pf.page_break_before and t.upper() != "СОДЕРЖАНИЕ":
            problems.append(f"Не с новой страницы: «{t[:50]}» (ГОСТ 7.32 п.6.2.2)")
        for r in p.runs:
            if (r.text or "").strip():
                if r.bold is not True:
                    warns.append(f"Заголовок не полужирный: «{t[:40]}»")
                    break

    # ── 5. Ссылки ──
    full = "\n".join(p.text for p in doc.paragraphs)
    broken = re.findall(r"\[\d+,\s*с\.\s*(?=[^\d\s]|\])|(?<!\d)\[\d+\](?!\s*,)", full)
    cites_with_page = re.findall(r"\[\d+,\s*с\.\s*\d+", full)
    if len(cites_with_page) < 3:
        warns.append(f"Ссылок вида [N, с. X] мало: {len(cites_with_page)}")

    # ── 6. Типографика ──
    if '"' in full:
        warns.append("Прямые кавычки \" вместо «ёлочек»")
    md = re.findall(r"(^|\s)(#{1,6}\s|\*\*)", full, flags=re.M)
    if md:
        problems.append(f"Markdown в тексте: {len(md)}")

    # ── 7. Содержание ──
    toc_zone = []
    in_toc = False
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t.upper().startswith("СОДЕРЖАНИЕ"):
            in_toc = True
            continue
        if in_toc:
            entry = t.split("\t")[0].strip()
            has_page = "\t" in t
            up = entry.upper()
            is_entry = (
                up in ("ВВЕДЕНИЕ", "ЗАКЛЮЧЕНИЕ")
                or re.match(r"^\d+(\.\d+)?\s+\S", entry)
                or any(b in up for b in BIB)
            )
            if is_entry and has_page:
                toc_zone.append(entry)
            else:
                break
    if not toc_zone:
        problems.append("Содержание пустое или не распознано")
    # все заголовки должны быть в содержании
    h1_texts = [p.text.strip() for p in h1_list if p.text.strip().upper() != "СОДЕРЖАНИЕ"]
    for ht in h1_texts:
        found = any(ht.lower()[:20] == tz.lower()[:20] for tz in toc_zone)
        if not found:
            warns.append(f"Заголовка нет в содержании: «{ht[:50]}»")
    if toc_zone and all("\t" not in (p.text or "") for p in doc.paragraphs if p.text.strip().upper().startswith(("ВВЕДЕНИЕ",)) is False):
        pass  # таб-стопы проверены выше по has_page

    print("=" * 60)
    print(f"ОШИБКИ ({len(problems)}):")
    for x in problems: print("  ✗", x)
    print(f"ПРЕДУПРЕЖДЕНИЯ ({len(warns)}):")
    for x in warns: print("  ⚠", x)
    print("=" * 60)
    return len(problems), len(warns)

if __name__ == "__main__":
    inspect(sys.argv[1])
