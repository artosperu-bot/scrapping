from __future__ import annotations

import html
import re
from urllib.parse import quote, quote_plus, unquote, urljoin, urlparse

SEARCH_HOSTS = {
    "bing.com", "www.bing.com", "duckduckgo.com", "html.duckduckgo.com",
    "brave.com", "search.brave.com", "mojeek.com", "www.mojeek.com",
    "yahoo.com", "search.yahoo.com",
}
_TRACKING_HOSTS = {
    "facebook.com", "facebook.net", "connect.facebook.net", "google-analytics.com",
    "googletagmanager.com", "doubleclick.net",
}
_DOCUMENT_PATH_HINTS = (
    "manual", "guide", "quick", "spec", "datasheet", "data-sheet", "document",
    "download", "instruction", "support", "technical", "ficha", "qsg",
)
_GENERIC_PDF_STEMS = {"generated", "file", "this", "i"}


def _is_search_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == known or host.endswith("." + known) for known in SEARCH_HOSTS)


def _is_tracking_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == known or host.endswith("." + known) for known in _TRACKING_HOSTS)


def _extract_result_rows(raw_rows):
    out = []
    seen = set()
    for row in raw_rows:
        url = str(row.get("href") or "").strip()
        if not url.startswith("http") or url in seen:
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host or _is_search_host(host):
            continue
        seen.add(url)
        out.append((url, str(row.get("text") or ""), str(row.get("snippet") or "")))
    return out


def _page_rows(page, selector: str, script: str):
    try:
        return page.locator(selector).evaluate_all(script)
    except Exception:
        return []


def _pdf_link_rows(page):
    try:
        return page.locator(
            "a[href], button, [data-url], [data-href], [data-file], [data-download-url], [onclick]"
        ).evaluate_all(
            """els => els.map(el => ({
              href: el.href || el.dataset?.url || el.dataset?.href || el.dataset?.file || el.dataset?.downloadUrl || '',
              text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim(),
              outer: el.outerHTML || ''
            }))"""
        )
    except Exception:
        return []


def _normalize_embedded_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    return (
        text.replace("\\u002F", "/")
        .replace("\\u002f", "/")
        .replace("\\x2F", "/")
        .replace("\\x2f", "/")
        .replace("\\/", "/")
    )


def _document_like_pdf_url(absolute: str) -> bool:
    parsed = urlparse(absolute)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if _is_tracking_host(host):
        return False
    decoded_path = unquote(parsed.path or "")
    if "\\" in decoded_path or any(ch in decoded_path for ch in ("*", "{", "}")):
        return False
    filename = decoded_path.rsplit("/", 1)[-1].strip()
    if not filename.lower().endswith(".pdf"):
        return False
    stem = filename[:-4].strip().lower()
    if not stem:
        return False
    semantic = " ".join(part.lower() for part in decoded_path.split("/") if part)
    has_document_hint = any(hint in semantic for hint in _DOCUMENT_PATH_HINTS)
    if stem in _GENERIC_PDF_STEMS and not has_document_hint:
        return False
    return True


def _absolute_pdf_url(raw: str, base_url: str) -> str | None:
    value = _normalize_embedded_text(raw).strip().strip('"\'()[]{};,')
    if ".pdf" not in value.lower():
        return None
    if value.startswith("//"):
        value = "https:" + value
    absolute = urljoin(base_url, value)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or ".pdf" not in parsed.path.lower():
        return None
    if not _document_like_pdf_url(absolute):
        return None
    return quote(absolute, safe=":/?&=%#@+;,~")


def extract_pdf_urls_from_text(text: str, base_url: str) -> list[tuple[str, str]]:
    normalized = _normalize_embedded_text(text)
    candidates: list[str] = []
    candidates.extend(match.group(1) for match in re.finditer(r'["\']([^"\']*?\.pdf(?:\?[^"\']*)?)["\']', normalized, re.I))
    candidates.extend(
        match.group(0)
        for match in re.finditer(r'(?:https?:)?//[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?|/[^\s"\'<>]+?\.pdf(?:\?[^\s"\'<>]*)?', normalized, re.I)
    )
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in candidates:
        url = _absolute_pdf_url(raw, base_url)
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append((url, ""))
    return rows


