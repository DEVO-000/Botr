# -*- coding: utf-8 -*-
"""Tests for the humanizer module.  Run: python3 test_humanizer.py"""
import re
import sys

import humanizer as H

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   " + name)
    else:
        print("  FAIL " + name + " " + str(detail))
        FAILED.append(name)


AI_TEXT = (
    "\u0412 \u0441\u043e\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e\u043c \u043c\u0438\u0440\u0435 \u0434\u0430\u043d\u043d\u0430\u044f \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u0430\u0442\u0438\u043a\u0430 \u0448\u0438\u0440\u043e\u043a\u043e \u043e\u0431\u0441\u0443\u0436\u0434\u0430\u0435\u0442\u0441\u044f "
    "\u0432 \u043b\u0438\u0442\u0435\u0440\u0430\u0442\u0443\u0440\u0435 [1, \u0441. 45]. \u0421\u043b\u0435\u0434\u0443\u0435\u0442 \u043e\u0442\u043c\u0435\u0442\u0438\u0442\u044c, \u0447\u0442\u043e \u0440\u0435\u0433\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 "
    "\u043e\u043f\u0438\u0440\u0430\u0435\u0442\u0441\u044f \u043d\u0430 \u0442\u0440\u0438 \u043c\u0435\u0445\u0430\u043d\u0438\u0437\u043c\u0430 [2, \u0441. 12].\n\n"
    "\u0422\u0430\u043a\u0438\u043c \u043e\u0431\u0440\u0430\u0437\u043e\u043c, \u0440\u0435\u0444\u043e\u0440\u043c\u0430 \u0438\u0437\u043c\u0435\u043d\u0438\u043b\u0430 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0443 \u0440\u044b\u043d\u043a\u0430 [3, \u0441. 78]. "
    "\u0422\u0430\u043a\u0438\u043c \u043e\u0431\u0440\u0430\u0437\u043e\u043c, \u0432\u044b\u0448\u0435\u0443\u043a\u0430\u0437\u0430\u043d\u043d\u044b\u0435 \u043c\u0435\u0440\u044b \u0434\u0430\u043b\u0438 \u044d\u0444\u0444\u0435\u043a\u0442 [4, \u0441. 90].\n\n"
    "\u0411\u0435\u0437\u0443\u0441\u043b\u043e\u0432\u043d\u043e, \u0432 \u043d\u0430\u0441\u0442\u043e\u044f\u0449\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u0441\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0430\u0435\u0442 \u0432\u044b\u0432\u043e\u0434 [5, \u0441. 33]."
)

print("1. Cliche removal")
out = H.humanize(AI_TEXT)
for bad in ("\u0412 \u0441\u043e\u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e\u043c \u043c\u0438\u0440\u0435", "\u0421\u043b\u0435\u0434\u0443\u0435\u0442 \u043e\u0442\u043c\u0435\u0442\u0438\u0442\u044c",
            "\u0422\u0430\u043a\u0438\u043c \u043e\u0431\u0440\u0430\u0437\u043e\u043c", "\u0411\u0435\u0437\u0443\u0441\u043b\u043e\u0432\u043d\u043e",
            "\u0432 \u043d\u0430\u0441\u0442\u043e\u044f\u0449\u0435\u0435 \u0432\u0440\u0435\u043c\u044f", "\u0434\u0430\u043d\u043d\u0430\u044f "):
    check("removed " + bad, bad.lower() not in out.lower(), out[:160])

print("\n2. GRAMMAR SAFETY (regression: v1 produced 'etaya')")
for broken in ("\u044d\u0442\u0430\u044f", "\u044d\u0442\u043e\u0435", " ,", ",,"):
    check("no '" + broken + "'", broken not in out, out)
for sent in H.split_sentences(out):
    check("sane: " + sent[:40], not H._looks_broken(sent), sent)

print("\n3. GOST citations preserved")
c1 = sorted(re.findall(r"\[\d+, \u0441\.\s*\d+\]", AI_TEXT.replace("\u00a0", " ")))
c2 = sorted(re.findall(r"\[\d+, \u0441\.\s*\d+\]", out.replace("\u00a0", " ")))
check("all 5 citations kept", c1 == c2, str(c1) + " != " + str(c2))
check("citations_preserved()", H.citations_preserved(AI_TEXT, out))

print("\n4. ai_score drops")
before, after = H.ai_score(AI_TEXT), H.ai_score(out)
check("score " + str(before) + " -> " + str(after), after < before)

print("\n5. Idempotent")
check("humanize(humanize(x)) == humanize(x)", H.humanize(out) == out)

