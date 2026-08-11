from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


@dataclass
class ImageCandidate:
    url: str
    score: float
    source: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    reasons: list[str] | None = None

    def to_dict(self):
        return asdict(self)


def _as_int(v):
    try:
        return int(str(v).replace("px", "").strip())
    except Exception:
        return None


def _srcset_urls(srcset: str) -> list[str]:
    out = []
    for part in (srcset or "").split(","):
        u = part.strip().split(" ")[0]
        if u:
            out.append(u)
    return out


def _tokens(*values: str | None) -> set[str]:
    s = " ".join(v or "" for v in values).lower()
    return {x for x in re.split(r"[^a-z0-9]+", s) if len(x) > 1}


def extract_image_candidates(html: str, base_url: str, identity_terms: list[str] | None = None) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    identity_tokens = _tokens(*(identity_terms or []))
    seen: dict[str, ImageCandidate] = {}

    def add(raw_url: str | None, source: str, alt: str | None = None, width=None, height=None):
        if not raw_url or raw_url.startswith("data:"):
            return
        url = urljoin(base_url, raw_url)
        low = url.lower()
        if not low.startswith(("http://", "https://")):
            return
        w, h = _as_int(width), _as_int(height)
        score = 0.20
        reasons = [source]
        bad = ["logo", "icon", "sprite", "favicon", "badge", "avatar", "payment", "social"]
        if any(x in low for x in bad):
            score -= 0.55; reasons.append("asset_noise")
        toks = _tokens(url, alt)
        overlap = len(toks & identity_tokens)
        if overlap:
            score += min(0.35, overlap * 0.10); reasons.append("identity_tokens")
        if source in {"jsonld", "og:image", "twitter:image"}:
            score += 0.30; reasons.append("structured_primary")
        if source in {"picture", "srcset"}:
            score += 0.08
        if w and h:
            if w >= 600 and h >= 600:
                score += 0.20; reasons.append("large")
            elif w < 120 or h < 120:
                score -= 0.35; reasons.append("tiny")
        if any(k in low for k in ["product", "gallery", "zoom", "large", "original", "hires", "hero"]):
            score += 0.15; reasons.append("gallery_hint")
        candidate = ImageCandidate(url=url, score=round(max(0.0, min(1.0, score)), 3), source=source, alt=alt, width=w, height=h, reasons=reasons)
        old = seen.get(url)
        if old is None or candidate.score > old.score:
            seen[url] = candidate

    for meta_key in [("property", "og:image"), ("name", "twitter:image")]:
        for m in soup.find_all("meta", attrs={meta_key[0]: meta_key[1]}):
            add(m.get("content"), meta_key[1])

    for img in soup.find_all("img"):
        alt = img.get("alt") or img.get("title")
        for attr in ["src", "data-src", "data-original", "data-zoom-image", "data-large-image"]:
            add(img.get(attr), "img", alt, img.get("width"), img.get("height"))
        for attr in ["srcset", "data-srcset"]:
            for u in _srcset_urls(img.get(attr) or ""):
                add(u, "srcset", alt, img.get("width"), img.get("height"))

    for source in soup.find_all("source"):
        for attr in ["srcset", "data-srcset"]:
            for u in _srcset_urls(source.get(attr) or ""):
                add(u, "picture")

    # JSON-LD Product.image
    import json
    def walk(x):
        if isinstance(x, dict):
            if str(x.get("@type", "")).lower() == "product":
                imgs = x.get("image")
                if isinstance(imgs, str): add(imgs, "jsonld")
                elif isinstance(imgs, list):
                    for i in imgs:
                        if isinstance(i, str): add(i, "jsonld")
                        elif isinstance(i, dict): add(i.get("url") or i.get("contentUrl"), "jsonld")
                elif isinstance(imgs, dict): add(imgs.get("url") or imgs.get("contentUrl"), "jsonld")
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try: walk(json.loads(script.string or ""))
        except Exception: pass

    out = sorted(seen.values(), key=lambda x: x.score, reverse=True)
    return [x.to_dict() for x in out]
