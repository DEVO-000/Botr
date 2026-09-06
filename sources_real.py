# -*- coding: utf-8 -*-
"""Настоящий список литературы: поиск, ПРОВЕРКА и оформление по ГОСТ.

ГЛАВНОЕ ПРАВИЛО: модуль НИКОГДА не выдумывает источники.
──────────────────────────────────────────────────────────────────────
Лучше вернуть 8 реальных источников, чем 20 с выдуманными. Преподаватель
проверяет список литературы первым делом, и несуществующий DOI — это
гарантированный провал работы.

Запрещено категорически:
  * возвращать зашитые в код списки DOI под любую тему;
  * отдавать страницы поисковой выдачи («Поисковая выдача по теме...») как
    библиографические записи;
  * подставлять заглушки вида «Материал с сайта по теме исследования»;
  * добивать список до минимума чем угодно.

Источники данных (все без API-ключей):
  * Crossref       — https://api.crossref.org
  * OpenAlex       — https://api.openalex.org
  * Semantic Scholar — https://api.semanticscholar.org
  * Google Scholar — https://scholar.google.com (HTML-выдача, публичного API нет)
  * КиберЛенинка   — https://cyberleninka.ru (главный источник русскоязычных
                     научных статей: поиск + метаданные citation_* со страниц)
  * arXiv          — https://export.arxiv.org (физика, математика, CS, биология)
  * DOAJ           — https://doaj.org (рецензируемые открытые журналы)
  * PubMed         — https://eutils.ncbi.nlm.nih.gov (медицина, биология)
  * DOI resolver   — https://doi.org (для проверки существования)
"""

from __future__ import annotations

import asyncio
import html as html_mod
import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field

log = logging.getLogger("sources_real")

USER_AGENT = "GOST-Assistant/3.0 (academic bibliography; mailto:noreply@example.org)"
DEFAULT_TIMEOUT = 15


# ──────────────────────────────────────────────────────────────────────
#  Модель записи
# ──────────────────────────────────────────────────────────────────────


@dataclass
class SourceRecord:
    """Одна библиографическая запись, полученная из реального каталога."""

    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    container: str = ""          # журнал / сборник / издательство
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    kind: str = "article"        # article | book | web
    origin: str = ""             # crossref | openalex | s2 | web
    verified: bool = False       # ПРОВЕРЕН ли адрес живым HTTP-запросом
    lang: str = ""

    @property
    def key(self) -> str:
        """Ключ для дедупликации."""
        if self.doi:
            return "doi:" + self.doi.lower()
        norm = re.sub(r"[^\w]+", "", (self.title or "").lower())[:80]
        return "ttl:" + norm if norm else "url:" + (self.url or "").lower()

    @property
    def best_url(self) -> str:
        if self.doi:
            return "https://doi.org/" + self.doi
        return self.url or ""

    def is_usable(self) -> bool:
        """Запись пригодна, если есть настоящее название и адрес."""
        if not self.title or len(self.title.strip()) < 8:
            return False
        if not self.best_url:
            return False
        return not _is_placeholder_title(self.title)


# Заглушки, которые раньше попадали в список литературы. Блокируем навсегда.
_PLACEHOLDER_TITLES = (
    "поисковая выдача",
    "материал с сайта",
    "электронный ресурс по теме",
    "результаты поиска",
    "search results",
    "just a moment",
    "доступ ограничен",
    "access denied",
    "page not found",
    "страница не найдена",
    "403 forbidden",
    "404",
    "attention required",
    "без названия",
    "untitled",
)


def _is_placeholder_title(title: str) -> bool:
    low = (title or "").strip().lower()
    if not low:
        return True
    return any(bad in low for bad in _PLACEHOLDER_TITLES)


# ──────────────────────────────────────────────────────────────────────
#  HTTP
# ──────────────────────────────────────────────────────────────────────