print("\n6. Tables / formulas / URLs intact")
tbl = ("| A | B |\n| --- | --- |\n| 1 | 2 |\n\n$ E = mc^2 $\n\n"
       "\u0422\u0430\u043a\u0438\u043c \u043e\u0431\u0440\u0430\u0437\u043e\u043c, \u0440\u0430\u0441\u0447\u0451\u0442 \u0432\u0435\u0440\u0435\u043d \u0438 \u043f\u0440\u043e\u0432\u0435\u0440\u0435\u043d.")
tout = H.humanize(tbl)
check("table row intact", "| --- | --- |" in tout, tout)
check("formula intact", "$ E = mc^2 $" in tout, tout)
doi = "https://doi.org/10.1111/aepr.12226"
check("URL intact", doi in H.humanize("\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a: " + doi + " \u2014 \u0434\u0430\u043d\u043d\u044b\u0435 \u0435\u0441\u0442\u044c."))

print("\n7. Long sentence split on safe boundary (semicolon)")
long_s = ("\u0420\u0435\u0433\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0442\u0430\u0440\u0438\u0444\u043e\u0432 \u043c\u0435\u043d\u044f\u0435\u0442 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0443 \u0438\u043c\u043f\u043e\u0440\u0442\u0430 "
          "\u0438 \u044d\u043a\u0441\u043f\u043e\u0440\u0442\u0430 \u0432 \u0434\u043e\u043b\u0433\u043e\u0441\u0440\u043e\u0447\u043d\u043e\u0439 \u043f\u0435\u0440\u0441\u043f\u0435\u043a\u0442\u0438\u0432\u0435; "
          "\u043a\u0440\u0443\u043f\u043d\u044b\u0435 \u044d\u043a\u0441\u043f\u043e\u0440\u0442\u0451\u0440\u044b \u043c\u0435\u043d\u044f\u044e\u0442 \u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 \u043d\u0430 \u0432\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0435\u043c "
          "\u0440\u044b\u043d\u043a\u0435 \u0432 \u0442\u0435\u0447\u0435\u043d\u0438\u0435 \u0432\u0441\u0435\u0433\u043e \u0440\u0430\u0441\u0441\u043c\u0430\u0442\u0440\u0438\u0432\u0430\u0435\u043c\u043e\u0433\u043e \u043f\u0435\u0440\u0438\u043e\u0434\u0430.")
res = H.vary_rhythm(long_s)
check("split into 2+", len(H.split_sentences(res)) >= 2, res)

print("\n8. 'a takzhe' must NOT be split (would orphan the subject)")
risky = ("\u0420\u0435\u0433\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043c\u0435\u043d\u044f\u0435\u0442 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0443 \u0438\u043c\u043f\u043e\u0440\u0442\u0430 \u0438 \u044d\u043a\u0441\u043f\u043e\u0440\u0442\u0430 "
         "\u0432 \u0434\u043e\u043b\u0433\u043e\u0441\u0440\u043e\u0447\u043d\u043e\u0439 \u043f\u0435\u0440\u0441\u043f\u0435\u043a\u0442\u0438\u0432\u0435, \u0430 \u0442\u0430\u043a\u0436\u0435 \u043c\u0435\u043d\u044f\u0435\u0442 \u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 "
         "\u043a\u0440\u0443\u043f\u043d\u044b\u0445 \u044d\u043a\u0441\u043f\u043e\u0440\u0442\u0451\u0440\u043e\u0432 \u043d\u0430 \u0432\u043d\u0443\u0442\u0440\u0435\u043d\u043d\u0435\u043c \u0440\u044b\u043d\u043a\u0435 \u0441\u0442\u0440\u0430\u043d\u044b \u0441\u0435\u0433\u043e\u0434\u043d\u044f.")
check("kept as one sentence", len(H.split_sentences(H.vary_rhythm(risky))) == 1)

print("\n9. Edge cases do not crash")
for v in ("", "   ", "Short.", None):
    try:
        H.humanize(v or "")
        H.ai_score(v or "")
        H.report(v or "")
        check("input " + repr(v), True)
    except Exception as e:
        check("input " + repr(v), False, str(e))

print("\n10. rewrite_prompt shape")
msgs = H.rewrite_prompt(AI_TEXT, topic="Test")
check("2 messages", len(msgs) == 2 and msgs[0]["role"] == "system")
check("text embedded", AI_TEXT[:40] in msgs[1]["content"])
check("citations_preserved catches loss", not H.citations_preserved("[1] [2]", "[1]"))

print("\n" + "=" * 62)
print("BEFORE score=" + str(before) + "   AFTER score=" + str(after))
print("=" * 62)
print(out)
print("=" * 62)
if FAILED:
    print("FAILED: " + str(len(FAILED)) + " -> " + str(FAILED))
    sys.exit(1)
print("ALL TESTS PASSED")
