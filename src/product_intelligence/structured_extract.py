from __future__ import annotations

from typing import Any


def extract_embedded_metadata(html: str, base_url: str) -> dict[str, Any]:
    """Extract JSON-LD, Microdata, OpenGraph and related embedded metadata."""
    try:
        import extruct
        return extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph"],
            uniform=True,
        )
    except Exception:
        return {}


def flatten_pairs(obj: Any, prefix: str = "", max_depth: int = 5) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    def walk(x: Any, path: str, depth: int):
        if depth > max_depth:
            return
        if isinstance(x, dict):
            for k, v in x.items():
                if str(k).startswith("@"):
                    continue
                p = f"{path}.{k}" if path else str(k)
                if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 500:
                    out.append((p, v))
                else:
                    walk(v, p, depth + 1)
        elif isinstance(x, list):
            for i, v in enumerate(x[:50]):
                walk(v, path, depth + 1)
    walk(obj, prefix, 0)
    return out
