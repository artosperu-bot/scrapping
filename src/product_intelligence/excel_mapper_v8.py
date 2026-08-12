from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from openpyxl import load_workbook

from .marketplace_resolution import FOUND_STATES, resolve_marketplace_field
from .models import ProductRecord
from .normalize import canonical_key, key_norm
from .semantic_guard import infer_contract, is_placeholder
from .template_contract import analyze_template_contract
from .template_intelligence import classify_field

IDENTITY_ALIASES = {"brand", "model", "mpn", "ean", "upc", "gtin", "product name"}


def _strip_field_id(label: str) -> str:
    return re.sub(r"#\s*[A-Za-z]*\d+", "", str(label)).strip()


def _external_id(label: str) -> str | None:
    match = re.search(r"#\s*([A-Za-z]*\d+)", str(label))
    return match.group(1) if match else None


def _detect_header_and_description(ws):
    best = None
    for row in range(1, min(ws.max_row, 25) + 1):
        values = [str(ws.cell(row, col).value or "") for col in range(1, ws.max_column + 1)]
        ids = sum(bool(re.search(r"#\s*[A-Za-z]*\d+", value)) for value in values)
        mapped = sum(bool(canonical_key(_strip_field_id(value))) for value in values if value)
        score = ids * 4 + mapped
        if best is None or score > best[1]:
            best = (row, score)
    if best is None:
        return 1, None
    header_row = best[0]
    candidates = []
    for row in range(max(1, header_row - 4), header_row):
        values = [
            str(ws.cell(row, col).value or "")
            for col in range(1, ws.max_column + 1)
            if ws.cell(row, col).value not in (None, "")
        ]
        avg = sum(map(len, values)) / len(values) if values else 0
        candidates.append((avg, row))
    description_row = max(candidates)[1] if candidates else None
    return header_row, description_row


def map_header(header, desc=None):
    field_class, _ext_id, class_conf = classify_field(str(header), str(desc) if desc not in (None, "") else None)
    normalized = key_norm(_strip_field_id(header))
    canonical = canonical_key(_strip_field_id(header))
    if field_class == "SELLER_DATA":
        return None, .99, "SELLER_DATA"
    if field_class == "IMAGE":
        return "__image__", .99, "IMAGE"
    if canonical:
        return canonical, 1.0, field_class
    table = [
        (["nombre", "name", "titulo", "title"], "product name"),
        (["marca", "brand"], "brand"),
        (["modelo", "model"], "model"),
        (["descripcion", "description"], "description"),
        (["codigo de barras", "barcode"], "ean"),
        (["conectividad", "connectivity"], "connectivity"),
        (["bluetooth"], "bluetooth"),
        (["tipo de auricular", "headphone type"], "headphone type"),
        (["resistente al agua", "water resistance"], "water resistance"),
        (["alimentacion", "power source"], "power source"),
        (["autonomia", "battery life"], "battery life"),
        (["caracteristicas", "features"], "features"),
        (["segmento", "segment"], "segment"),
        (["tipo de salida", "output type"], "output type"),
        (["contenido del paquete", "package contents"], "package contents"),
        (["ancho del paquete", "package width"], "package width"),
        (["largo del paquete", "package length"], "package length"),
        (["alto del paquete", "package height"], "package height"),
        (["peso del paquete", "package weight"], "package weight"),
        (["alto", "height"], "height"),
        (["ancho", "width"], "width"),
        (["largo", "length"], "length"),
        (["dimensiones", "dimensions"], "dimensions"),
        (["potencia", "power"], "power"),
        (["garantia del producto", "product warranty"], "product warranty"),
        (["pais de produccion", "country of production"], "country of origin"),
        (["color"], "color"),
    ]
    for tokens, key in table:
        if any(key_norm(token) in normalized for token in tokens):
            return key, .92, field_class
    return None, class_conf, field_class


def _is_template_example(value, desc):
    if value in (None, ""):
        return False
    normalized_value = key_norm(str(value))
    normalized_desc = key_norm(str(desc or ""))
    if is_placeholder(value):
        return True
    if normalized_value in {"esto es un parrafo", "1234567890", "abc 1000 202", "999 999 99"}:
        return True
    numbers = re.findall(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)", str(desc or ""))
    if str(value).strip() in numbers and ("value" in normalized_desc or "example" in normalized_desc or "ejemplo" in normalized_desc):
        return True
    if "e.g." in normalized_desc or "ejemplo" in normalized_desc:
        return bool(normalized_value and normalized_value in normalized_desc)
    return False


def _option_keys(label):
    text = str(label or "")
    return {key_norm(text), key_norm(_strip_field_id(text))} - {""}


