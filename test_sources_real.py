# -*- coding: utf-8 -*-
"""Тесты модуля sources_real без сети (HTTP подменён фейковой сессией).

Запуск:  python3 test_sources_real.py

Главное, что здесь проверяется: модуль НИКОГДА не выдумывает источники.
"""
import asyncio
import json
import sys

import sources_real as S

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   " + name)
    else:
        print("  FAIL " + name + "  " + str(detail))
        FAILED.append(name)


# ── Фейковый HTTP ────────────────────────────────────────────────────────

class _Content:
    def __init__(self, body: bytes):
        self._body = body

    async def read(self, limit=None):
        return self._body[:limit] if limit else self._body


class _Resp:
    def __init__(self, status=200, text=""):
        self.status = status
        self._text = text
        self.content = _Content(text.encode("utf-8"))

    async def text(self):
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Отдаёт заранее заданные ответы по подстроке URL. Считает запросы."""

    def __init__(self, routes, head_status=None):
        self.routes = routes
        self.head_status = head_status or {}
        self.calls = []

    def _match(self, url):
        for frag, payload in self.routes.items():
            if frag in url:
                return payload
        return (404, "")

    def get(self, url, **kw):
        self.calls.append(("get", url))
        status, text = self._match(url)
        return _Resp(status, text)

    def head(self, url, **kw):
        self.calls.append(("head", url))
        for frag, status in self.head_status.items():
            if frag in url:
                return _Resp(status, "")
        status, text = self._match(url)
        return _Resp(status, "")

    async def close(self):
        pass


CROSSREF = json.dumps({"message": {"items": [{
    "DOI": "10.1234/abcd.2021.55",
    "title": ["Таможенное регулирование импорта в условиях санкций"],
    "author": [{"family": "Иванов", "given": "Сергей Петрович"},
               {"family": "Петрова", "given": "Анна"}],
    "issued": {"date-parts": [[2021]]},
    "container-title": ["Вопросы экономики"],
    "volume": "14", "issue": "3", "page": "45-58",
    "type": "journal-article", "language": "ru",
}]}}, ensure_ascii=False)

OPENALEX = json.dumps({"results": [{
    "display_name": "Импорт и таможенные пошлины: эмпирический анализ",
    "authorships": [{"author": {"display_name": "John Smith"}}],
    "publication_year": 2020,
    "primary_location": {"source": {"display_name": "World Economy"},
                         "landing_page_url": "https://example.org/w1"},
    "biblio": {"volume": "7", "issue": "2", "first_page": "10", "last_page": "20"},
    "doi": "https://doi.org/10.5555/dead.beef",
    "type": "article", "language": "en",
}]}, ensure_ascii=False)

S2 = json.dumps({"data": [{
    "title": "Tariffs and trade flows",
    "year": 2019,
    "authors": [{"name": "Alice Brown"}],
    "journal": {"name": "Journal of Trade", "volume": "3", "pages": "1-15"},
    "externalIds": {"DOI": "10.7777/jt.2019.3"},
    "url": "https://example.org/s2",
}]}, ensure_ascii=False)

DOI_OK = json.dumps({"responseCode": 1, "handle": "10.1234/abcd.2021.55"})

HTML_GOOD = """<html><head>
<meta property="og:title" content="Регулирование импорта: практика 2023 года">
<meta name="author" content="Смирнов Игорь Валентинович">
<meta property="article:published_time" content="2023-04-11T10:00:00Z">
<meta property="og:site_name" content="Экономический вестник">
<title>Регулирование импорта: практика 2023 года | Экономический вестник</title>
</head><body><h1>Заголовок</h1></body></html>"""

HTML_JUNK = ('<html><head><title>Just a moment...</title></head>'
             '<body>captcha</body></html>')


def run(coro):
    return asyncio.run(coro)


# ── 1. Нормализация DOI ──────────────────────────────────────────────────
print("1. Нормализация DOI")
check("https-префикс срезан",
      S._clean_doi("https://doi.org/10.1234/ab.cd") == "10.1234/ab.cd")
check("doi: срезан", S._clean_doi("doi: 10.1234/ab.cd") == "10.1234/ab.cd")
check("точка на конце срезана",
      S._clean_doi("10.1234/ab.cd.") == "10.1234/ab.cd")
check("мусор отвергнут", S._clean_doi("не-doi") == "")
check("пустое отвергнуто", S._clean_doi("") == "")

# ── 2. Инициалы и авторы по ГОСТ ─────────────────────────────────────────
print("\n2. Авторы по ГОСТ")
check("русское ФИО", S._initials("Иванов Сергей Петрович") == "Иванов С. П.",
      S._initials("Иванов Сергей Петрович"))
check("латиница переворачивается", S._initials("John Smith") == "Smith J.",
      S._initials("John Smith"))
check("4+ авторов → [и др.]",
      S._authors_gost(["А Б В", "Г Д Е", "Ж З И", "К Л М"])[1].endswith("[и др.]"))
check("2 автора перечислены",
      "," in S._authors_gost(["Иванов Иван", "Петров Петр"])[1])
check("без авторов пусто", S._authors_gost([]) == ("", ""))

# ── 3. Оформление по ГОСТ ────────────────────────────────────────────────
print("\n3. Оформление по ГОСТ")
art = S.SourceRecord(
    title="Таможенное регулирование импорта",
    authors=["Иванов Сергей Петрович"], year="2021",
    container="Вопросы экономики", volume="14", issue="3",
    pages="45-58", doi="10.1234/abcd", kind="article")
line = S.format_gost(art)
print("     " + line)
for frag in ("Иванов С. П.", "Вопросы экономики", "2021", "Т. 14", "№ 3",
             "С. 45", "URL: https://doi.org/10.1234/abcd"):
    check("содержит " + frag, frag in line, line)
check("заканчивается точкой", line.endswith("."))

web = S.SourceRecord(title="Регулирование импорта: практика", year="2023",
                     container="Экономический вестник",
                     url="https://example.org/a", kind="web")
wline = S.format_gost(web)
print("     " + wline)
check("веб-ресурс помечен", "[Электронный ресурс]" in wline, wline)
check("веб-ресурс с URL", "URL: https://example.org/a" in wline)

# ── 4. Заглушки заблокированы (ключевое требование) ──────────────────────
print("\n4. Заглушки заблокированы")
for bad in ("Поисковая выдача научных публикаций по теме «Х»",
            "Материал с сайта по теме исследования",
            "Just a moment...", "404 Not Found", "Страница не найдена"):
    rec = S.SourceRecord(title=bad, url="https://example.org/x")
    check("отвергнуто: " + bad[:34], not rec.is_usable(), bad)
check("запись без URL отвергнута",
      not S.SourceRecord(title="Вполне нормальное название статьи").is_usable())
check("нормальная запись принята", art.is_usable())

# ── 5. Разбор метаданных страницы ────────────────────────────────────────
print("\n5. Метаданные страницы")
check("og:title", S._page_title(HTML_GOOD).startswith("Регулирование импорта"),
      S._page_title(HTML_GOOD))
check("хвост сайта срезан",
      "Экономический вестник" not in S._clean_site_title(S._page_title(HTML_GOOD)))
check("автор найден", "Смирнов" in S._meta(HTML_GOOD, "author"))

sess = FakeSession({"good": (200, HTML_GOOD), "junk": (200, HTML_JUNK),
                    "gone": (404, "")})
rec = run(S.extract_web_metadata(sess, "https://example.org/good"))
check("метаданные извлечены", rec is not None and rec.year == "2023", rec)
check("автор разобран", rec and rec.authors and "Смирнов" in rec.authors[0], rec)
check("источник помечен проверенным", rec and rec.verified)
check("captcha-страница → None",
      run(S.extract_web_metadata(sess, "https://example.org/junk")) is None)
check("404 → None (а не заглушка)",
      run(S.extract_web_metadata(sess, "https://example.org/gone")) is None)

# ── 6. Разбор ответов каталогов ──────────────────────────────────────────
print("\n6. Каталоги")
cs = FakeSession({"api.crossref.org": (200, CROSSREF),
                  "api.openalex.org": (200, OPENALEX),
                  "semanticscholar.org": (200, S2)})
cr = run(S.search_crossref(cs, "импорт"))
check("crossref: 1 запись", len(cr) == 1, cr)
check("crossref: DOI", cr and cr[0].doi == "10.1234/abcd.2021.55")
check("crossref: 2 автора", cr and len(cr[0].authors) == 2)
check("crossref: год", cr and cr[0].year == "2021")

oa = run(S.search_openalex(cs, "импорт"))
check("openalex: DOI без префикса", oa and oa[0].doi == "10.5555/dead.beef", oa)
check("openalex: страницы склеены", oa and oa[0].pages == "10-20")

s2 = run(S.search_semantic_scholar(cs, "tariffs"))
check("s2: DOI", s2 and s2[0].doi == "10.7777/jt.2019.3", s2)

bad_sess = FakeSession({"api.crossref.org": (500, "")})
check("HTTP 500 → пустой список, не исключение",
      run(S.search_crossref(bad_sess, "импорт")) == [])

# ── 7. Проверка существования ────────────────────────────────────────────
print("\n7. Проверка существования")
vs = FakeSession({"doi.org/api/handles/10.1234": (200, DOI_OK),
                  "doi.org/api/handles": (404, "")})
check("живой DOI подтверждён", run(S.verify_doi(vs, "10.1234/abcd.2021.55")))
check("выдуманный DOI отвергнут", not run(S.verify_doi(vs, "10.9999/fake.doi")))
check("мусорный DOI отвергнут без запроса", not run(S.verify_doi(vs, "nope")))

hs = FakeSession({"example.org": (200, "ok")}, head_status={"noheadok": 403})
check("HEAD 403 → откат к GET",
      run(S.verify_url(hs, "https://example.org/noheadok")))
check("нет URL → False", not run(S.verify_url(hs, "")))

# ── 8. Релевантность ─────────────────────────────────────────────────────
print("\n8. Релевантность")
toks = S._tokens("Таможенное регулирование импорта")
check("по теме — высокая", S.relevance(art, toks) > 0.5, S.relevance(art, toks))
off = S.SourceRecord(title="Разведение пчёл в средней полосе", container="Пчеловодство")
check("не по теме — низкая", S.relevance(off, toks) < 0.2, S.relevance(off, toks))

# ── 9. Оркестрация: НИКАКИХ выдумок ──────────────────────────────────────
print("\n9. Оркестрация: никаких выдумок")
empty = FakeSession({})
res = run(S.find_real_sources("Тема без источников", target=20, session=empty))
check("нет данных → пустой список", res == [], res)

full = FakeSession({"api.crossref.org": (200, CROSSREF),
                    "api.openalex.org": (200, OPENALEX),
                    "semanticscholar.org": (200, S2),
                    "doi.org/api/handles/10.1234": (200, DOI_OK),
                    "doi.org/api/handles": (404, "")})
res = run(S.find_real_sources("Таможенное регулирование импорта",
                              target=20, min_relevance=0.0, session=full))
check("остались только проверенные", all(r.verified for r in res), res)
check("неподтверждённые DOI отброшены",
      all(r.doi != "10.5555/dead.beef" for r in res),
      [r.doi for r in res])
check("подтверждённый DOI остался",
      any(r.doi == "10.1234/abcd.2021.55" for r in res), [r.doi for r in res])
check("список не добит до target", len(res) < 20)

lines = run(S.build_bibliography("Таможенное регулирование импорта",
                                 target=20, session=full))
print("     записей: " + str(len(lines)))
for ln in lines:
    print("     " + ln)
check("каждая запись с URL", all("URL:" in ln for ln in lines), lines)
check("каждая запись с точкой", all(ln.endswith(".") for ln in lines))

FORBIDDEN = ("Поисковая выдача", "Материал с сайта", "по теме исследования",
             "scholar.google", "cyberleninka.ru/search", "elibrary.ru/query")
blob = " ".join(lines)
for bad in FORBIDDEN:
    check("нет фабрикации: " + bad, bad not in blob)

# ── 10. Синхронная обёртка ───────────────────────────────────────────────
print("\n10. Синхронная обёртка")


async def _inside_loop():
    try:
        S.build_bibliography_sync("тема")
        return False
    except RuntimeError:
        return True


check("внутри loop — понятная ошибка", run(_inside_loop()))

print("\n" + "=" * 62)
if FAILED:
    print("FAILED: " + str(len(FAILED)) + " -> " + str(FAILED))
    sys.exit(1)
print("ALL TESTS PASSED")


# ── 11. Google Scholar (без API, парсинг HTML) ────────────────────────
GS_HTML = """<html><body>
<div class="gs_r"><div class="gs_ri">
<h3 class="gs_rt"><a href="https://www.sciencedirect.com/science/article/pii/123"
  >Импорт и тарифная политика: опыт санкционных ограничений</a></h3>
