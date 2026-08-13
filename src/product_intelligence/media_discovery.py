from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .models import ProductIdentity

MediaScope = str


@dataclass
class MediaResource:
    url: str
    media_type: str  # image|video|pdf|other
    source: str
    scope: MediaScope = "UNVERIFIED"
    confidence: float = 0.0
    provider: str | None = None
    variant_hint: str | None = None
    alt: str | None = None
    evidence: list[str] | None = None
    conflict_reasons: list[str] | None = None
    role: str | None = None
    autofill_eligible: bool = False
    gallery_index: int | None = None

    def to_dict(self):
        return asdict(self)


def _norm(v: str | None) -> str:
    if not v:
        return ""
    return re.sub(r"[^a-z0-9]+", "", v.lower())


def _tokens(*values: str | None) -> set[str]:
    text = " ".join(v or "" for v in values).lower()
    return {t for t in re.split(r"[^a-z0-9]+", text) if len(t) > 1}


def _capacity_aliases(value: str | None) -> set[str]:
    if not value:
        return set()
    s = value.lower().replace(" ", "")
    out = {s}
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(tb|gb)", s)
    if m:
        num, unit = m.groups()
        out |= {f"{num}{unit}", f"{num}_{unit}", f"{num}-{unit}"}
        if unit == "tb":
            try:
                gb = int(float(num) * 1000)
                out |= {f"{gb}gb", f"{gb}_gb", f"{gb}-gb"}
            except Exception:
                pass
    return out


