from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    html: str
    method: str
    headers: dict[str, str] = field(default_factory=dict)
    json_responses: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    network_resources: list[dict[str, Any]] = field(default_factory=list)


def _looks_js_shell(html: str) -> bool:
    text = " ".join(html.lower().split())
    if len(text) < 700:
        return True
    hints = ["enable javascript", "javascript is required", "__next_data__", "id=\"__next\"", "data-reactroot"]
    return any(h in text for h in hints) and len(text) < 6000


def fetch_static(url: str, timeout: int = 30) -> FetchResult:
    r = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    return FetchResult(
        url=url,
        final_url=r.url,
        status_code=r.status_code,
        html=r.text or "",
        method="requests",
        headers={k.lower(): v for k, v in r.headers.items()},
    )


def fetch_browser(url: str, timeout: int = 45, capture_json: bool = True, activate_lazy_media: bool = False) -> FetchResult:
    """Render a public page with a normal Chromium browser.

    This is a compatibility fallback for JavaScript-rendered pages. It intentionally
    does not implement CAPTCHA solving, stealth plugins or access-control bypasses.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Playwright no esta instalado. Instala: pip install -e '.[browser]' y luego playwright install chromium"
        ) from e

    captured: list[dict[str, Any]] = []
    network_resources: list[dict[str, Any]] = []
    warnings: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA,
            locale="es-PE",
            viewport={"width": 1440, "height": 1200},
        )
        page = context.new_page()

        if capture_json:
            def on_response(response):
                try:
                    ctype = (response.headers.get("content-type") or "").lower()
                    if "json" not in ctype:
                        return
                    # Keep only reasonably-sized GET responses from the same site or APIs used by it.
                    if response.request.method != "GET":
                        return
                    body = response.body()
                    if not body or len(body) > 2_000_000:
                        return
                    obj = json.loads(body.decode("utf-8", errors="replace"))
                    captured.append({
                        "url": response.url,
                        "status": response.status,
                        "content_type": ctype,
                        "data": obj,
                    })
                except Exception:
                    return
            page.on("response", on_response)

        def on_request(request):
            try:
                rt = request.resource_type
                if rt in {"image", "media", "document", "xhr", "fetch"}:
                    network_resources.append({"url": request.url, "resource_type": rt, "method": request.method})
            except Exception:
                return
        page.on("request", on_request)

        resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout, 12) * 1000)
        except Exception:
            warnings.append("networkidle_timeout")
        if activate_lazy_media:
            try:
                page.evaluate("""async () => {
                    const step = Math.max(600, Math.floor(window.innerHeight * 0.8));
                    const maxY = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
                    for (let y = 0; y < maxY; y += step) {
                        window.scrollTo(0, y);
                        await new Promise(r => setTimeout(r, 90));
                    }
                    window.scrollTo(0, 0);
                }""")
                page.wait_for_timeout(500)
            except Exception:
                warnings.append("lazy_media_activation_failed")
        html = page.content()
        final_url = page.url
        status = resp.status if resp else 0
        headers = resp.headers if resp else {}
        browser.close()

    return FetchResult(
        url=url,
        final_url=final_url,
        status_code=status,
        html=html,
        method="playwright",
        headers={k.lower(): v for k, v in headers.items()},
        json_responses=captured,
        warnings=warnings,
        network_resources=network_resources,
    )


def fetch_page(url: str, timeout: int = 30, browser_fallback: bool = True, prefer_browser: bool = False, activate_lazy_media: bool = False) -> FetchResult:
    """Fast HTTP first, browser fallback only when it materially helps.

    401/403/429 are not treated as permission to circumvent site controls. We may
    retry through a normal browser because some public storefronts require JS/cookies;
    if the browser is also denied, the caller receives the denial and should move on.
    """
    static = fetch_static(url, timeout=timeout)
    needs_browser = prefer_browser or static.status_code in {401, 403, 429} or _looks_js_shell(static.html)
    if browser_fallback and needs_browser:
        try:
            browser = fetch_browser(url, timeout=max(timeout, 40), activate_lazy_media=activate_lazy_media)
            browser_is_useful = browser.status_code and browser.status_code < 400 and (prefer_browser or len(browser.html) >= len(static.html))
            if browser_is_useful:
                browser.warnings.insert(0, f"static_status={static.status_code}")
                return browser
            static.warnings.append(f"browser_fallback_status={browser.status_code}")
        except Exception as e:
            static.warnings.append(f"browser_fallback_failed:{type(e).__name__}")
    return static
