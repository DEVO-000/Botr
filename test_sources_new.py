# -*- coding: utf-8 -*-
"""Тесты новых источников (v3.4): КиберЛенинка, arXiv, DOAJ, PubMed, Google Books.
Все тесты офлайн — на фикстурах. Запуск: python3.13 test_sources_new.py
"""
import asyncio
import io
import sys
import types

sys.path.insert(0, "/home/z/my-project/J.")

import sources_real
from sources_real import (
    SourceRecord,
    _parse_cyberleninka_search,
    search_arxiv,
    search_doaj,
    search_pubmed,
    search_google_books,
    find_real_sources,
    format_gost,
)

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  ok   " + name)
    else:
        print("  FAIL " + name + "  " + str(detail))
        FAILED.append(name)


# ─────────────────────────────────────────────
print("1. КиберЛенинка: парсер карточек поиска")
html = '''
<div class="results">
<a href="/article/n/osobennosti-tsifrovoy-transformatsii-obrazovaniya">Особенности цифровой трансформации образования в вузе</a>
<a href="/article/n/second-slug-xyz" class="other">Правовое регулирование ИИ в Российской Федерации</a>
<a href="/article/n/second-slug-xyz">Дубль той же статьи — должен быть отброшен</a>
<a href="/article/n/short">кратко</a>
<a href="https://example.com/article/n/external">Внешний сайт — не берём</a>
</div>
'''
urls = _parse_cyberleninka_search(html)
check("найдено 2 уникальные статьи", len(urls) == 2, urls)
check("слаг первой корректен", urls and "osobennosti" in urls[0])
check("короткие заголовки отброшены", all("short" not in u for u in urls))
check("внешние ссылки отброшены", all("example.com" not in u for u in urls))

# ─────────────────────────────────────────────
print("2. arXiv: разбор Atom-выдачи")
ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
  <id>http://arxiv.org/abs/2306.14753v1</id>
  <title>A Study of Machine Learning
    Methods</title>
  <published>2023-06-26T17:59:59Z</published>
  <author><name>John Smith</name></author>
  <author><name>Jane Doe</name></author>
  <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.48550/arXiv.2306.14753</arxiv:doi>
</entry>
<entry>
  <id>http://arxiv.org/abs/2307.05639v2</id>
  <title>Second Paper Without Authors</title>
  <published>2023-07-12T00:00:00Z</published>
</entry>
</feed>"""


class FakeResp:
    """Мимикрирует под aiohttp-ответ для sources_real._get_text."""

    status = 200

    def __init__(self, body: str = ""):
        self._body = body.encode("utf-8")
        self.content = types.SimpleNamespace(read=lambda limit: asyncio.sleep(0, result=self._body))

    async def text(self):
        return self._body.decode("utf-8")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, body: str = ""):
        self._body = body

    def get(self, url, **kwargs):
        return FakeResp(self._body)


recs = asyncio.run(search_arxiv(FakeSession(ARXIV_XML), "machine learning", limit=5))
check("разобрано 2 записи", len(recs) == 2, len(recs))
check("многострочный title очищен", recs and recs[0].title == "A Study of Machine Learning Methods", recs[0].title if recs else "-")
check("авторы arXiv", recs[0].authors == ["John Smith", "Jane Doe"])
check("год из published", recs[0].year == "2023")
check("DOI распознан", recs[0].doi.startswith("10.48550/"), recs[0].doi)

# ─────────────────────────────────────────────
print("3. DOAJ: разбор JSON")
DOAJ_JSON = """{"total":1,"results":[{"bibjson":{
  "title":"Deep Learning for Crop Disease Detection",
  "author":[{"name":"Alice A."},{"name":"Bob B."}],
  "journal":{"title":"Agricultural AI Review"},
  "year":"2024","volume":"12","start_page":"100","end_page":"115",
  "identifier":[{"type":"doi","id":"10.1000/agri.2024.001"}],
  "link":[{"type":"fulltext","url":"https://doaj.org/article/xyz"}]
}}]}"""


recs = asyncio.run(search_doaj(FakeSession(DOAJ_JSON), "crop disease", limit=5))
check("запись разобрана", len(recs) == 1)
check("журнал и год", recs[0].container == "Agricultural AI Review" and recs[0].year == "2024")
check("DOI извлечён", recs[0].doi == "10.1000/agri.2024.001")
check("ГОСТ-запись строится", "Deep Learning" in format_gost(recs[0]))

# ─────────────────────────────────────────────
print("4. PubMed: esearch + esummary")
PUBMED_SEARCH = """{"esearchresult":{"idlist":["39123456"]}}"""
PUBMED_SUM = """{"result":{"39123456":{
  "title":"Insulin resistance and cardiovascular risk: a cohort study.",
  "authors":[{"name":"Ivanov I"},{"name":"Petrov P"}],
  "source":"BMJ Open Diabetes","pubdate":"2024 Mar 15",
  "articleids":[{"idtype":"doi","value":"10.1000/bmjod.2024.77"}]
}}}"""


class SwitchSession(FakeSession):
    def get(self, url, **kwargs):
        body = PUBMED_SEARCH if "esearch" in url else PUBMED_SUM
        return FakeResp(body)


recs = asyncio.run(search_pubmed(SwitchSession(), "insulin", limit=5))
check("PubMed запись разобрана", len(recs) == 1 and "Insulin resistance" in recs[0].title)
check("год PubMed", recs[0].year == "2024")
check("DOI PubMed", recs[0].doi == "10.1000/bmjod.2024.77")

# ─────────────────────────────────────────────
print("5. Google Books: книги с автором берутся, без автора — нет")
BOOKS_JSON = """{"items":[
 {"volumeInfo":{"title":"Цифровая экономика: монография","authors":["Иванов П. С."],
  "publishedDate":"2021","publisher":"Экономика","pageCount":320,"language":"ru",
  "canonicalVolumeLink":"https://books.google.com/books?id=abc"}},
 {"volumeInfo":{"title":"Безавторский сборник материалов конференции 2020","publishedDate":"2020"}}
]}"""


recs = asyncio.run(search_google_books(FakeSession(BOOKS_JSON), "цифровая экономика", limit=5))
check("только книга с автором", len(recs) == 1 and recs[0].kind == "book")
check("издательство = container", recs[0].container == "Экономика")
gost_line = format_gost(recs[0])
check("ГОСТ книга: автор в начале", gost_line.startswith("Иванов"), gost_line)

# ─────────────────────────────────────────────
print("6. Оркестратор: без сети не падает, добивки нет")


class DeadSession(FakeSession):
    def get(self, url, **kwargs):
        raise ConnectionError("offline")


recs = asyncio.run(find_real_sources(
    "тестовая тема про роботов", session=DeadSession(), verify=False, target=5))
check("офлайн → пустой список без исключений", recs == [])

print("\n" + "=" * 62)
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
print("ALL NEW SOURCES TESTS PASSED")