async def _get_json(session, url: str, timeout: int = DEFAULT_TIMEOUT):
    """GET → JSON. При 429 (rate limit) — один повтор с паузой.

    Каталоги (OpenAlex, Semantic Scholar) ограничивают частоту: при
    параллельном опросе несколькими запросами мы получали 429 и молча
    теряли целые каталоги. Повтор через паузу возвращает их в работу.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(2):
        try:
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status == 429 and attempt == 0:
                    await asyncio.sleep(2.0)
                    continue
                if resp.status != 200:
                    log.warning("catalog %s -> HTTP %s", url[:90], resp.status)
                    return None
                text = await resp.text()
            return json.loads(text)
        except asyncio.TimeoutError:
            log.warning("catalog timeout: %s", url[:90])
        except Exception as exc:
            log.warning("catalog error %s: %s", url[:90], exc)
        return None
    return None


async def _get_text(session, url: str, timeout: int = DEFAULT_TIMEOUT, limit: int = 200_000, headers=None):
    """GET → HTML-текст (ограниченный по размеру)."""
    try:
        if headers is None:
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru,en;q=0.8",
            }
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                return None, resp.status
            raw = await resp.content.read(limit)
        for enc in ("utf-8", "windows-1251"):
            try:
                return raw.decode(enc), 200
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "ignore"), 200
    except asyncio.TimeoutError:
        return None, 0
    except Exception as exc:
        log.debug("fetch failed %s: %s", url[:90], exc)
        return None, 0


# ──────────────────────────────────────────────────────────────────────
#  Проверка существования (то, чего раньше НЕ было вообще)
# ──────────────────────────────────────────────────────────────────────


async def verify_doi(session, doi: str, timeout: int = 10) -> bool:
    """Проверяет, что DOI реально регистрируется в системе DOI.

    Используется content negotiation к doi.org: если DOI не зарегистрирован,
    сервис ответит 404. Это отсекает галлюцинации модели.
    """
    doi = _clean_doi(doi)
    if not doi:
        return False
    url = "https://doi.org/api/handles/" + urllib.parse.quote(doi)
    data = await _get_json(session, url, timeout=timeout)
    if isinstance(data, dict) and data.get("responseCode") == 1:
        return True
    return False


async def verify_url(session, url: str, timeout: int = 10) -> bool:
    """Проверяет, что страница отвечает успешным кодом."""
    if not url or not url.startswith("http"):
        return False
    headers = {"User-Agent": USER_AGENT}
    for method in ("head", "get"):
        try:
            fn = getattr(session, method)
            async with fn(url, headers=headers, timeout=timeout,
                          allow_redirects=True) as resp:
                if resp.status < 400:
                    return True
                # Часть сайтов запрещает HEAD — пробуем GET.
                if method == "head" and resp.status in (403, 405, 501):
                    continue
                return False
        except asyncio.TimeoutError:
            if method == "get":
                return False
        except Exception:
            if method == "get":
                return False
    return False


async def verify_record(session, rec: SourceRecord, timeout: int = 10) -> bool:
    """Ставит rec.verified. Записи без проверки в список не попадают."""
    if rec.doi:
        rec.verified = await verify_doi(session, rec.doi, timeout=timeout)
        if rec.verified:
            return True
    if rec.url:
        rec.verified = await verify_url(session, rec.url, timeout=timeout)
    return rec.verified


def _clean_doi(doi: str) -> str:
    """Нормализует DOI: срезает префиксы и мусор."""
    if not doi:
        return ""
    d = str(doi).strip()
    d = re.sub(r"(?i)^https?://(dx\.)?doi\.org/", "", d)
    d = re.sub(r"(?i)^doi:\s*", "", d).strip().rstrip(".,;)")
    return d if re.match(r"^10\.\d{4,9}/\S+$", d) else ""


# ──────────────────────────────────────────────────────────────────────
#  Каталоги
# ──────────────────────────────────────────────────────────────────────


async def search_crossref(session, query: str, rows: int = 20) -> list[SourceRecord]:
    """Поиск в Crossref (каноническая база DOI)."""
    q = urllib.parse.quote(query)
    url = (
        "https://api.crossref.org/works"
        "?query.bibliographic=" + q +
        "&rows=" + str(int(rows)) +
        # ФИКС: поле `language` НЕ входит в допустимые select для /works —
        # из-за него Crossref отвечал HTTP 400 на КАЖДЫЙ запрос, и поиск
        # молча возвращал пусто (тесты на моках этого не ловили).
        "&select=DOI,title,author,issued,container-title,volume,issue,page,type"
        "&sort=relevance"
    )
    data = await _get_json(session, url)
    items = ((data or {}).get("message") or {}).get("items") or []
    out = []
    for it in items:
        titles = it.get("title") or []
        title = (titles[0] if titles else "").strip()
        if not title:
            continue
        authors = []
        for a in (it.get("author") or [])[:8]:
            fam, giv = (a.get("family") or "").strip(), (a.get("given") or "").strip()
            if fam:
                authors.append((fam + " " + giv).strip())
        year = ""
        parts = ((it.get("issued") or {}).get("date-parts") or [[]])[0]
        if parts and parts[0]:
            year = str(parts[0])
        containers = it.get("container-title") or []
        ctype = it.get("type") or ""
        out.append(SourceRecord(
            title=title,
            authors=authors,
            year=year,
            container=(containers[0] if containers else "").strip(),
            volume=str(it.get("volume") or ""),
            issue=str(it.get("issue") or ""),
            pages=str(it.get("page") or ""),
            doi=_clean_doi(it.get("DOI") or ""),
            kind="book" if "book" in ctype else "article",
            origin="crossref",
            lang=str(it.get("language") or ""),
        ))
    return out


async def search_openalex(session, query: str, per_page: int = 20) -> list[SourceRecord]:
    """Поиск в OpenAlex. Сортировка по цитируемости — сразу даёт веские работы."""
    q = urllib.parse.quote(query)
    url = (
        "https://api.openalex.org/works?search=" + q +
        "&per-page=" + str(int(per_page)) +
        "&sort=cited_by_count:desc"
    )
    data = await _get_json(session, url)
    out = []
    for it in (data or {}).get("results") or []:
        title = (it.get("display_name") or "").strip()
        if not title:
            continue
        authors = []
        for au in (it.get("authorships") or [])[:8]:
            name = ((au.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors.append(name)
        loc = (it.get("primary_location") or {}) or {}
        src = (loc.get("source") or {}) or {}
        biblio = it.get("biblio") or {}
        first, last = biblio.get("first_page") or "", biblio.get("last_page") or ""
        pages = (str(first) + "-" + str(last)) if first and last else str(first or "")
        out.append(SourceRecord(
            title=title,
            authors=authors,
            year=str(it.get("publication_year") or ""),
            container=(src.get("display_name") or "").strip(),
            volume=str(biblio.get("volume") or ""),
            issue=str(biblio.get("issue") or ""),
            pages=pages,
            doi=_clean_doi(it.get("doi") or ""),
            url=loc.get("landing_page_url") or "",
            kind="book" if (it.get("type") or "") == "book" else "article",
            origin="openalex",
            lang=str(it.get("language") or ""),
        ))
    return out


async def search_semantic_scholar(session, query: str, limit: int = 20) -> list[SourceRecord]:
    """Поиск в Semantic Scholar (без ключа — с ограничением частоты)."""
    q = urllib.parse.quote(query)
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search?query=" + q +
        "&limit=" + str(int(limit)) +
        "&fields=title,year,authors,journal,externalIds,url"
    )
    data = await _get_json(session, url)
    out = []
    for it in (data or {}).get("data") or []:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        ext = it.get("externalIds") or {}
        journal = (it.get("journal") or {}) or {}
        out.append(SourceRecord(
            title=title,
            authors=[a.get("name", "") for a in (it.get("authors") or [])[:8] if a.get("name")],
            year=str(it.get("year") or ""),
            container=str(journal.get("name") or ""),
            volume=str(journal.get("volume") or ""),
            pages=str(journal.get("pages") or ""),
            doi=_clean_doi(ext.get("DOI") or ""),
            url=it.get("url") or "",
            origin="s2",
        ))
    return out


async def search_google_books(session, query: str, limit: int = 10) -> list[SourceRecord]:
    """Поиск книг и монографий в Google Books (без ключа).

    Закрывает типовой пробел: каталоги статей дают одни статьи, а по ГОСТ
    в списке литературы нужны и книги. Возвращает ТОЛЬКО реальные издания
    с автором и годом; записи без автора в список не попадают.
    """
    q = urllib.parse.quote(query)
    url = (
        "https://www.googleapis.com/books/v1/volumes?q=" + q +
        "&maxResults=" + str(min(40, int(limit))) +
        "&printType=books&langRestrict=ru"
    )
    data = await _get_json(session, url)
    out: list[SourceRecord] = []
    for it in (data or {}).get("items") or []:
        info = it.get("volumeInfo") or {}
        title = (info.get("title") or "").strip()
        authors = [a.strip() for a in (info.get("authors") or [])[:4] if a.strip()]
        # Книга без автора — обычно сборник без метаданных: не рискуем.
        if not title or len(title) < 8 or not authors:
            continue
        year_m = re.search(r"(19|20)\d{2}", str(info.get("publishedDate") or ""))
        out.append(SourceRecord(
            title=title,
            authors=authors,
            year=year_m.group(0) if year_m else "",
            container=(info.get("publisher") or "").strip(),
            pages=str(info.get("pageCount") or ""),
            kind="book",
            origin="google_books",
            url=(info.get("canonicalVolumeLink") or info.get("infoLink") or "").strip(),
            lang=str(info.get("language") or ""),
        ))
    return out


# ──────────────────────────────────────────────────────────────────────
#  КиберЛенинка — главный источник РУССКОЯЗЫЧНЫХ научных статей.
#  Публичного API нет, поэтому: поиск → ссылки на статьи → метаданные
#  citation_* со страницы каждой статьи (авторы, журнал, год, DOI).
#  Страница скачана = источник существует (verified=True).
# ──────────────────────────────────────────────────────────────────────


def _parse_cyberleninka_search(html: str) -> list[str]:
    """Достаёт ссылки на статьи (/article/n/...) из HTML-выдачи поиска.

    Никаких выдуманных записей: если разметка изменилась или поиск
    недоступен — вернётся пустой список.
    """
    urls: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r'href=["\'](/article/[a-z]/[^"\'#?]+)["\'][^>]*>(.*?)</a>',
                         html or "", re.DOTALL | re.IGNORECASE):
        slug = m.group(1).strip()
        title = html_mod.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if slug in seen or len(title) < 12:
            continue
        seen.add(slug)
        urls.append("https://cyberleninka.ru" + slug)
    return urls


async def search_cyberleninka(session, query: str, limit: int = 10) -> list[SourceRecord]:
    """Поиск статей в КиберЛенинке (русскоязычные научные журналы).

    Возвращает записи с РЕАЛЬНЫМИ метаданными: авторы, журнал, год и DOI
    берутся из citation_* meta-тегов страницы статьи. Страница недоступна
    или без метаданных → статья не попадает в список (пустых заглушек нет).
    """
    q = urllib.parse.quote(query)
    search_url = "https://cyberleninka.ru/search?q=" + q
    html, status = await _get_text(session, search_url, timeout=DEFAULT_TIMEOUT)
    if not html or status != 200:
        log.info("cyberleninka: поиск недоступен (HTTP %s), пропускаем", status)
        return []
    if "g-recaptcha" in html or "Доступ ограничен" in html:
        log.info("cyberleninka: антиспам-защита, пропускаем")
        return []

    article_urls = _parse_cyberleninka_search(html)[: max(1, int(limit))]
    if not article_urls:
        log.info("cyberleninka: карточки статей не распознаны, пропускаем")
        return []

    # Тянем метаданные со страниц статей (параллельно, с ограничением).
    sem = asyncio.Semaphore(5)

    async def _fetch_one(u: str) -> SourceRecord | None:
        async with sem:
            try:
                html_page, st = await _get_text(session, u, timeout=DEFAULT_TIMEOUT)
            except Exception:
                return None
            if not html_page or st != 200:
                return None
            title = _clean_site_title(_meta(html_page, "citation_title", "og:title"))
            if not title or len(title) < 8 or _is_placeholder_title(title):
                return None
            authors: list[str] = []
            raw = _meta(html_page, "citation_author")
            if raw:
                for part in re.split(r"\s*[;,]\s*", raw):
                    part = part.strip()
                    if 3 <= len(part) <= 60:
                        authors.append(part)
            year = ""
            m_y = re.search(r"(19|20)\d{2}", _meta(html_page, "citation_publication_date") or "")
            if m_y:
                year = m_y.group(0)
            journal = _meta(html_page, "citation_journal_title")
            doi = _clean_doi(_meta(html_page, "citation_doi", "citation_doi_url", "dc.identifier"))
            return SourceRecord(
                title=title,
                authors=authors[:4],
                year=year,
                container=journal,
                doi=doi,
                url=u,
                kind="article",
                origin="cyberleninka",
                verified=True,  # страница успешно загружена
                lang="ru",
            )

    pages = await asyncio.gather(*[_fetch_one(u) for u in article_urls])
    recs = [r for r in pages if isinstance(r, SourceRecord)]
    if recs:
        log.info("cyberleninka: получено %s статей по запросу %r", len(recs), query[:60])
    return recs


# ──────────────────────────────────────────────────────────────────────
#  Международные открытые каталоги (без ключей)
# ──────────────────────────────────────────────────────────────────────


async def search_arxiv(session, query: str, limit: int = 10) -> list[SourceRecord]:
    """Поиск препринтов arXiv (физика, математика, CS, биология, статистика).

    Русскоязычные запросы не находятся — для них arXiv просто вернёт пусто,
    и оркестратор возьмёт источники из других каталогов.
    """
    q = urllib.parse.quote(query)
    url = (
        "http://export.arxiv.org/api/query?search_query=all:" + q +
        "&max_results=" + str(int(limit)) + "&sortBy=relevance"
    )
    xml, status = await _get_text(session, url, timeout=DEFAULT_TIMEOUT)
    if not xml or status != 200:
        return []
    out: list[SourceRecord] = []
    for entry in xml.split("<entry>")[1:]:
        title_m = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
        if not title_m:
            continue
        title = re.sub(r"\s+", " ", title_m.group(1)).strip()
        if len(title) < 8:
            continue
        authors = [
            re.sub(r"\s+", " ", n).strip()
            for n in re.findall(r"<name>(.*?)</name>", entry)
        ][:8]
        year_m = re.search(r"<published>(\d{4})", entry)
        id_m = re.search(r"<id>(http://arxiv.org/abs/[^<]+)</id>", entry)
        doi_m = re.search(r"<arxiv:doi[^>]*>(.*?)</arxiv:doi>", entry, re.DOTALL)
        if not id_m:
            continue
        out.append(SourceRecord(
            title=title,
            authors=[a for a in authors if a],
            year=year_m.group(1) if year_m else "",
            container="arXiv",
            doi=_clean_doi(doi_m.group(1)) if doi_m else "",
            url=id_m.group(1).strip(),
            kind="article",
            origin="arxiv",
            lang="en",
        ))
    return out


async def search_doaj(session, query: str, limit: int = 10) -> list[SourceRecord]:
    """Поиск статей в DOAJ (рецензируемые открытые журналы, без ключа)."""
    q = urllib.parse.quote(query)
    url = "https://doaj.org/api/search/articles/" + q + "?pageSize=" + str(int(limit))
    data = await _get_json(session, url)
    out: list[SourceRecord] = []
    for it in (data or {}).get("results") or []:
        bib = it.get("bibjson") or {}
        title = (bib.get("title") or "").strip()
        if not title:
            continue
        authors = [
            (a.get("name") or "").strip()
            for a in (bib.get("author") or [])[:8]
        ]
        authors = [a for a in authors if a]
        journal = ((bib.get("journal") or {}).get("title") or "").strip()
        doi = ""
        fulltext = ""
        for ident in bib.get("identifier") or []:
            if ident.get("type") == "doi" and not doi:
                doi = _clean_doi(ident.get("id") or "")
        for link in bib.get("link") or []:
            if link.get("type") == "fulltext" and link.get("url"):
                fulltext = link["url"]
                break
        year = str(bib.get("year") or "")
        vol = str(bib.get("volume") or "")
        pages = str(bib.get("start_page") or "")
        out.append(SourceRecord(
            title=title,
            authors=authors,
            year=year,
            container=journal,
            volume=vol,
            pages=pages,
            doi=doi,
            url=fulltext or ("https://doi.org/" + doi if doi else ""),
            kind="article",
            origin="doaj",
            lang="en",
        ))
    return out


async def search_pubmed(session, query: str, limit: int = 8) -> list[SourceRecord]:
    """Поиск в PubMed (медицина, биология, фармакология) через E-utilities."""
    q = urllib.parse.quote(query)
    esearch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        "?db=pubmed&term=" + q + "&retmax=" + str(int(limit)) + "&retmode=json"
    )
    found = await _get_json(session, esearch_url)
    ids = ((found or {}).get("esearchresult") or {}).get("idlist") or []
    if not ids:
        return []
    esum_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        "?db=pubmed&id=" + ",".join(ids) + "&retmode=json"
    )
    data = await _get_json(session, esum_url)
    result = (data or {}).get("result") or {}
    out: list[SourceRecord] = []
    for uid in ids:
        it = result.get(uid) or {}
        title = (it.get("title") or "").strip()
        if not title:
            continue
        authors = [
            (a.get("name") or "").strip()
            for a in (it.get("authors") or [])[:8]
        ]
        authors = [a for a in authors if a]
        doi = ""
        for art in it.get("articleids") or []:
            if art.get("idtype") == "doi" and art.get("value"):
                doi = _clean_doi(art["value"])
                break
        year_m = re.search(r"(19|20)\d{2}", it.get("pubdate") or "")
        out.append(SourceRecord(
            title=re.sub(r"\s+", " ", title),
            authors=authors,
            year=year_m.group(0) if year_m else "",
            container=(it.get("source") or "").strip(),
            doi=doi,
            url="https://pubmed.ncbi.nlm.nih.gov/" + uid + "/",
            kind="article",
            origin="pubmed",
            lang="en",
        ))
    return out


# ──────────────────────────────────────────────────────────────────────
#  Google Scholar (без API, парсинг HTML-выдачи)
#  Публичного API у Google Scholar нет, поэтому берём страницу результатов
#  и достаём карточки публикаций. Ссылка на сам scholar.google.com в
#  библиографию НЕ попадает — только на издателя/страницу работы.
# ──────────────────────────────────────────────────────────────────────

_GS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.9",
}


def _parse_google_scholar(html: str) -> list[dict]:
    """Достаёт карточки публикаций (.gs_ri) из HTML-выдачи Google Scholar.

    Возвращает список словарей для SourceRecord. Никакие данные не выдумываются:
    если карточку не удалось разобрать или в ней нет рабочей ссылки — она
    пропускается.
    """
    out: list[dict] = []
    for chunk in (html or "").split('<div class="gs_ri">')[1:]:
        block = chunk.split('<div class="gs_r')[0]
        link = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', block, re.DOTALL)
        if not link:
            continue
        url = html_mod.unescape(link.group(1)).strip()
        title = html_mod.unescape(re.sub(r"<[^>]+>", "", link.group(2)))
        title = re.sub(r"\s+", " ", title).strip()
        if not url.startswith("http") or not title or len(title) < 8:
            continue
        # scholar.google и google.com/url — служебные ссылки, не публикации.
        if "scholar.google" in url or "google.com/" in url:
            continue

        meta = ""
        m_meta = re.search(r'<div class="gs_a">(.*?)</div>', block, re.DOTALL)
        if m_meta:
            meta = html_mod.unescape(re.sub(r"<[^>]+>", "", m_meta.group(1)))
            meta = re.sub(r"\s+", " ", meta).strip()

        # Строка .gs_a обычно: «Иванов И. И., Петров П. — Журнал, 2021»
        # или «A. Smith, B. Johnson - Journal of X (2020)».
        authors: list[str] = []
        venue = ""
        year = ""
        if meta:
            # Разделитель авторов и издания — короткое/длинное тире или дефис
            # («Иванов С. П., Петрова А. — Вопросы экономики, 2021»).
            _meta_parts = re.split(r"\s*[-—–]\s*", meta, maxsplit=1)
            head = _meta_parts[0].strip()
            tail = _meta_parts[1] if len(_meta_parts) > 1 else ""
            years = re.findall(r"(?:19|20)\d{2}", meta)
            if years:
                year = years[-1]
            for name in head.split(","):
                name = name.strip()
                if name and 2 <= len(name) <= 70:
                    authors.append(name)
            venue = re.sub(r"(?:19|20)\d{2}.*$", "", tail).strip(", .")

        out.append({
            "title": title,
            "authors": authors[:8],
            "year": year,
            "container": venue,
            "doi": _clean_doi(url),
            "url": url,
            "kind": "article",
            "origin": "google_scholar",
            "verified": False,
            "lang": "",
        })
    return out


async def search_google_scholar(session, query: str, limit: int = 20) -> list[SourceRecord]:
    """Поиск в Google Scholar (HTML-выдача, без API-ключа).

    Google Scholar не предоставляет публичного API, поэтому разбирается страница
    результатов. Антибот-защита, капча или смена разметки НЕ ломают модуль:
    функция просто вернёт пустой список (или меньше записей), и список литературы
    не будет добит выдумками.

    Каждая карточка дальше проходит те же фильтры, что и каталоги: relevance()
    и verify_record(). В итоговый список попадают только реально существующие
    публикации, адрес которых отвечает на живой HTTP-запрос.
    """
    q = urllib.parse.quote(query)
    url = (
        "https://scholar.google.com/scholar?q=" + q +
        "&num=" + str(max(1, min(int(limit), 20))) + "&hl=ru"
    )
    html, status = await _get_text(session, url, timeout=DEFAULT_TIMEOUT, headers=_GS_HEADERS)
    if not html or status != 200:
        log.info("google scholar: страница недоступна (HTTP %s), пропускаем", status)
        return []
    if 'class="gs_r"' not in html and 'class="gs_ri"' not in html:
        log.info("google scholar: нет карточек публикаций (капча или блокировка), пропускаем")
        return []

    recs: list[SourceRecord] = []
    for item in _parse_google_scholar(html):
        if len(recs) >= limit:
            break
        rec = SourceRecord(**item)
        if rec.is_usable() and "scholar.google" not in (rec.url or ""):
            recs.append(rec)
    if recs:
        log.info("google scholar: распознано %s публикаций по запросу %r",
                 len(recs), query[:60])
    return recs


# ──────────────────────────────────────────────────────────────────────
#  Реальные метаданные веб-страницы
#  Замена заглушки «Материал с сайта по теме исследования».
# ──────────────────────────────────────────────────────────────────────

_META_RE_CACHE: dict[str, re.Pattern] = {}


def _meta(html: str, *names: str) -> str:
    """Извлекает content из <meta name=...> / <meta property=...>."""
    for name in names:
        key = name.lower()
        rx = _META_RE_CACHE.get(key)
        if rx is None:
            esc = re.escape(name)
            rx = re.compile(
                r"<meta[^>]+(?:name|property|itemprop)\s*=\s*[\"']" + esc +
                r"[\"'][^>]*content\s*=\s*[\"'](.*?)[\"']"
                r"|<meta[^>]+content\s*=\s*[\"'](.*?)[\"'][^>]*"
                r"(?:name|property|itemprop)\s*=\s*[\"']" + esc + r"[\"']",
                re.IGNORECASE | re.DOTALL,
            )
            _META_RE_CACHE[key] = rx
        m = rx.search(html or "")
        if m:
            val = (m.group(1) or m.group(2) or "").strip()
            if val:
                return html_mod.unescape(re.sub(r"\s+", " ", val))
    return ""


def _page_title(html: str) -> str:
    """Настоящий заголовок страницы: og:title → citation_title → <title> → <h1>."""
    for cand in (
        _meta(html, "citation_title", "og:title", "twitter:title", "dc.title", "DC.Title"),
    ):
        if cand:
            return cand
    m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.IGNORECASE | re.DOTALL)
    if m:
        return html_mod.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html or "", re.IGNORECASE | re.DOTALL)
    if m:
        return html_mod.unescape(re.sub(r"<[^>]+>|\s+", " ", m.group(1))).strip()
    return ""


def _clean_site_title(title: str) -> str:
    """Срезает хвост вида «— Название сайта» из заголовка."""
    t = (title or "").strip()
    for sep in (" | ", " \u2014 ", " \u2013 ", " :: ", " \u00b7 "):
        if sep in t and len(t.split(sep)[0]) >= 25:
            t = t.split(sep)[0].strip()
            break
    return t.strip(" .\u2014-–")


async def extract_web_metadata(session, url: str, timeout: int = DEFAULT_TIMEOUT):
    """Скачивает страницу и собирает РЕАЛЬНЫЕ библиографические данные.

    Возвращает None, если страница недоступна или заголовка нет.
    Заглушки НЕ генерируются ни при каких условиях.
    """
    html, status = await _get_text(session, url, timeout=timeout)
    if not html or status != 200:
        log.info("web source unavailable (HTTP %s): %s", status, url[:90])
        return None

    title = _clean_site_title(_page_title(html))
    if not title or len(title) < 8 or _is_placeholder_title(title):
        log.info("web source has no real title: %s", url[:90])
        return None

    authors = []
    for raw in (
        _meta(html, "citation_author", "author", "article:author", "dc.creator", "DC.Creator"),
    ):
        if raw:
            for part in re.split(r"\s*[;,]\s*|\s+\u0438\s+", raw):
                part = part.strip()
                if 3 <= len(part) <= 60 and not part.lower().startswith("http"):
                    authors.append(part)
            break

    date_raw = _meta(
        html, "citation_publication_date", "article:published_time",
        "datePublished", "dc.date", "DC.Date", "pubdate",
    )
    year = ""
    m = re.search(r"(19|20)\d{2}", date_raw or "")
    if m:
        year = m.group(0)

    site = _meta(html, "og:site_name", "citation_journal_title", "application-name")
    if not site:
        site = urllib.parse.urlparse(url).netloc.replace("www.", "")

    return SourceRecord(
        title=title,
        authors=authors[:4],
        year=year,
        container=site,
        doi=_clean_doi(_meta(html, "citation_doi", "dc.identifier")),
        url=url,
        kind="web",
        origin="web",
        verified=True,  # страница только что была успешно загружена
    )


# ──────────────────────────────────────────────────────────────────────
#  Оформление по ГОСТ Р 7.0.5–2008
# ──────────────────────────────────────────────────────────────────────


def _initials(name: str) -> str:
    """«Иванов Сергей Петрович» → «Иванов С. П.»; «John Smith» → «Smith J.»"""
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not name:
        return ""
    parts = name.split(" ")
    if len(parts) == 1:
        return parts[0]
    # Латиница в порядке «Имя Фамилия» → переворачиваем.
    if re.match(r"^[A-Za-z.\-']+$", parts[0]) and len(parts) == 2 \
            and not parts[1].endswith("."):
        first, last = parts[0], parts[1]
        return last + " " + first[0].upper() + "."
    surname, rest = parts[0], parts[1:]
    ini = " ".join(p[0].upper() + "." for p in rest if p and p[0].isalpha())
    return (surname + " " + ini).strip()


def _initials_first(name: str) -> str:
    """Форма для сведений после косой черты: «С. П. Иванов».

    По ГОСТ Р 7.0.5 в заголовке записи фамилия идёт первой, а в сведениях
    об ответственности (после «/») — инициалы перед фамилией.
    """
    compact = _initials(name)
    if not compact:
        return ""
    m = re.match(r"^(\S+)\s+((?:[А-ЯЁA-Z]\.\s*)+)$", compact)
    if m:
        return m.group(2).strip() + " " + m.group(1)
    return compact


def _authors_gost(authors: list[str]) -> tuple[str, str]:
    """Возвращает (заголовок до названия, сведения после косой черты).

    По ГОСТ: 1 автор — выносится в начало; 2–3 — все после «/»;
    4 и больше — первый и «[и др.]».
    """
    clean = [_initials(a) for a in (authors or []) if a and a.strip()]
    clean = [a for a in clean if len(a) >= 3]
    if not clean:
        return "", ""
    flipped = [_initials_first(a) for a in (authors or []) if a and a.strip()]
    flipped = [a for a in flipped if len(a) >= 3]
    if len(clean) == 1:
        return clean[0], flipped[0]
    if len(clean) <= 3:
        return clean[0], ", ".join(flipped)
    return clean[0], flipped[0] + " [и др.]"


def format_gost(rec: SourceRecord) -> str:
    """Строит библиографическую запись по ГОСТ Р 7.0.5–2008.

    Никакие поля не выдумываются: чего нет в записи — того нет и в строке.
    """
    head, tail = _authors_gost(rec.authors)
    title = (rec.title or "").strip().rstrip(".")
    out = ""

    if head and rec.kind != "web":
        out += head + " "
    out += title

    if rec.kind == "web":
        out += " [Электронный ресурс]"

    if tail:
        out += " / " + tail

    if rec.kind == "article" and rec.container:
        out += ". \u2014 " + rec.container.strip().rstrip(".")
        if rec.year:
            out += ". \u2014 " + rec.year
        if rec.volume:
            out += ". \u2014 Т. " + rec.volume
        if rec.issue:
            out += ", \u2116 " + rec.issue
        if rec.pages:
            out += ". \u2014 С. " + rec.pages.replace("-", "\u2013")
    elif rec.kind == "book":
        if rec.container:
            out += ". \u2014 " + rec.container.strip().rstrip(".")
        if rec.year:
            out += ", " + rec.year
    else:  # web
        if rec.container:
            out += " // " + rec.container.strip().rstrip(".")
        if rec.year:
            out += ". \u2014 " + rec.year

    url = rec.best_url
    if url:
        out += ". \u2014 URL: " + url
    out = re.sub(r"\s{2,}", " ", out).strip()
    if not out.endswith("."):
        out += "."
    # Сокращённые имена уже оканчиваются точкой — убираем удвоение.
    out = re.sub(r"\.{2,}", ".", out)
    out = re.sub(r"\.\s*\.", ".", out)
    return out


# ──────────────────────────────────────────────────────────────────────
#  Релевантность
# ──────────────────────────────────────────────────────────────────────

_STOP = {
    "и", "в", "на", "с", "по", "для", "как", "из", "о", "об", "к", "от", "при", "за", "их",
    "the", "a", "an", "of", "and", "in", "on", "for", "to", "is", "are", "with", "by",
    "анализ", "исследование", "изучение", "роль", "влияние", "особенности",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[\w\u0430-\u044f\u0451]{4,}", (text or "").lower())
    return {w[:6] for w in words if w not in _STOP}


_MEDICAL_WORDS = (
    "медиц", "заболеван", "болезн", "пациент", "клин", "терап", "диагност",
    "лечен", "хирург", "фармак", "эпидеми", "вирус", "инфекц", "онколог",
    "кардиолог", "невролог", "педиатр", "здоров", "питани", "медсестр",
    "health", "disease", "clinical", "patient", "cancer", "therapy",
    "diagnosis", "treatment", "virus", "infect", "medicine",
)


def _looks_medical(text: str) -> bool:
    """Грубая эвристика: тема относится к медицине/биологии."""
    low = (text or "").lower()
    return any(w in low for w in _MEDICAL_WORDS)


def relevance(rec: SourceRecord, topic_tokens: set[str]) -> float:
    """Доля совпадения основ слов темы с названием источника."""
    if not topic_tokens:
        return 0.0
    hay = _tokens(rec.title + " " + rec.container)
    if not hay:
        return 0.0
    
    # Требуем совпадения хотя бы 1 ключевого токена из темы
    match_count = len(topic_tokens & hay)
    if match_count == 0:
        return 0.0
    
    return match_count / len(topic_tokens)


def _query_variants(topic: str, keywords: str = "") -> list[str]:
    """Разные формулировки запроса, чтобы расширить охват."""
    topic = re.sub(r"\s+", " ", (topic or "").strip())
    out = [topic]
    if keywords:
        out.append(keywords.strip())
    words = [w for w in re.findall(r"[\w\u0430-\u044f\u0451]{4,}", topic.lower())
             if w not in _STOP]
    if len(words) > 3:
        out.append(" ".join(words[:4]))
    seen, uniq = set(), []
    for q in out:
        if q and q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq[:4]


# ──────────────────────────────────────────────────────────────────────
#  Оркестрация
# ──────────────────────────────────────────────────────────────────────


async def find_real_sources(
    topic: str,
    *,
    keywords: str = "",
    target: int = 20,
    min_relevance: float = 0.12,
    verify: bool = True,
    extra_urls: list[str] | None = None,
    session=None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[SourceRecord]:
    """Ищет реальные источники по теме и возвращает только ПРОВЕРЕННЫЕ.

    Если нашлось меньше target — возвращает меньше. Добивки НЕТ.
    """
    own_session = False
    if session is None:
        import aiohttp
        session = aiohttp.ClientSession()
        own_session = True

    try:
        queries = _query_variants(topic, keywords)

        # Семафор каталогов: не бомбим API всем списком одновременно —
        # из-за параллельного опроса OpenAlex/Semantic Scholar отдавали 429
        # и каталоги молча выпадали из поиска.
        cat_sem = asyncio.Semaphore(6)

        async def _polite(coro):
            async with cat_sem:
                return await coro

        tasks = []
        for q in queries:
            tasks.append(_polite(search_crossref(session, q, rows=15)))
            tasks.append(_polite(search_openalex(session, q, per_page=15)))
        tasks.append(_polite(search_semantic_scholar(session, queries[0], limit=15)))
        # Google Scholar — дополнительный источник, особенно полезен для
        # русскоязычных статей и книг, которых нет в англоязычных каталогах.
        for q in queries[:2]:
            tasks.append(_polite(search_google_scholar(session, q, limit=10)))
        # КиберЛенинка — русскоязычные статьи; при недоступности/антиспаме
        # возвращает пустой список и не мешает остальным источникам.
        for q in queries[:2]:
            tasks.append(_polite(search_cyberleninka(session, q, limit=10)))
        # Международные открытые каталоги: DOAJ и arXiv — по одному запросу
        # (первая формулировка темы), PubMed — для медико-биологических тем.
        tasks.append(_polite(search_doaj(session, queries[0], limit=10)))
        tasks.append(_polite(search_arxiv(session, queries[0], limit=10)))
        if _looks_medical(topic + " " + keywords):
            tasks.append(_polite(search_pubmed(session, queries[0], limit=8)))
        # Книги и монографии — отдельная важная часть ГОСТ-списка
        # (каталоги статей книг не дают, а в списке литературы они нужны).
        tasks.append(_polite(search_google_books(session, queries[0], limit=10)))
        if len(queries) > 1:
            tasks.append(_polite(search_google_books(session, queries[1], limit=8)))
        for u in (extra_urls or [])[:12]:
            tasks.append(extract_web_metadata(session, u, timeout=timeout))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        pool: dict[str, SourceRecord] = {}
        for res in results:
            if isinstance(res, Exception) or res is None:
                continue
            batch = res if isinstance(res, list) else [res]
            for rec in batch:
                if not isinstance(rec, SourceRecord) or not rec.is_usable():
                    continue
                pool.setdefault(rec.key, rec)

        topic_tokens = _tokens(topic + " " + keywords)
        scored = []
        for rec in pool.values():
            score = relevance(rec, topic_tokens)
            if rec.origin == "web":
                score += 0.10  # страница пришла из адресов, найденных по теме
            if score >= min_relevance:
                scored.append((score, rec))
        scored.sort(key=lambda p: (-p[0], -len(p[1].authors), p[1].title))

        candidates = [rec for _, rec in scored[: target * 3]]

        if not verify:
            return candidates[:target]

        # Проверяем существование параллельно, но с ограничением нагрузки.
        sem = asyncio.Semaphore(8)

        async def _check(rec: SourceRecord):
            if rec.verified:
                return rec
            async with sem:
                ok = await verify_record(session, rec, timeout=min(timeout, 10))
            return rec if ok else None

        checked = await asyncio.gather(
            *[_check(r) for r in candidates], return_exceptions=True
        )
        good = [r for r in checked if isinstance(r, SourceRecord) and r.verified]

        if len(good) < target:
            log.warning(
                "Найдено только %s проверенных источников из %s запрошенных по теме %r. "
                "Список НЕ добивается выдуманными записями.",
                len(good), target, topic[:60],
            )
        return good[:target]
    finally:
        if own_session:
            await session.close()


async def build_bibliography(
    topic: str,
    *,
    keywords: str = "",
    target: int = 20,
    extra_urls: list[str] | None = None,
    session=None,
) -> list[str]:
    """Главная точка входа: список готовых строк по ГОСТ.

    Сортировка алфавитная: сначала кириллица, затем латиница — как требует ГОСТ.
    """
    recs = await find_real_sources(
        topic, keywords=keywords, target=target,
        extra_urls=extra_urls, session=session,
    )
    lines = [format_gost(r) for r in recs]

    def _sort_key(s: str):
        first = (s or " ")[0]
        return (0 if "\u0430" <= first.lower() <= "\u044f" else 1, s.lower())

    return sorted(lines, key=_sort_key)


def build_bibliography_sync(topic: str, **kwargs) -> list[str]:
    """Синхронная обёртка для вызова из неасинхронного кода."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(build_bibliography(topic, **kwargs))
    raise RuntimeError(
        "build_bibliography_sync нельзя вызывать внутри работающего event loop — "
        "используйте await build_bibliography(...)"
    )


__all__ = [
    "SourceRecord",
    "search_crossref",
    "search_openalex",
    "search_semantic_scholar",
    "search_google_scholar",
    "search_cyberleninka",
    "search_google_books",
    "search_arxiv",
    "search_doaj",
    "search_pubmed",
    "extract_web_metadata",
    "verify_doi",
    "verify_url",
    "verify_record",
    "format_gost",
    "relevance",
    "find_real_sources",
    "build_bibliography",
    "build_bibliography_sync",
]