<div class="gs_a">Иванов С. П., Петрова А. — Вопросы экономики, 2021</div>
</div></div>
<div class="gs_r"><div class="gs_ri">
<h3 class="gs_rt"><a href="https://scholar.google.com/scholar?cites=123"
  >Служебная карточка, которую надо пропустить</a></h3>
<div class="gs_a">Аноним — Тест, 2020</div>
</div></div>
</body></html>"""

print("\n11. Google Scholar (без API, парсинг HTML)")
gs_items = S._parse_google_scholar(GS_HTML)
check("2 карточки на входе, 1 рабочая на выходе", len(gs_items) == 1, gs_items)
if gs_items:
    it = gs_items[0]
    check("gs: название настоящее", "Импорт и тарифная" in it["title"], it["title"])
    check("gs: URL издателя (не scholar.google)", "sciencedirect.com" in it["url"], it["url"])
    check("gs: год", it["year"] == "2021", it)
    check("gs: авторы", "Иванов С. П." in it["authors"][0], it.get("authors"))

gs_sess = FakeSession({"scholar.google.com": (200, GS_HTML)})
gs_res = run(S.search_google_scholar(gs_sess, "импорт тарифы"))
check("gs search: вернул рабочую запись", len(gs_res) == 1, gs_res)
check("gs search: без scholar.google в URL", all("scholar.google" not in r.url for r in gs_res), gs_res)

# Капча/блокировка → пустой список, не исключение и не фабрикация.
cap_sess = FakeSession({"scholar.google.com": (200, "<title>Just a moment...</title>")})
check("gs: капча → пустой список",
      run(S.search_google_scholar(cap_sess, "импорт")) == [], )