def _detect_provider(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if "vimeo.com" in host:
        return "vimeo"
    if "youtube.com" in host or "youtu.be" in host or "youtube-nocookie.com" in host:
        return "youtube"
    return None


def _media_type(url: str, tag_hint: str | None = None) -> str:
    path = urlparse(url).path.lower()
    if tag_hint == "video" or re.search(r"\.(mp4|webm|m3u8|mov)(?:$|\?)", url.lower()):
        return "video"
    if tag_hint == "image" or re.search(r"\.(jpe?g|png|webp|avif|gif|bmp|tiff?)(?:$|\?)", url.lower()):
        return "image"
    if path.endswith(".pdf"):
        return "pdf"
    if _detect_provider(url):
        return "video"
    return "other"


def classify_media_role(url: str, alt: str | None, source: str, media_type: str) -> tuple[str, bool]:
    """Separate actual product gallery assets from page chrome and recommendations."""
    hay = key_norm_media(f"{url} {alt or ''} {source}")
    if re.search(r"related|recommend|similar|cross[ _-]?sell|upsell|you may also|otros productos", hay, re.I):
        return "related_product", False
    if media_type == "video":
        return "product_video", True
    if re.search(r"footer|logo|sprite|icon[ _-]|badge|payment|social|avatar|swatch|flag|rating|stars", hay, re.I):
        return "page_asset", False
    if re.search(r"product image|hero|front|back|left|right|folded|detailshot|detail shot|gallery|product_image|angle|zoom|video_poster", hay, re.I):
        return "product_gallery", True
    if source.startswith("jsonld:Product.image") or source.startswith("meta:og:image"):
        return "product_gallery", True
    if source.startswith("json:") and re.search(r"image|gallery|media|asset|picture|photo", hay, re.I):
        return "product_gallery", True
    if source.startswith("network:image") and re.search(r"product|mastercatalog|catalog", hay, re.I):
        return "product_gallery", True
    return "unknown_image", False


def key_norm_media(v: str) -> str:
    return re.sub(r"[^a-z0-9._/-]+", " ", (v or "").lower()).strip()


_CONDITION_TERMS = {
    "refurbished": (r"certified[ -]?refurbished", r"refurbished", r"reacondicionad[oa]"),
    "used": (r"\bused\b", r"\busado\b", r"pre[ -]?owned", r"segunda mano"),
    "open_box": (r"open[ -]?box", r"caja abierta"),
    "renewed": (r"\brenewed\b", r"renovad[oa]"),
}


def _condition_set(*texts: str | None) -> set[str]:
    joined = " ".join(x or "" for x in texts).lower()
    return {name for name, pats in _CONDITION_TERMS.items() if any(re.search(p, joined, re.I) for p in pats)}


def _condition_mismatch(expected: ProductIdentity, *resource_context: str | None) -> bool:
    target = _condition_set(expected.product_name, expected.model, expected.variant)
    found = _condition_set(*resource_context)
    return bool(found - target)


def _has_repeated_path_segment(url: str) -> bool:
    parts = [p.lower() for p in urlparse(url).path.split("/") if p]
    return any(a == b for a, b in zip(parts, parts[1:]))


def _largest_srcset(raw: str | None) -> str | None:
    """Return the highest-resolution candidate rather than every thumbnail rendition."""
    best_url = None
    best_score = -1.0
    for part in (raw or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        url = bits[0]
        score = 1.0
        if len(bits) > 1:
            descriptor = bits[-1].lower()
            match = re.match(r"([0-9.]+)(w|x)$", descriptor)
            if match:
                score = float(match.group(1)) * (1000.0 if match.group(2) == "x" else 1.0)
        if score >= best_score:
            best_url, best_score = url, score
    return best_url


def validate_resource_identity(
    resource_url: str,
    expected: ProductIdentity,
    *,
    found_on_validated_product_page: bool,
    triggered_after_variant_selection: bool = False,
    surrounding_text: str | None = None,
) -> tuple[MediaScope, float, list[str], list[str]]:
    """Classify a media/resource URL without assuming same-family means same-variant."""
    hay = " ".join([resource_url, surrounding_text or ""]).lower()
    compact = _norm(hay)
    evidence: list[str] = []
    conflicts: list[str] = []

    strong_values = {
        "mpn": expected.mpn,
        "ean": expected.ean,
        "upc": expected.upc,
        "gtin": expected.gtin,
    }
    strong_positive = False
    for name, value in strong_values.items():
        if not value:
            continue
        nv = _norm(str(value))
        if nv and nv in compact:
            strong_positive = True
            evidence.append(f"{name}_match")

    target_caps = _capacity_aliases(expected.capacity)
    capacity_tokens = {f"{n}{u}".lower() for n, u in re.findall(r"(?<![a-z])([0-9]+(?:\.[0-9]+)?)[_\-\s]*(tb|gb)", hay, flags=re.I)}
    target_norm = {_norm(x) for x in target_caps}
    norm_caps = {_norm(x) for x in capacity_tokens}
    if target_norm and norm_caps:
        if norm_caps & target_norm:
            evidence.append("capacity_match")
        elif norm_caps:
            conflicts.append("capacity_conflict")

    for name in ["variant", "color"]:
        value = getattr(expected, name, None)
        if not value:
            continue
        nv = _norm(str(value))
        if len(nv) >= 3 and nv in compact:
            evidence.append(f"{name}_match")

    if expected.color:
        colors = {"black", "blue", "white", "red", "green", "gray", "grey", "beige", "pink", "purple", "orange", "yellow", "brown", "silver", "gold",
                  "negro", "azul", "blanco", "rojo", "verde", "gris", "rosado", "morado", "naranjo", "amarillo", "cafe", "plateado", "dorado"}
        mentioned = {c for c in colors if re.search(rf"(?<![a-z]){re.escape(c)}(?![a-z])", hay, re.I)}
        target = _norm(expected.color)
        if mentioned and not any(_norm(c) == target for c in mentioned) and "color_match" not in evidence:
            conflicts.append("color_conflict")

    if conflicts:
        return "UNVERIFIED", 0.0, evidence, conflicts

    if strong_positive and ("capacity_match" in evidence or not expected.capacity):
        evidence.append("strong_identifier_in_resource")
        return "EXACT_VARIANT", 0.99, evidence, conflicts

    if triggered_after_variant_selection and found_on_validated_product_page:
        if expected.capacity or expected.variant or expected.color:
            evidence.append("triggered_after_variant_selection")
            return "EXACT_VARIANT", 0.97, evidence, conflicts

    model_or_family = False
    for value, label in [(expected.model, "model_match"), (expected.product_name, "product_name_match")]:
        nv = _norm(value)
        if nv and len(nv) >= 3 and nv in compact:
            model_or_family = True
            evidence.append(label)

    if found_on_validated_product_page:
        evidence.append("embedded_or_requested_by_validated_product_page")
        variant_fields = [x for x in [expected.capacity, expected.variant, expected.color] if x]
        variant_positive = any(x in evidence for x in ["capacity_match", "variant_match", "color_match"])
        if model_or_family and variant_fields and variant_positive:
            return "EXACT_VARIANT", 0.98, evidence, conflicts
        if model_or_family:
            return "EXACT_PRODUCT", 0.94, evidence, conflicts
        return "PRODUCT_FAMILY", 0.84, evidence, conflicts

    if model_or_family and expected.brand and _norm(expected.brand) in compact:
        return "EXACT_PRODUCT", 0.80, evidence, conflicts

    return "UNVERIFIED", 0.20, evidence, conflicts


def discover_media(
    html: str,
    base_url: str,
    expected: ProductIdentity,
    *,
    network_resources: list[dict] | None = None,
    page_is_validated: bool = True,
) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    resources: dict[str, MediaResource] = {}

    def add(
        raw: str | None,
        source: str,
        *,
        tag_hint: str | None = None,
        alt: str | None = None,
        variant_selected: bool = False,
        surrounding_text: str | None = None,
        gallery_index: int | None = None,
    ):
        if not raw or raw.startswith("data:"):
            return
        url = urljoin(base_url, raw)
        if not url.startswith(("http://", "https://")):
            return
        mtype = _media_type(url, tag_hint)
        if mtype == "other":
            return
        context = " ".join(x for x in [base_url, alt, surrounding_text] if x)
        scope, confidence, ev, conflicts = validate_resource_identity(
            url,
            expected,
            found_on_validated_product_page=page_is_validated,
            triggered_after_variant_selection=variant_selected,
            surrounding_text=" ".join(x for x in [alt, surrounding_text] if x),
        )
        if mtype == "image" and _condition_mismatch(expected, context, url):
            conflicts = list(conflicts) + ["condition_mismatch"]
        if mtype == "image" and _has_repeated_path_segment(url):
            conflicts = list(conflicts) + ["malformed_repeated_path_segment"]
        if conflicts:
            confidence = 0.0
            scope = "UNVERIFIED"
        role, role_ok = classify_media_role(url, alt, source, mtype)
        obj = MediaResource(
            url=url,
            media_type=mtype,
            source=source,
            scope=scope,
            confidence=round(confidence, 3),
            provider=_detect_provider(url),
            alt=alt,
            evidence=ev,
            conflict_reasons=conflicts,
            role=role,
            autofill_eligible=bool(role_ok and scope in {"EXACT_VARIANT", "EXACT_PRODUCT"} and confidence >= .80),
            gallery_index=gallery_index if role == "product_gallery" else None,
        )
        old = resources.get(url)
        if old is None or obj.confidence > old.confidence:
            resources[url] = obj
        elif old is not None and old.gallery_index is None and obj.gallery_index is not None:
            old.gallery_index = obj.gallery_index

    for index, img in enumerate(soup.find_all("img"), 1):
        alt = img.get("alt") or img.get("title")
        contexts = []
        node = img
        for _ in range(3):
            node = getattr(node, "parent", None)
            if node is None:
                break
            contexts.append(str(getattr(node, "attrs", {}).get("class", "")))
            contexts.append(str(getattr(node, "attrs", {}).get("id", "")))
        parent_ctx = " ".join([str(img.get("class") or ""), str(img.get("id") or ""), *contexts])
        gallery_idx = index if re.search(r"gallery|product[ _-]?media|product[ _-]?image|pdp", parent_ctx, re.I) else None
        for attr in ["src", "data-src", "data-original", "data-original-src", "data-zoom", "data-zoom-image", "data-large", "data-large-image", "data-full", "data-image"]:
            add(
                img.get(attr),
                f"dom:{attr}:{parent_ctx}",
                tag_hint="image",
                alt=alt,
                surrounding_text=parent_ctx,
                gallery_index=gallery_idx,
            )
        for attr in ["srcset", "data-srcset"]:
            best = _largest_srcset(img.get(attr))
            add(
                best,
                f"dom:{attr}:{parent_ctx}",
                tag_hint="image",
                alt=alt,
                surrounding_text=parent_ctx,
                gallery_index=gallery_idx,
            )

    for source in soup.find_all("source"):
        parent = getattr(source.parent, "name", "")
        hint = "video" if parent == "video" else "image"
        context = " ".join([
            str(getattr(source.parent, "attrs", {}).get("class", "")),
            str(getattr(source.parent, "attrs", {}).get("id", "")),
        ])
        for attr in ["src", "data-src"]:
            add(source.get(attr), f"dom:source:{attr}:{context}", tag_hint=hint, surrounding_text=context)
        for attr in ["srcset", "data-srcset"]:
            add(_largest_srcset(source.get(attr)), f"dom:source:{attr}:{context}", tag_hint=hint, surrounding_text=context)

    for video in soup.find_all("video"):
        context = " ".join([str(video.get("class") or ""), str(video.get("id") or ""), str(getattr(video.parent, "attrs", {}).get("class", ""))])
        add(video.get("src"), f"dom:video:{context}", tag_hint="video", surrounding_text=context)
        add(video.get("poster"), f"dom:video_poster:{context}", tag_hint="image", surrounding_text=context)

    for iframe in soup.find_all("iframe"):
        src = iframe.get("src")
        if src and _detect_provider(urljoin(base_url, src)):
            add(src, "dom:iframe", tag_hint="video", surrounding_text=iframe.get("title"))

    for tag in soup.find_all(True):
        for attr in ["data-video", "data-video-url", "data-video-src", "data-video-href", "data-embed-url"]:
            raw = tag.get(attr)
            if raw and (_media_type(urljoin(base_url, raw), "video") == "video" or _detect_provider(urljoin(base_url, raw))):
                add(raw, f"dom:{attr}", tag_hint="video", surrounding_text=str(tag.get("class") or ""))
        youtube_id = tag.get("data-youtube-id") or tag.get("data-youtube")
        if youtube_id and not str(youtube_id).startswith(("http://", "https://")):
            add(f"https://www.youtube.com/watch?v={youtube_id}", "dom:data-youtube-id", tag_hint="video")
        vimeo_id = tag.get("data-vimeo-id")
        if vimeo_id and not str(vimeo_id).startswith(("http://", "https://")):
            add(f"https://vimeo.com/{vimeo_id}", "dom:data-vimeo-id", tag_hint="video")

    for meta_name in ["og:image", "twitter:image", "og:video", "og:video:url", "og:video:secure_url"]:
        for attr in ["property", "name"]:
            for m in soup.find_all("meta", attrs={attr: meta_name}):
                hint = "video" if "video" in meta_name else "image"
                add(m.get("content"), f"meta:{meta_name}", tag_hint=hint)

    def add_video_object(value: dict, source: str):
        add(value.get("embedUrl") or value.get("contentUrl") or value.get("url"), source, tag_hint="video", surrounding_text=value.get("name"))
        thumbnail = value.get("thumbnailUrl")
        if isinstance(thumbnail, str):
            add(thumbnail, f"{source}.thumbnail", tag_hint="image", surrounding_text=value.get("name"))
        elif isinstance(thumbnail, list):
            for thumb in thumbnail:
                if isinstance(thumb, str):
                    add(thumb, f"{source}.thumbnail", tag_hint="image", surrounding_text=value.get("name"))

    def walk(obj):
        if isinstance(obj, dict):
            typ_value = obj.get("@type", "")
            types = {str(x).lower() for x in (typ_value if isinstance(typ_value, list) else [typ_value]) if x}
            if "videoobject" in types:
                add_video_object(obj, "jsonld:VideoObject")
            if "product" in types:
                imgs = obj.get("image")
                if isinstance(imgs, str):
                    add(imgs, "jsonld:Product.image", tag_hint="image")
                elif isinstance(imgs, list):
                    for item in imgs:
                        if isinstance(item, str):
                            add(item, "jsonld:Product.image", tag_hint="image")
                        elif isinstance(item, dict):
                            add(item.get("url") or item.get("contentUrl"), "jsonld:Product.image", tag_hint="image")
                elif isinstance(imgs, dict):
                    add(imgs.get("url") or imgs.get("contentUrl"), "jsonld:Product.image", tag_hint="image")
                for key in ["video", "subjectOf"]:
                    val = obj.get(key)
                    if isinstance(val, dict):
                        add_video_object(val, f"jsonld:Product.{key}")
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, dict):
                                add_video_object(item, f"jsonld:Product.{key}")
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            walk(json.loads(script.string or ""))
        except Exception:
            pass

    def walk_media_json(obj, path="root", context=""):
        if isinstance(obj, dict):
            ctx_parts = []
            for k in ["name", "title", "productName", "sku", "mpn", "id", "color", "variant", "model"]:
                v = obj.get(k)
                if isinstance(v, (str, int, float)):
                    ctx_parts.append(f"{k}={v}")
            local_ctx = " ".join([context, *ctx_parts])[-1200:]
            for k, v in obj.items():
                pth = f"{path}.{k}"
                if isinstance(v, str):
                    mtype = _media_type(v)
                    if mtype == "image" and re.search(r"image|img|gallery|media|asset|photo|picture|src|url", str(k), re.I):
                        add(v, f"json:{pth}", tag_hint="image", surrounding_text=local_ctx)
                    elif (mtype == "video" or _detect_provider(urljoin(base_url, v))) and re.search(r"video|media|embed|content|src|url", str(k), re.I):
                        add(v, f"json:{pth}", tag_hint="video", surrounding_text=local_ctx)
                elif isinstance(v, (dict, list)):
                    walk_media_json(v, pth, local_ctx)
        elif isinstance(obj, list):
            for idx, v in enumerate(obj[:500]):
                walk_media_json(v, f"{path}[{idx}]", context)

    for script in soup.find_all("script"):
        typ = (script.get("type") or "").lower()
        raw = script.string or script.get_text(" ", strip=False) or ""
        if not raw or len(raw) > 5_000_000:
            continue
        if "json" in typ or script.get("id") in {"__NEXT_DATA__", "__NUXT_DATA__"}:
            try:
                walk_media_json(json.loads(raw), f"script:{script.get('id') or typ or 'json'}")
            except Exception:
                pass

    for link in soup.find_all("a", href=True):
        href = link.get("href")
        ctx = " ".join([str(link.get("class") or ""), str(link.get("id") or ""), link.get_text(" ", strip=True)[:120]])
        full = urljoin(base_url, href)
        mtype = _media_type(full)
        if mtype == "image" and (link.find("img") is not None or re.search(r"gallery|zoom|product|image", ctx, re.I)):
            add(href, f"dom:a:href:{ctx}", tag_hint="image", surrounding_text=ctx)
        elif mtype == "video" or _detect_provider(full):
            add(href, f"dom:a:video:{ctx}", tag_hint="video", surrounding_text=ctx)

    for item in network_resources or []:
        url = item.get("url")
        rtype = item.get("resource_type")
        if rtype in {"image", "media", "document"} or _media_type(url or "") != "other":
            add(
                url,
                f"network:{rtype or 'unknown'}",
                tag_hint="video" if rtype == "media" else None,
                variant_selected=bool(item.get("triggered_after_variant_selection")),
            )

    rows = [r.to_dict() for r in resources.values()]
    rows.sort(
        key=lambda x: (
            float(x.get("confidence") or 0),
            1 if x.get("gallery_index") is not None else 0,
            -(int(x.get("gallery_index") or 999999)),
        ),
        reverse=True,
    )
    return rows


def build_site_profile(page_url: str, media: list[dict], json_responses: list[dict] | None = None) -> dict:
    origin = (urlparse(page_url).hostname or "").lower()
    asset_hosts: dict[str, dict] = {}
    for item in media:
        host = (urlparse(item.get("url") or "").hostname or "").lower()
        if not host or host == origin:
            continue
        rec = asset_hosts.setdefault(host, {"host": host, "types": set(), "count": 0, "max_confidence": 0.0})
        rec["types"].add(item.get("media_type"))
        rec["count"] += 1
        rec["max_confidence"] = max(rec["max_confidence"], float(item.get("confidence") or 0))
    for item in json_responses or []:
        host = (urlparse(item.get("url") or "").hostname or "").lower()
        if host and host != origin:
            rec = asset_hosts.setdefault(host, {"host": host, "types": set(), "count": 0, "max_confidence": 0.0})
            rec["types"].add("json_api")
            rec["count"] += 1
    hosts = []
    for rec in asset_hosts.values():
        rec["types"] = sorted(x for x in rec["types"] if x)
        rec["max_confidence"] = round(rec["max_confidence"], 3)
        hosts.append(rec)
    return {
        "origin_domain": origin,
        "observed_asset_hosts": sorted(hosts, key=lambda x: (x["max_confidence"], x["count"]), reverse=True),
        "video_providers": sorted({m.get("provider") for m in media if m.get("provider")}),
        "note": "Observed from this validated page; not a hardcoded trust list.",
    }