def _build_option_index(wb):
    index = {}
    for ws in wb.worksheets:
        for row in range(1, min(ws.max_row, 8) + 1):
            headers = [ws.cell(row, col).value for col in range(1, ws.max_column + 1)]
            populated = 0
            for col, header in enumerate(headers, 1):
                if header in (None, ""):
                    continue
                below = [ws.cell(rr, col).value for rr in range(row + 1, min(ws.max_row, row + 80) + 1)]
                if sum(value not in (None, "") for value in below) >= 2:
                    populated += 1
            if populated < 2:
                continue
            for col, header in enumerate(headers, 1):
                if header in (None, ""):
                    continue
                values = [ws.cell(rr, col).value for rr in range(row + 1, ws.max_row + 1) if ws.cell(rr, col).value not in (None, "")]
                if values:
                    for key in _option_keys(header):
                        index[key] = values
            break
        if ws.max_column == 1 and ws.max_row >= 2:
            values = [ws.cell(row, 1).value for row in range(1, ws.max_row + 1) if ws.cell(row, 1).value not in (None, "")]
            if len(values) >= 2:
                index[key_norm(ws.title)] = values
                if len(str(values[0])) < 100:
                    for key in _option_keys(values[0]):
                        index[key] = values[1:]
    return index


def _find_options(index, label):
    for key in _option_keys(label):
        if key in index:
            return index[key]
    base = key_norm(_strip_field_id(label))
    aliases = []
    if base in {"marca", "brand"}:
        aliases = ["marcas", "brands", "brand"]
    elif "categoria" in base or "category" in base:
        aliases = ["categorias", "categories", "category"]
    for alias in aliases:
        if key_norm(alias) in index:
            return index[key_norm(alias)]
    return []


def _match_record(records, rowvals, mapped):
    best = None
    for rec in records:
        score = 0
        for col, (_key, _confidence, _field_class) in mapped.items():
            value = rowvals.get(col)
            if value in (None, ""):
                continue
            normalized = key_norm(str(value))
            for attr in ["mpn", "ean", "upc", "gtin", "model", "product_name"]:
                record_value = getattr(rec.identity, attr, None)
                if record_value and (normalized == key_norm(str(record_value)) or (len(normalized) > 5 and normalized in key_norm(str(record_value)))):
                    score += 100 if attr in {"mpn", "ean", "upc", "gtin"} else 20
        if best is None or score > best[0]:
            best = (score, rec)
    return best[1] if best and best[0] > 0 else None


def _media_key(url):
    parsed = urlparse(str(url))
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in {"sw", "sh", "w", "h", "width", "height", "quality", "q", "format"}
    ]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", urlencode(query), ""))


def media_rank(item):
    scope_rank = {"EXACT_VARIANT": 3, "EXACT_PRODUCT": 2}.get(item.get("scope"), 0)
    source_class_rank = {"manufacturer": 3, "secondary": 2, "marketplace": 1}.get(str(item.get("source_class") or ""), 0)
    role_rank = 2 if item.get("role") == "product_gallery" else 0
    source = key_norm(item.get("source") or "")
    presentation_rank = 0
    if "jsonld product image" in source:
        presentation_rank += 3
    if "zoom" in source or "large" in source:
        presentation_rank += 2
    if "og image" in source:
        presentation_rank += 1
    return (scope_rank, source_class_rank, role_rank, presentation_rank, float(item.get("confidence", 0)))


