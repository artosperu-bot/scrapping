from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]
TRACE = ROOT / "src/product_intelligence/price_trace.py"
WORKFLOW = ROOT / "src/product_intelligence/price_workflow.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one patch target, got {count}")
    return text.replace(old, new, 1)


trace = TRACE.read_text(encoding="utf-8")
if '"FETCH_NOT_FOUND": "ACCESS"' not in trace:
    trace = replace_once(
        trace,
        '    "FETCH_BLOCKED": "ACCESS",\n    "FETCH_TIMEOUT": "ACCESS",\n',
        '    "FETCH_BLOCKED": "ACCESS",\n    "FETCH_NOT_FOUND": "ACCESS",\n    "FETCH_TIMEOUT": "ACCESS",\n',
        "trace-status-map",
    )
    trace = trace.replace(
        '"FETCH_OK", "FETCH_BLOCKED", "FETCH_TIMEOUT", "PARSER_STARTED"',
        '"FETCH_OK", "FETCH_BLOCKED", "FETCH_NOT_FOUND", "FETCH_TIMEOUT", "PARSER_STARTED"',
    )
    trace = trace.replace(
        '"FETCH_STARTED", "FETCH_OK", "FETCH_BLOCKED", "FETCH_TIMEOUT", "PARSER_STARTED"',
        '"FETCH_STARTED", "FETCH_OK", "FETCH_BLOCKED", "FETCH_NOT_FOUND", "FETCH_TIMEOUT", "PARSER_STARTED"',
    )
TRACE.write_text(trace, encoding="utf-8")

workflow = WORKFLOW.read_text(encoding="utf-8")
if "class _PriceFetchStatusError" not in workflow:
    anchor = 'BROWSER_PRICE_CHANNELS = {"Ripley", "MercadoLibre", "Mercado Libre", "JBL Perú"}\n\n\n'
    helper = '''BROWSER_PRICE_CHANNELS = {"Ripley", "MercadoLibre", "Mercado Libre", "JBL Perú"}\n\n\nclass _PriceFetchStatusError(RuntimeError):\n    def __init__(self, status_code: int):\n        self.status_code = int(status_code)\n        self.trace_status = "FETCH_NOT_FOUND" if self.status_code in {404, 410} else "FETCH_BLOCKED"\n        super().__init__(f"HTTP {self.status_code}")\n\n\ndef _ensure_usable_price_fetch(result) -> None:\n    raw = getattr(result, "status_code", None)\n    if raw is None:\n        return\n    try:\n        status = int(raw)\n    except (TypeError, ValueError):\n        return\n    if status >= 400:\n        raise _PriceFetchStatusError(status)\n\n\n'''
    workflow = replace_once(workflow, anchor, helper, "fetch-status-helper")

if "_ensure_usable_price_fetch(fetched)" not in workflow:
    workflow = replace_once(
        workflow,
        '    fetched = fetch_page(url, timeout=25, browser_fallback=True, activate_lazy_media=False)\n    final_url = str(getattr(fetched, "final_url", None) or url)\n',
        '    fetched = fetch_page(url, timeout=25, browser_fallback=True, activate_lazy_media=False)\n    _ensure_usable_price_fetch(fetched)\n    final_url = str(getattr(fetched, "final_url", None) or url)\n',
        "primary-fetch-check",
    )
    workflow = replace_once(
        workflow,
        '            rendered = fetch_page(url, timeout=35, browser_fallback=True, prefer_browser=True, activate_lazy_media=False)\n            rendered_url = str(getattr(rendered, "final_url", None) or final_url)\n',
        '            rendered = fetch_page(url, timeout=35, browser_fallback=True, prefer_browser=True, activate_lazy_media=False)\n            _ensure_usable_price_fetch(rendered)\n            rendered_url = str(getattr(rendered, "final_url", None) or final_url)\n',
        "rendered-fetch-check",
    )
    workflow = replace_once(
        workflow,
        '        fetched = fetch_page(url, timeout=8, browser_fallback=False, activate_lazy_media=False)\n        final_url = str(getattr(fetched, "final_url", None) or url)\n',
        '        fetched = fetch_page(url, timeout=8, browser_fallback=False, activate_lazy_media=False)\n        _ensure_usable_price_fetch(fetched)\n        final_url = str(getattr(fetched, "final_url", None) or url)\n',
        "learned-fetch-check",
    )

old_catch = '''            if trace:\n                if isinstance(exc, (requests.Timeout, TimeoutError)):\n                    trace.record(channel, "FETCH_TIMEOUT", url=url, detail=type(exc).__name__)\n                else:\n                    trace.record(channel, "FETCH_BLOCKED", url=url, detail=type(exc).__name__)\n'''
new_catch = '''            if trace:\n                trace_status = getattr(exc, "trace_status", None)\n                if trace_status:\n                    trace.record(channel, trace_status, url=url, detail=f"HTTP_{getattr(exc, 'status_code', 0)}")\n                elif isinstance(exc, (requests.Timeout, TimeoutError)):\n                    trace.record(channel, "FETCH_TIMEOUT", url=url, detail=type(exc).__name__)\n                else:\n                    trace.record(channel, "FETCH_BLOCKED", url=url, detail=type(exc).__name__)\n'''
if old_catch in workflow:
    workflow = replace_once(workflow, old_catch, new_catch, "collect-trace-catch")
elif "trace_status = getattr(exc, \"trace_status\", None)" not in workflow:
    raise SystemExit("collect-trace-catch: neither old nor patched block found")

WORKFLOW.write_text(workflow, encoding="utf-8")
print("P7_FETCH_STATUS_SEMANTICS_PATCH=APPLIED")
