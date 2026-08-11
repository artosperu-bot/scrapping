from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any
from rapidfuzz import fuzz
from .normalize import canonical_key, key_norm
from .semantic_guard import infer_contract


SELLER_HINTS = {
    "price", "saleprice", "precio", "stock", "quantity", "cantidad", "seller sku", "sku vendedor",
    "sale start", "sale end", "fecha inicio", "fecha fin", "commission", "comision", "sku del vendedor", "seller sku", "sku padre", "parent sku", "garantia del vendedor", "garantía del vendedor", "seller warranty",
}
IMAGE_HINTS = {"image", "imagen", "foto", "photo", "picture", "url imagen", "image url"}


@dataclass
class TemplateField:
    column: int
    label: str
    canonical: str | None
    field_class: str
    confidence: float
    description: str | None = None
    external_id: str | None = None
    contract: dict | None = None

    def to_dict(self): return asdict(self)


def classify_field(label: str, description: str | None = None) -> tuple[str, str | None, float]:
    joined = key_norm(f"{label} {description or ''}")
    ext_id = None
    m = re.search(r"#\s*(\d+)", str(label))
    if m: ext_id = m.group(1)
    if any(key_norm(x) in joined for x in SELLER_HINTS):
        return "SELLER_DATA", ext_id, 0.98
    if any(key_norm(x) in joined for x in IMAGE_HINTS):
        return "IMAGE", ext_id, 0.96
    # Explicit marketplace-derived fields: logistics English name and product variation.
    nlabel = key_norm(re.sub(r"#\s*\d+", "", str(label)).strip())
    if ext_id == "133816" or nlabel in {"nameen", "name en", "english name", "nombre ingles", "nombre en ingles"}:
        return "DERIVABLE", ext_id, 0.99
    if ext_id == "1700" or "variacion" in nlabel or "variation" in nlabel:
        return "DERIVABLE", ext_id, 0.98
    ck = canonical_key(re.sub(r"#\s*\d+", "", str(label)).strip())
    if ck:
        return "SCRAPABLE", ext_id, 1.0
    if any(x in joined for x in ["nombre", "name", "descripcion", "description", "titulo", "title"]):
        return "DERIVABLE", ext_id, 0.90
    return "UNKNOWN", ext_id, 0.35


def infer_header_row(matrix: list[list[Any]], scan_rows: int = 20) -> int:
    """Infer a likely machine-field row from a rectangular cell matrix (0-based)."""
    best = (0, -1.0)
    for r, row in enumerate(matrix[:scan_rows]):
        values = [str(v).strip() for v in row if v not in (None, "")]
        if not values: continue
        mapped = sum(1 for v in values if canonical_key(re.sub(r"#\s*\d+", "", v).strip()))
        ids = sum(1 for v in values if re.search(r"#\s*\d+", v))
        compact = sum(1 for v in values if len(v) < 80)
        score = mapped * 3 + ids * 2 + compact / max(len(values), 1)
        if score > best[1]: best = (r, score)
    return best[0]


def analyze_matrix(matrix: list[list[Any]]) -> dict:
    header = infer_header_row(matrix)
    # A nearby verbose row often contains field instructions. Search up to 3 rows above.
    desc_row = None
    candidates = []
    for r in range(max(0, header - 3), header):
        vals = [str(v) for v in matrix[r] if v not in (None, "")]
        avg = sum(map(len, vals)) / len(vals) if vals else 0
        candidates.append((avg, r))
    if candidates:
        desc_row = max(candidates)[1]
    fields=[]
    width=max((len(r) for r in matrix), default=0)
    for c in range(width):
        label = matrix[header][c] if c < len(matrix[header]) else None
        if label in (None, ""): continue
        desc = matrix[desc_row][c] if desc_row is not None and c < len(matrix[desc_row]) else None
        cls, ext_id, conf = classify_field(str(label), str(desc) if desc not in (None, "") else None)
        canonical = canonical_key(re.sub(r"#\s*\d+", "", str(label)).strip())
        contract = infer_contract(str(label), str(desc) if desc else None, canonical, cls).to_dict()
        fields.append(TemplateField(c + 1, str(label), canonical, cls, conf, str(desc) if desc else None, ext_id, contract).to_dict())
    return {"header_row": header + 1, "description_row": (desc_row + 1) if desc_row is not None else None, "fields": fields}