def fill_excel_v8(template, output, records, overwrite=False, trace_path=None, row_assignments: dict[tuple[str, int], ProductRecord] | None = None):
    """Deterministic writer: it writes resolved values; it does not infer product facts."""
    row_assignments = row_assignments or {}
    wb = load_workbook(template)
    template_plan = analyze_template_contract(template)
    target_lookup = {
        (field["sheet"], field["column"]): field
        for sheet in template_plan.get("sheets", [])
        for field in sheet.get("fields", [])
    }
    options_index = _build_option_index(wb)
    written = []
    rejected = []
    unresolved = []
    cleared_examples = []

    for ws in wb.worksheets:
        header_row, description_row = _detect_header_and_description(ws)
        headers = {col: ws.cell(header_row, col).value for col in range(1, ws.max_column + 1) if ws.cell(header_row, col).value is not None}
        if not headers:
            continue
        mapped = {}
        contracts = {}
        descriptions = {}
        options = {}
        for col, header in headers.items():
            desc = ws.cell(description_row, col).value if description_row else None
            descriptions[col] = desc
            mapped[col] = map_header(str(header), str(desc) if desc not in (None, "") else None)
            key, _, field_class = mapped[col]
            contracts[col] = infer_contract(str(header), str(desc) if desc else None, key, field_class)
            options[col] = _find_options(options_index, str(header))

        id_cols = [col for col, (key, confidence, _field_class) in mapped.items() if key in IDENTITY_ALIASES and confidence >= .9]
        image_cols = [col for col, (key, _confidence, _field_class) in mapped.items() if key == "__image__"]
        if not id_cols:
            continue

        assigned_rows = [row for (sheet_name, row) in row_assignments if sheet_name == ws.title]
        last_row = max([ws.max_row, *assigned_rows]) if assigned_rows else ws.max_row
        for row in range(header_row + 1, last_row + 1):
            row_values = {col: ws.cell(row, col).value for col in headers}
            rec = row_assignments.get((ws.title, row)) or _match_record(records, row_values, mapped)
            if not rec or rec.identity.match_level == "CONFLICT":
                continue

            for col, (_key, _confidence, field_class) in mapped.items():
                if field_class == "SELLER_DATA" and _is_template_example(ws.cell(row, col).value, descriptions.get(col)):
                    cleared_examples.append({"sheet": ws.title, "cell": ws.cell(row, col).coordinate, "value": ws.cell(row, col).value, "reason": "TEMPLATE_EXAMPLE_SELLER_DATA"})
                    ws.cell(row, col).value = None

            if overwrite:
                for col, (_key, _confidence, field_class) in mapped.items():
                    plan = target_lookup.get((ws.title, col), {})
                    if field_class != "SELLER_DATA" or plan.get("role") == "SCRAPE_TARGET":
                        ws.cell(row, col).value = None

            for col, (key, _mapping_confidence, field_class) in mapped.items():
                if key == "__image__":
                    continue
                cell = ws.cell(row, col)
                header = str(headers[col])
                desc = descriptions[col]
                if _is_template_example(cell.value, desc):
                    cleared_examples.append({"sheet": ws.title, "cell": cell.coordinate, "value": cell.value, "reason": "TEMPLATE_EXAMPLE"})
                    cell.value = None

                plan_field = target_lookup.get((ws.title, col), {})
                if (field_class == "SELLER_DATA" and plan_field.get("role") != "SCRAPE_TARGET") or plan_field.get("role") in {"SELLER_INPUT", "MARKETPLACE_INPUT", "DERIVED_OUTPUT"}:
                    continue
                if cell.value not in (None, "") and not overwrite:
                    continue

                result = resolve_marketplace_field(
                    rec,
                    header=header,
                    description=str(desc) if desc else None,
                    canonical=key,
                    contract=contracts[col],
                    options=options[col],
                    external_id=_external_id(header),
                )
                audit = {
                    "sheet": ws.title,
                    "cell": cell.coordinate,
                    "header": header,
                    **result.to_dict(),
                }
                if result.status in FOUND_STATES and result.value not in (None, "") and result.confidence >= .85:
                    cell.value = result.value
                    written.append(audit)
                elif result.status not in {"SELLER_REQUIRED", "NOT_APPLICABLE", "NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS"}:
                    rejected.append(audit)
                else:
                    unresolved.append(audit)

            ranked = sorted(
                [
                    item for item in rec.images
                    if item.get("autofill_eligible", True)
                    and item.get("role", "product_gallery") == "product_gallery"
                    and item.get("scope") in {"EXACT_VARIANT", "EXACT_PRODUCT"}
                    and item.get("confidence", 0) >= .80
                ],
                key=media_rank,
                reverse=True,
            )
            seen = set()
            dedup = []
            for item in ranked:
                url = item.get("url")
                if not url:
                    continue
                canonical_url = _media_key(url)
                if canonical_url in seen:
                    continue
                seen.add(canonical_url)
                dedup.append(item)
            for index, col in enumerate(image_cols):
                if index >= len(dedup):
                    break
                cell = ws.cell(row, col)
                if cell.value not in (None, "") and not overwrite:
                    continue
                item = dedup[index]
                cell.value = item["url"]
                written.append({
                    "sheet": ws.title,
                    "cell": cell.coordinate,
                    "header": str(headers[col]),
                    "field": "product_image_url",
                    "value": item["url"],
                    "status": "FOUND_DIRECT",
                    "confidence": item.get("confidence", 0),
                    "source": item.get("source_page") or item["url"],
                    "source_class": item.get("source_class"),
                    "scope": item.get("scope"),
                    "reason": "validated_exact_product_media",
                })

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    report = {
        "written": written,
        "rejected": rejected,
        "unresolved": unresolved,
        "cleared_template_examples": cleared_examples,
        "summary": {
            "written_count": len(written),
            "rejected_count": len(rejected),
            "unresolved_count": len(unresolved),
            "cleared_template_examples": len(cleared_examples),
        },
    }
    if trace_path:
        Path(trace_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
