# -*- coding: utf-8 -*-
"""E2E: все типы документов + таблицы/формулы/рисунки."""
import os, io, sys
os.environ.setdefault("BOT_TOKEN", "123:TEST")

import main
from checker import validate_docx
from PIL import Image, ImageDraw

TXT = (
    "Расчёт индекса по данным 78 регионов показал значение 58,4 балла [6, с. 31]. "
    "Разрыв между Москвой и Тывой превышает 2,4 раза [7, с. 45].\n\n"
    "| Показатель | 2023 | 2024 |\n|---|---|---|\n| Рост, % | 12 | 18 |\n\n"
    "$$K = \\frac{P}{Q}$$\n\n"
    "Международный опыт показывает эффективность налоговых стимулов для работодателей "
    "в Германии и Франции [9, с. 15]. Аналогичные меры внедрены в Скандинавии."
)
BIB = (
    "1. Иванов, П.С. Цифровая экономика : монография / П.С. Иванов. — Москва: Экономика, 2021. — 320 с.\n"
    "2. Петрова, А.В. Адаптация занятых / А.В. Петрова // Вопросы экономики. — 2022. — № 4. — С. 42–58.\n"
    "3. Müller, H. Arbeitsmarkt / H. Müller. — Berlin: Springer, 2020. — 210 p."
)

def img():
    im = Image.new("RGB", (600, 400), (240, 240, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([50, 50, 550, 350], outline=(80, 80, 80), width=3)
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return {"bytes": buf.getvalue(), "caption": "Динамика показателей", "source": None}

CASES = {
    "referat": [
        ("ВВЕДЕНИЕ", 1, TXT, []),
        ("1 Глава первая", 1, "", [("1.1 Подглава один", TXT), ("1.2 Подглава два", TXT)]),
        ("ЗАКЛЮЧЕНИЕ", 1, TXT, []),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, BIB, []),
    ],
    "kursovaya": [
        ("ВВЕДЕНИЕ", 1, TXT, []),
        ("1 Теория вопроса", 1, "", [("1.1 Базовые понятия", TXT), ("1.2 Методика", TXT)]),
        ("2 Практический анализ", 1, "", [("2.1 Данные", TXT), ("2.2 Результаты", TXT)]),
        ("ЗАКЛЮЧЕНИЕ", 1, TXT, []),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, BIB, []),
    ],
    "doklad": [
        ("ВВЕДЕНИЕ", 1, TXT, []),
        ("1. Теоретические основы и ключевые понятия", 1, TXT, []),
        ("2. Факты, статистика и практические примеры", 1, TXT, []),
        ("ЗАКЛЮЧЕНИЕ", 1, TXT, []),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, BIB, []),
    ],
    "esse": [
        ("ВВЕДЕНИЕ", 1, TXT, []),
        ("ОСНОВНАЯ ЧАСТЬ", 1, TXT + "\n\n" + TXT, []),
        ("ЗАКЛЮЧЕНИЕ", 1, TXT, []),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, BIB, []),
    ],
    "article": [
        ("АННОТАЦИЯ И КЛЮЧЕВЫЕ СЛОВА / ABSTRACT AND KEYWORDS", 1, TXT, []),
        ("ВВЕДЕНИЕ", 1, TXT, []),
        ("ОБЗОР ЛИТЕРАТУРЫ", 1, TXT, []),
        ("МЕТОДОЛОГИЯ ИССЛЕДОВАНИЯ", 1, TXT, []),
        ("РЕЗУЛЬТАТЫ И ИХ ОБСУЖДЕНИЕ", 1, TXT, []),
        ("ЗАКЛЮЧЕНИЕ", 1, TXT, []),
        ("СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ", 1, BIB, []),
    ],
}

data = {
    "doc_type": "referat",
    "topic": "Тестовая тема исследования",
    "subject": "Дисциплина",
    "author": "Иванов И.И.",
    "group": "ЭК-31",
    "teacher": "Петрова А. В.",
    "teacher_post": "к.э.н., доцент",
    "institution": "МГУ",
    "city": "Москва",
}

fails = 0
for dtype, blocks in CASES.items():
    data["doc_type"] = dtype
    if dtype in ("referat", "kursovaya"):
        data["images"] = [img()]
        gost = main.get_gost_config(dtype)
        gost["image_width_cm"] = 8.5
    else:
        data.pop("images", None)
        gost = main.get_gost_config(dtype)
    blocks = main._apply_heading_format_to_blocks(blocks)
    b = main.build_docx_bytes(data, blocks, gost)
    path = f"/tmp/opencode/test_{dtype}.docx"
    with open(path, "wb") as f:
        f.write(b)
    res = validate_docx(path, doc_type=dtype)
    status = "PASS" if res.passed and not res.errors else "FAIL"
    print(f"[{status}] {dtype}: score={res.score}")
    for e in res.errors:
        print("   ERR:", e); fails += 1
    for w in res.warnings:
        print("   warn:", w)

print("\nTOTAL FAILS:", fails)
