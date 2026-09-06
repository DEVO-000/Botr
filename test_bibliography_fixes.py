# -*- coding: utf-8 -*-
"""Тесты исправлений библиографии (main.py): дата обращения не слипается,
инициалы-без-фамилии отбрасываются.
Запуск: python3 test_bibliography_fixes.py
"""
import os, sys
os.environ.setdefault("BOT_TOKEN", "123:TEST")

import main

FAILED = []
def check(name, cond, detail=""):
    if cond:
        print("  ok   " + name)
    else:
        print("  FAIL " + name + "  " + str(detail))
        FAILED.append(name)


print("1. Дата обращения не слипается (регрессия «датаобращения»)")
item = ("Amosova I.Y, Ilicheva E. A. Spatial Distribution // "
        "The Bulletin of Irkutsk State University. — 2020. — "
        "URL: https://doi.org/10.26516/2073-3402.2020.34.21")
norm = main._normalize_bibliography(item)
check("пробел перед (дата", " (дата обращения:" in norm or norm.endswith("(дата обращения:"), norm)
check("нет слитого датаобращения", "датаобращения" not in norm, norm)
check("нет слипшегося двоеточия", "дата обращения:" in norm, norm)
check("есть сегодняшняя дата", "дата обращения:" in norm, norm)

print("\n2. Даже уже-слитый суффикс исправляется")
glued = item + "(датаобращения:01.01.2024)"
norm2 = main._normalize_bibliography(glued)
check("рассклеен", "датаобращения" not in norm2 and "дата обращения:" in norm2, norm2)

print("\n3. Инициалы без фамилии в начале отбрасываются")
junk = "А. Ю. Х. Анализ влияния морфометрических особенностей рельефа // Вестник. — 2026."
check("3 инициала без фамилии → брак", main._is_bad_literature_line(junk), junk)
ok = "Иванов И. И. Книга о Байкале. — М., 2020."
check("И. И. + фамилия → норма", not main._is_bad_literature_line(ok), ok)
ok2 = "Hampton S. E., Izmest'eva L. R. Sixty years // Global Change Biology. — 2008."
check("латинские инициалы после фамилии → норма", not main._is_bad_literature_line(ok2), ok2)

print("\n" + "=" * 62)
if FAILED:
    print("FAILED: " + str(len(FAILED)) + " -> " + str(FAILED))
    sys.exit(1)
print("ALL TESTS PASSED")
