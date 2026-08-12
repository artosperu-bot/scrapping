from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook

from .ai_enrichment import AIConfig
from .discovery import search_web
from .excel_mapper_v8 import fill_excel_v8
from .models import ProductIdentity, ProductRecord
from .normalize import key_norm
from .pipeline import ProductPipeline
from .record_builder import build_record_strict
from .template_contract import analyze_template_contract
from .template_intelligence import analyze_matrix


@dataclass
class BatchItem:
    row: int
    sheet: str
    identity: ProductIdentity
    source_url: str | None = None


def _clean_id(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def detect_items(template: str) -> list[BatchItem]:
    """Detect product identities from the workbook without importing seller data into identity."""
    wb = load_workbook(template, data_only=False, read_only=False)
    items: list[BatchItem] = []
    for ws in wb.worksheets:
        matrix = [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)] for r in range(1, min(ws.max_row, 20) + 1)]
        info = analyze_matrix(matrix)
        fields = {f["column"]: f for f in info.get("fields") or []}
        if len(fields) < 3:
            continue
        header_row = info["header_row"]
        for row in range(header_row + 1, ws.max_row + 1):
            vals: dict[str, str] = {}
            source_url = None
            for col, field in fields.items():
                value = ws.cell(row, col).value
                if value in (None, ""):
                    continue
                label = key_norm(field["label"])
                canonical = field.get("canonical")
                if canonical in {"brand", "model", "ean", "upc", "gtin", "mpn"}:
                    vals[canonical] = _clean_id(value)
                if field.get("external_id") == "39" or canonical == "product_name":
                    vals["product_name"] = str(value).strip()
                if any(x in label for x in ["source url", "url fuente", "pagina oficial", "official url"]):
                    source_url = str(value).strip()

            # Explicit manufacturer identifiers always win. Seller SKU is deliberately ignored.
            for col in range(1, ws.max_column + 1):
                header = key_norm(str(ws.cell(header_row, col).value or ""))
                if any(x == header or x in header for x in ["mpn", "part number", "manufacturer part number", "codigo fabricante"]):
                    vals["mpn"] = _clean_id(ws.cell(row, col).value)

            if not any(vals.get(k) for k in ["mpn", "ean", "upc", "gtin", "model", "product_name"]):
                continue
            identity = ProductIdentity(**{k: v for k, v in vals.items() if k in ProductIdentity.model_fields})
            items.append(BatchItem(row=row, sheet=ws.title, identity=identity, source_url=source_url))
    return items


def _best_product_sheet(template: str) -> tuple[str, int]:
    wb = load_workbook(template, data_only=False, read_only=False)
    best = None
    for ws in wb.worksheets:
        matrix = [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)] for r in range(1, min(ws.max_row, 20) + 1)]
        info = analyze_matrix(matrix)
        score = len(info.get("fields") or [])
        if score and (best is None or score > best[0]):
            best = (score, ws.title, info["header_row"])
    if not best:
        raise ValueError("No se pudo detectar la hoja de carga de productos del Excel.")
    return best[1], best[2]


def manual_items(template: str, part_numbers: list[str]) -> list[BatchItem]:
    """Assign explicit manufacturer part numbers to product rows; never copy them to seller SKU."""
    sheet, header_row = _best_product_sheet(template)
    clean: list[str] = []
    seen: set[str] = set()
    for part_number in part_numbers:
        value = _clean_id(part_number)
        if not value:
            continue
        key = value.upper()
        if key in seen:
            continue
        seen.add(key)
        clean.append(value)
    return [BatchItem(header_row + i + 1, sheet, ProductIdentity(mpn=pn)) for i, pn in enumerate(clean)]


def _meaningful_product_tokens(value: str | None) -> set[str]:
    stop = {
        "the", "and", "with", "for", "of", "de", "del", "con", "para", "headphone", "headphones",
        "headset", "auricular", "auriculares", "wireless", "wired", "black", "blue", "white", "negro",
        "azul", "blanco", "on", "ear", "in",
    }
    return {x for x in re.split(r"[^a-z0-9]+", key_norm(value or "")) if len(x) >= 2 and x not in stop}


