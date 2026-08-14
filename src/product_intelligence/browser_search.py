from __future__ import annotations

from urllib.parse import quote_plus, urlparse

SEARCH_HOSTS = {
    "bing.com", "www.bing.com", "duckduckgo.com", "html.duckduckgo.com",
    "brave.com", "search.brave.com", "mojeek.com", "www.mojeek.com",
    "yahoo.com", "search.yahoo.com",
}


def _is_search_host(host: str) -> bool:
    host = (host or "").lower()
    return any(host == known or host.endswith("." + known) for known in SEARCH_HOSTS)


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


def browser_search(query: str, *, timeout: int = 20, limit: int = 20):
    """Use bundled Chromium as a real-browser fallback for search discovery."""
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

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/151 Safari/537.36"
            ))
            combined = []
            seen = set()
            for search_url, selector, script in engines:
                try:
                    page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=max(5, timeout) * 1000,
                    )
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


def browser_pdf_links(url: str, *, timeout: int = 20, limit: int = 30) -> list[tuple[str, str]]:
    """Render a product/support landing and collect concrete PDF download URLs.

    This is discovery only: page text is never returned as product evidence.
    It exists for sites where document links are injected by JavaScript after
    the static HTML response has loaded.
    """
    if not str(url or "").startswith("http"):
        return []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/151 Safari/537.36"
            ))
            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=max(5, timeout) * 1000,
                )
                page.wait_for_timeout(1200)
            except Exception:
                return []

            raw = page.locator("a[href], [data-url], [data-href], [data-file], [data-download-url]").evaluate_all(
                """els => els.map(el => ({
                  href: el.href || el.dataset?.url || el.dataset?.href || el.dataset?.file || el.dataset?.downloadUrl || '',
                  text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim()
                }))"""
            )
            found: list[tuple[str, str]] = []
            seen = set()
            for row in raw:
                href = str(row.get("href") or "").strip()
                if not href.startswith("http") or href in seen:
                    continue
                path_and_query = href.lower()
                if ".pdf" not in path_and_query:
                    continue
                seen.add(href)
                found.append((href, str(row.get("text") or "").strip()))
                if len(found) >= limit:
                    break
            return found
        finally:
            browser.close()
