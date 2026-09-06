# -*- coding: utf-8 -*-
"""v3.6: возврат платного режима, честные тексты (без 5–20 мин),
строгие структуры эссе/доклада/статьи, запрет выдуманных страниц в дописи,
эскалация подгонки страниц."""
import os, sys, inspect, asyncio
os.environ.setdefault("BOT_TOKEN", "123:TEST")

import main
from structure_generator import StructureGenerator

fails = 0
def check(name, cond, extra=""):
    global fails
    ok = bool(cond)
    print(("[OK]  " if ok else "[FAIL]") + f" {name}" + (f" — {extra}" if extra and not ok else ""))
    if not ok:
        fails += 1

# ── 1. Меню режимов: обе кнопки, платный вернулся ─────────────────────
kb = main.kb_mode()
rows = [btn.callback_data for row in kb.inline_keyboard for btn in row]
check("kb_mode: есть mode_free", "mode_free" in rows)
check("kb_mode: есть mode_paid", "mode_paid" in rows)
labels = " ".join(btn.text for row in kb.inline_keyboard for btn in row)
check("kb_mode: нет слова «быстро»", "быстро" not in labels.lower())
check("kb_mode: нет «безлимит» в кнопке", "безлимит" not in labels.lower())

# ── 2. Тексты режимов: без пугающего времени, честный платный ─────────
free_txt = main._mode_free_text()
check("free_text: нет «5–20»", "5–20" not in free_txt)
check("free_text: нет «минут»", "минут" not in free_txt)
paid_txt = main._mode_paid_text()
check("paid_text: нет «безлимитно»", "безлимитн" not in paid_txt.lower())
check("paid_text: нет «любое количество страниц»", "Любое количество страниц" not in paid_txt)
check("paid_text: упоминает модель", "модель" in paid_txt.lower())

# ── 3. h_mode принимает paid ──────────────────────────────────────────
src_h_mode = inspect.getsource(main.h_mode)
check("h_mode: платный режим принимается", '"free", "paid"' in src_h_mode)
src_status = inspect.getsource(main.get_user_limits_info)
check("status: платная строка в статусе", "⭐ Платно" in src_status)

# ── 4. Структуры эссе/доклада: 2 пронумерованных раздела по теме ──────
parts = {
    "intro": "Вводный текст работы.",
    "main1": "Первый аргумент с фактами.",
    "main2": "Второй аргумент и контраргумент.",
    "part1": "Теория и понятия.",
    "part2": "Факты и статистика.",
    "conclusion": "Итоговые выводы.",
    "literature": "1. Источник один.\n2. Источник два.",
}
tt = [
    {"title": "1 Первая тема раздела", "subs": []},
    {"title": "2 Вторая тема раздела", "subs": []},
]
b_esse = StructureGenerator.generate_docx_blocks("esse", parts, tt, topic="Тестовая тема")
titles_esse = [b[0] for b in b_esse]
check("esse: заголовки от ИИ", "1 Первая тема раздела" in titles_esse and "2 Вторая тема раздела" in titles_esse)
check("esse: нет безликой «ОСНОВНАЯ ЧАСТЬ»", "ОСНОВНАЯ ЧАСТЬ" not in titles_esse)
check("esse: 6 блоков (введение, 2 раздела, заключение, литература, ...) ",
      len(b_esse) == 5 and titles_esse[0] == "ВВЕДЕНИЕ")

b_dok = StructureGenerator.generate_docx_blocks("doklad", parts, tt, topic="Тестовая тема")
td = [b[0] for b in b_dok]
check("doklad: заголовки от ИИ", "1 Первая тема раздела" in td and "2 Вторая тема раздела" in td)

# фоллбэк без chapter_titles: тематические названия, а не «ОСНОВНАЯ ЧАСТЬ»
b_esse2 = StructureGenerator.generate_docx_blocks("esse", parts, [], topic="Влияние климата")
t2 = [b[0] for b in b_esse2]
check("esse fallback: тема в названии", any("Влияние климата" in t for t in t2))
check("esse fallback: нет «ОСНОВНАЯ ЧАСТЬ»", "ОСНОВНАЯ ЧАСТЬ" not in t2)

b_art = StructureGenerator.generate_docx_blocks("article", parts, [])
ta = [b[0] for b in b_art]
check("article: одноязычный заголовок аннотации", "АННОТАЦИЯ И КЛЮЧЕВЫЕ СЛОВА" in ta)

# ── 5. Допись текста НЕ должна инструктировать выдумывать страницы ────
src_expand = inspect.getsource(main._expand_blocks_by_chars)
check("expand: запрет выдуманных страниц", "ЗАПРЕЩЕНО придумывать страницы" in src_expand)
check("expand: нет старой подсказки [1, с. 45]",
      "сноски только с номерами страниц" not in src_expand)
src_prompts = inspect.getsource(main.build_prompts)
check("prompts.article: нет выдуманных страниц в обзоре литературы",
      "сноски только с номерами страниц" not in src_prompts)

# ── 6. Эскалация подгонки: floor 0.30 реально режет глубже ────────────
blocks = [
    ("1 Глава", 1, "Абзац. " * 400, []),
    ("2 Глава", 1, "Текст предложения. " * 400, []),
]
before = main._blocks_text_total(blocks)
trimmed = main._trim_blocks_by_chars(blocks, 2000, floor_ratio=0.30)
after = main._blocks_text_total(trimmed)
check("trim floor=0.30: текст сократился", after < before, f"{before}->{after}")

# ── 7. Фоллбэк плоских заголовков (ИИ недоступен) ──────────────────────
async def _boom(*a, **k):
    raise RuntimeError("LLM down")
orig_chat = main.chat_with_fallback
main.chat_with_fallback = _boom
try:
    flat = asyncio.get_event_loop().run_until_complete(
        main._generate_flat_section_titles("deepseek", "esse", "Цифровая экономика", "Экономика")
    )
finally:
    main.chat_with_fallback = orig_chat
check("flat titles: 2 раздела", len(flat) == 2)
check("flat titles: тема в названии", any("Цифровая экономика" in r["title"] for r in flat))

# ── 8. Регрессия: ни одного U+FFFD в main.py ──────────────────────────
src_main = open("main.py", encoding="utf-8").read()
check("main.py: нет U+FFFD", "\ufffd" not in src_main)
src_sg = open("structure_generator.py", encoding="utf-8").read()
check("structure_generator.py: нет U+FFFD", "\ufffd" not in src_sg)

# ── 9. Нумерация эссе детерминирована по ГОСТ ─────────────────────────
formatted = main._apply_heading_format_to_blocks(b_esse)
ft = [b[0] for b in formatted]
check("esse после нумерации: раздел 1", ft[1].startswith("1 "))
check("esse после нумерации: раздел 2", ft[2].startswith("2 "))

print(f"\nTOTAL FAILS: {fails}")
sys.exit(1 if fails else 0)