def _cross_source_consistent(primary: ProductRecord, other: ProductRecord, url: str) -> bool:
    mpn = str(primary.identity.mpn or "").strip()
    compact_url = re.sub(r"[^a-z0-9]", "", key_norm(url or ""))
    compact_mpn = re.sub(r"[^a-z0-9]", "", key_norm(mpn))
    if compact_mpn and compact_mpn in compact_url:
        return True
    a = _meaningful_product_tokens(primary.identity.product_name or primary.identity.model)
    b = _meaningful_product_tokens(other.identity.product_name or other.identity.model)
    if not a or not b:
        return False
    shared = a & b
    return len(shared) >= max(2, min(3, len(a) // 2))


def _merge_valid_records(records: list[ProductRecord]) -> ProductRecord:
    if not records:
        raise ValueError("no records to merge")

    def rank(rec: ProductRecord):
        return (
            2 if (rec.fetch or {}).get("source_class") == "manufacturer" else 1,
            2 if rec.identity.match_level == "EXACT" else 1,
            float(rec.identity.confidence or 0),
            len(rec.evidence),
        )

    ordered = sorted(records, key=rank, reverse=True)
    primary = ordered[0]
    evidence = []
    sources = []
    warnings = []
    notes = []
    media_by_url: dict[str, dict] = {}
    for rec in ordered:
        evidence.extend(rec.evidence)
        sources.extend(rec.sources)
        warnings.extend(rec.warnings)
        notes.extend(rec.technical_notes)
        for item in rec.media:
            url = item.get("url")
            if not url:
                continue
            previous = media_by_url.get(url)
            if previous is None or item.get("confidence", 0) > previous.get("confidence", 0):
                media_by_url[url] = item

    merged = build_record_strict(primary.identity, evidence, list(dict.fromkeys(sources)))
    merged.media = list(media_by_url.values())
    merged.images = [
        m for m in merged.media
        if m.get("media_type") == "image"
        and m.get("scope") in {"EXACT_VARIANT", "EXACT_PRODUCT"}
        and m.get("confidence", 0) >= .80
        and m.get("autofill_eligible")
    ]
    merged.videos = [
        m for m in merged.media
        if m.get("media_type") == "video"
        and m.get("scope") in {"EXACT_VARIANT", "EXACT_PRODUCT"}
        and m.get("confidence", 0) >= .80
        and m.get("autofill_eligible")
    ]
    merged.warnings = list(dict.fromkeys(warnings))
    merged.technical_notes = notes
    merged.site_profile = primary.site_profile
    merged.fetch = {
        "method": "multi_source",
        "source_class": (primary.fetch or {}).get("source_class"),
        "validated_sources": len(ordered),
        "manufacturer_sources": sum(1 for r in ordered if (r.fetch or {}).get("source_class") == "manufacturer"),
    }
    return merged


def scrape_item(item: BatchItem, out_dir: str, template_plan: dict | None = None, log=lambda m: None) -> ProductRecord | None:
    """Single product scraping path. The Excel contract decides which capabilities are needed."""
    pipe = ProductPipeline()
    candidates = [type("Candidate", (), {"url": item.source_url, "likely_official": True, "score": 1.0})()] if item.source_url else search_web(item.identity, limit=12)
    media_slots = int((template_plan or {}).get("media_slots", 0) or 0)
    target_semantics = list((template_plan or {}).get("scrape_semantics") or [])
    include_images = bool(media_slots)
    include_pdfs = bool((template_plan or {}).get("summary", {}).get("scrape_targets", 1))
    errors: list[str] = []
    accepted: list[ProductRecord] = []

    for candidate in candidates:
        try:
            host = (urlparse(candidate.url).hostname or "").removeprefix("www.")
            official_domain = host if getattr(candidate, "likely_official", False) else None
            if not official_domain and accepted:
                brand = re.sub(r"[^a-z0-9]", "", key_norm(accepted[0].identity.brand or ""))
                host_compact = re.sub(r"[^a-z0-9]", "", key_norm(host))
                if brand and brand in host_compact:
                    official_domain = host

            log(f"  probando: {candidate.url}")
            rec = pipe.process_url(
                item.identity,
                candidate.url,
                official_domain=official_domain,
                include_pdfs=include_pdfs,
                include_images=include_images,
                browser_fallback=True,
                target_semantics=target_semantics,
                media_slots=media_slots,
            )
            if rec.identity.identifiers_conflicting:
                raise ValueError("identificadores en conflicto")
            if accepted and not _cross_source_consistent(accepted[0], rec, candidate.url):
                raise ValueError("fuente exacta contiene el identificador pero no representa la misma ficha de producto")
            accepted.append(rec)
            log(f"  fuente validada: {(rec.fetch or {}).get('source_class', '?')} / {rec.identity.match_level}")
            has_manufacturer = any((r.fetch or {}).get("source_class") == "manufacturer" for r in accepted)
            if len(accepted) >= 3 or (has_manufacturer and len(accepted) >= 2):
                break
        except Exception as exc:
            errors.append(f"{candidate.url}: {type(exc).__name__}: {exc}")

    if not accepted:
        log("  SIN FUENTE VALIDADA: " + (errors[-1] if errors else "no hubo candidatos"))
        return None

    rec = _merge_valid_records(accepted)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", item.identity.mpn or item.identity.ean or item.identity.model or f"row_{item.row}")
    (Path(out_dir) / f"{stem}.json").write_text(rec.model_dump_json(indent=2), encoding="utf-8")
    return rec


def run_batch(
    template: str,
    output_dir: str,
    overwrite: bool = False,
    log=lambda m: None,
    ai_config: AIConfig | None = None,
    manual_part_numbers: list[str] | None = None,
) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Contract first: understand exactly what the workbook asks before going to the web.
    template_plan = analyze_template_contract(template)
    (out / "template_contract.json").write_text(json.dumps(template_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    ps = template_plan["summary"]
    log(
        f"Contrato Excel: {ps['fields_total']} campos | {ps['scrape_targets']} datos de producto | "
        f"{ps['media_slots']} imágenes | {ps['seller_inputs']} datos del vendedor | "
        f"{ps['marketplace_inputs']} datos marketplace"
    )

    manual_mode = bool(manual_part_numbers)
    items = manual_items(template, manual_part_numbers or []) if manual_mode else detect_items(template)
    log(f"Productos a procesar: {len(items)}" + (" (part numbers manuales)" if manual_mode else " (detectados en Excel)"))

    records: list[ProductRecord] = []
    # Every product is bound to the exact input row that created it. The mapper must not
    # rematch records against vocabulary/reference sheets such as Marcas/Opciones.
    row_assignments: dict[tuple[str, int], ProductRecord] = {}
    failures: list[dict] = []
    for index, item in enumerate(items, 1):
        label = item.identity.mpn or item.identity.ean or item.identity.model or item.identity.product_name
        log(f"[{index}/{len(items)}] {label}")
        rec = scrape_item(item, str(out / "json"), template_plan=template_plan, log=log)
        if rec:
            records.append(rec)
            row_assignments[(item.sheet, item.row)] = rec
        else:
            failures.append({"part_number": label, "sheet": item.sheet, "row": item.row})

    output_xlsx = str(out / (Path(template).stem + "_completado.xlsx"))
    trace = str(out / "trazabilidad.json")
    report = fill_excel_v8(
        template,
        output_xlsx,
        # Deliberately disable heuristic workbook-wide record matching. All records
        # already have a deterministic source row, which is safer and simpler.
        [],
        overwrite=overwrite,
        trace_path=trace,
        ai_config=ai_config,
        row_assignments=row_assignments,
    )
    summary = {
        "mode": "manual_part_numbers" if manual_mode else "excel_detected",
        "template_contract": template_plan["summary"],
        "template_contract_file": str(out / "template_contract.json"),
        "products_detected": len(items),
        "products_scraped": len(records),
        "products_failed": len(failures),
        "failures": failures,
        "output_excel": output_xlsx,
        "trace": trace,
        "mapping": report.get("summary", {}),
    }
    (out / "resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