def _launch_chromium(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except Exception:
        return None


def browser_search(query: str, *, timeout: int = 20, limit: int = 20):
    if not str(query or "").strip():
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    encoded = quote_plus(str(query).strip())
    engines = [
        (
            f"https://www.bing.com/search?q={encoded}&count={max(10, limit)}",
            "li.b_algo",
            """els => els.map(el => { const a=el.querySelector('h2 a'); const p=el.querySelector('.b_caption p'); return {href:a?.href||'', text:a?.innerText||'', snippet:p?.innerText||''}; })""",
        ),
        (
            f"https://html.duckduckgo.com/html/?q={encoded}",
            ".result",
            """els => els.map(el => { const a=el.querySelector('a.result__a'); const p=el.querySelector('.result__snippet'); return {href:a?.href||'', text:a?.innerText||'', snippet:p?.innerText||''}; })""",
        ),
        (
            f"https://search.brave.com/search?q={encoded}",
            "div.snippet, div[data-type='web']",
            """els => els.map(el => { const a=el.querySelector('a[href]'); const p=el.querySelector('.snippet-description, .description'); return {href:a?.href||'', text:a?.innerText||'', snippet:p?.innerText||el.innerText||''}; })""",
        ),
    ]

    try:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            if browser is None:
                return []
            try:
                page = browser.new_page(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
                ))
                combined = []
                seen = set()
                for search_url, selector, script in engines:
                    try:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=max(5, timeout) * 1000)
                    except Exception:
                        continue
                    raw = _page_rows(page, selector, script)
                    rows = _extract_result_rows(raw)
                    for row in rows:
                        if row[0] in seen:
                            continue
                        seen.add(row[0])
                        combined.append(row)
                        if len(combined) >= limit:
                            return combined[:limit]
                return combined[:limit]
            finally:
                browser.close()
    except Exception:
        return []


def browser_pdf_links(url: str, *, timeout: int = 20, limit: int = 30) -> list[tuple[str, str]]:
    if not str(url or "").startswith("http"):
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    try:
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            if browser is None:
                return []
            try:
                page = browser.new_page(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151 Safari/537.36"
                ))
                responses = []
                page.on("response", lambda response: responses.append(response))
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=max(5, timeout) * 1000)
                    page.wait_for_timeout(1400)
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                except Exception:
                    return []

                found: list[tuple[str, str]] = []
                seen: set[str] = set()

                def add(raw_url: str, label: str = ""):
                    resolved = _absolute_pdf_url(raw_url, url)
                    if not resolved or resolved in seen or len(found) >= limit:
                        return
                    seen.add(resolved)
                    found.append((resolved, str(label or "").strip()))

                for row in _pdf_link_rows(page):
                    add(str(row.get("href") or ""), str(row.get("text") or ""))
                    for embedded, _ in extract_pdf_urls_from_text(str(row.get("outer") or ""), url):
                        add(embedded, str(row.get("text") or ""))

                try:
                    page_html = page.content()
                except Exception:
                    page_html = ""
                for embedded, label in extract_pdf_urls_from_text(page_html, url):
                    add(embedded, label)

                for response in responses[:120]:
                    if len(found) >= limit:
                        break
                    response_url = str(getattr(response, "url", "") or "")
                    add(response_url)
                    try:
                        headers = response.headers
                        content_type = str(headers.get("content-type") or "").lower()
                    except Exception:
                        content_type = ""
                    if not any(token in content_type for token in ("json", "javascript", "text", "html")):
                        continue
                    try:
                        body = response.text()
                    except Exception:
                        continue
                    for embedded, label in extract_pdf_urls_from_text(body, response_url or url):
                        add(embedded, label)

                return found[:limit]
            finally:
                browser.close()
    except Exception:
        return []
