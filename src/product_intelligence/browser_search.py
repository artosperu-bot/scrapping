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


def browser_search(query: str, *, timeout: int = 20, limit: int = 20):
    """Use the bundled Chromium as a real-browser fallback for search discovery.

    Playwright is imported lazily so core installs and unit tests do not require
    the desktop/browser profile unless this fallback is actually executed.
    """
    if not str(query or "").strip():
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
            page.goto(
                f"https://www.bing.com/search?q={quote_plus(query)}&count={max(10, limit)}",
                wait_until="domcontentloaded",
                timeout=max(5, timeout) * 1000,
            )
            raw = page.locator("li.b_algo").evaluate_all(
                """els => els.map(el => {
                  const a = el.querySelector('h2 a');
                  const p = el.querySelector('.b_caption p');
                  return {href: a?.href || '', text: a?.innerText || '', snippet: p?.innerText || ''};
                })"""
            )
            return _extract_result_rows(raw)[:limit]
        except Exception:
            return []
        finally:
            browser.close()
