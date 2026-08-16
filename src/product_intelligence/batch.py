from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from openpyxl import load_workbook

from .input_identity import parse_product_query
from .discovery import search_web, search_web_for_fields
from .document_discovery import discover_product_documents
from .document_ingestion import process_pdf_document
from .excel_intake import analyze_workbook_intake
from .excel_mapper_v8 import fill_excel_v8
from .models import ProductIdentity, ProductRecord
from .normalize import key_norm
from .pdf_search_trace import PdfSearchTrace, format_trace_lines
from .pipeline import ProductPipeline
from .record_builder import build_record_strict
from .resolution_engine import analyze_resolution
from .semantic_guard import is_placeholder
from .source_strategy import SourceStrategy
from .template_contract import analyze_template_contract
from .template_intelligence import analyze_matrix


@dataclass
class BatchItem:
    row: int
    sheet: str
    identity: ProductIdentity
    source_url: str | None = None
    source_urls: list[str] | None = None


_TEMPLATE_IDENTITY_EXAMPLES = {
    "1234567890",
    "99999999",
    "999999999",
    "abc-1000-202",
    "abc1000202",
}


def _clean_id(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None


def _identity_placeholder(value) -> bool:
    text = _clean_id(value)
    if not text:
        return True
    compact = key_norm(text).replace(" ", "")
    if compact in _TEMPLATE_IDENTITY_EXAMPLES:
        return True
    return is_placeholder(text)


def _looks_like_part_number(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text or " " in text or len(text) < 6 or len(text) > 48:
        return False
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", text):
        return False
    if text.isdigit():
        return False
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    return letters >= 2 and digits >= 1


def _promote_mpn(vals: dict[str, str]) -> None:
    if vals.get("mpn"):
        return
    for key in ("model", "product_name"):
        value = vals.get(key)
        if _looks_like_part_number(value):
            vals["mpn"] = value
            return


def detect_items(template: str) -> list[BatchItem]:
    intake = analyze_workbook_intake(template)
    return [
        BatchItem(
            row=product.row,
            sheet=product.sheet,
            identity=product.identity,
            source_url=product.source_url,
            source_urls=list(product.source_urls or []),
        )
        for product in intake.products
    ]


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


def manual_identity_items(template: str, identities: list[ProductIdentity], source_urls_by_index: list[list[str]] | None = None) -> list[BatchItem]:
    sheet, header_row = _best_product_sheet(template)
    items = []
    for i, ident in enumerate(identities):
        urls = []
        if source_urls_by_index and i < len(source_urls_by_index):
            urls = list(dict.fromkeys(u for u in (source_urls_by_index[i] or []) if u))
        items.append(BatchItem(header_row + i + 1, sheet, ident, source_urls=urls))
    return items


def manual_items(template: str, part_numbers: list[str]) -> list[BatchItem]:
    identities = []
    for value in part_numbers:
        ident = parse_product_query(str(value))
        if ident:
            identities.append(ident)
    return manual_identity_items(template, identities)


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
        "source_decisions": [
            (r.fetch or {}).get("source_decision")
            for r in ordered
            if (r.fetch or {}).get("source_decision")
        ],
        "source_validation_counts": {
            "validated_sources": len(ordered),
            "material_evidence": len(merged.evidence or []),
            "final_specifications": len(merged.specifications or {}),
        },
    }
    return merged


def _compact(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", key_norm(value or ""))


def _candidate_official_domain(candidate, identity: ProductIdentity, accepted: list[ProductRecord]) -> str | None:
    """Return only a discovery hint; the pipeline independently proves authority.

    Critically, a brand token in the hostname is no longer treated as an official-domain hint.
    """
    host = (urlparse(candidate.url).hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    if bool(getattr(candidate, "likely_official", False)):
        return host
    if getattr(candidate, "manual_source", False):
        label = _compact(host.split(".")[0])
        strong = _compact(identity.mpn or identity.model or identity.product_name)
        if len(label) >= 3 and strong and strong.startswith(label):
            return host
    return None


def _manufacturer_domains(records: list[ProductRecord]) -> set[str]:
    out: set[str] = set()
    for rec in records:
        if (rec.fetch or {}).get("source_class") != "manufacturer":
            continue
        for url in [rec.fetch.get("final_url") if rec.fetch else None, *(rec.sources or [])]:
            if not url:
                continue
            host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            if host:
                out.add(host)
    return out


def _resolution_for(records: list[ProductRecord], template_plan: dict | None) -> tuple[ProductRecord, dict]:
    merged = _merge_valid_records(records)
    return merged, analyze_resolution(merged, template_plan)


def _coverage_sufficient(resolution: dict, has_manufacturer: bool) -> bool:
    if not has_manufacturer or resolution.get("blocked"):
        return False
    return not list(resolution.get("research_terms") or [])


def _enriched_identity(item: BatchItem, rec: ProductRecord) -> ProductIdentity | None:
    learned_brand = rec.identity.brand or item.identity.brand
    learned_model = rec.identity.model or rec.identity.product_name or item.identity.model or item.identity.product_name
    strong = item.identity.mpn or item.identity.ean or item.identity.upc or item.identity.gtin or rec.identity.mpn or rec.identity.gtin
    if not learned_brand or not strong:
        return None
    return ProductIdentity(
        mpn=item.identity.mpn or rec.identity.mpn,
        ean=item.identity.ean or rec.identity.ean,
        upc=item.identity.upc or rec.identity.upc,
        gtin=item.identity.gtin or rec.identity.gtin,
        brand=learned_brand,
        model=learned_model,
    )


def _prioritize(candidates) -> list:
    return sorted(candidates, key=lambda c: (not bool(getattr(c, "likely_official", False)), -float(getattr(c, "score", 0))))


def _looks_like_pdf_url(url: str | None) -> bool:
    path = (urlparse(str(url or "")).path or "").lower()
    return path.endswith(".pdf")


def _product_key(identity: ProductIdentity) -> str:
    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or "producto")


def _log_source_decision(rec: ProductRecord, log, prefix: str = "  ") -> bool:
    decision = (rec.fetch or {}).get("source_decision") or {}
    page_type = decision.get("page_type", "UNKNOWN")
    identity = decision.get("identity", rec.identity.match_level or "UNKNOWN")
    authority = decision.get("authority", (rec.fetch or {}).get("source_class", "unknown"))
    material = bool(decision.get("material_allowed", True))
    evidence_count = len(rec.evidence or [])
    allowed = material and identity in {"EXACT", "COMPATIBLE", "HIGH"} and evidence_count > 0
    reason = "OK" if allowed else (
        "PAGE_TYPE_NOT_MATERIAL" if not material
        else "IDENTITY_NOT_STRONG_ENOUGH" if identity not in {"EXACT", "COMPATIBLE", "HIGH"}
        else "NO_POLICY_APPROVED_EVIDENCE"
    )
    log(f"{prefix}PAGE_TYPE={page_type} confidence={decision.get('page_type_confidence', '?')}")
    log(f"{prefix}IDENTITY={identity} confidence={decision.get('identity_confidence', '?')}")
    log(f"{prefix}AUTHORITY={authority} confidence={decision.get('authority_confidence', '?')}")
    log(f"{prefix}EVIDENCE_ALLOWED={'YES' if allowed else 'NO'} reason={reason} evidence={evidence_count}")
    return allowed


def _log_source_rejection(exc: Exception, log, prefix: str = "  ") -> None:
    text = str(exc)
    marker = "SOURCE_VALIDATION_REJECTED:"
    if marker in text:
        detail = text.split(marker, 1)[1].strip()
        reason = detail.split()[0] if detail else "SOURCE_VALIDATION_REJECTED"
        if "identity=CONFLICT" in detail or "IDENTITY_CONFLICT" in detail:
            log(f"{prefix}IDENTITY=CONFLICT")
        if "page_type=" in detail:
            page_type = detail.split("page_type=", 1)[1].split()[0]
            log(f"{prefix}PAGE_TYPE={page_type}")
        if "authority=" in detail:
            authority = detail.split("authority=", 1)[1].split()[0]
            log(f"{prefix}AUTHORITY={authority}")
        log(f"{prefix}EVIDENCE_ALLOWED=NO reason={reason}")
    else:
        log(f"{prefix}SOURCE_REJECTED={type(exc).__name__}: {text}")


def _ingest_direct_documents(
    identity: ProductIdentity,
    *,
    target_semantics: list[str],
    seen_urls: set[str],
    errors: list[str],
    log,
    limit: int = 6,
) -> list[ProductRecord]:
    accepted: list[ProductRecord] = []
    trace = PdfSearchTrace(_product_key(identity))
    document_candidates = discover_product_documents(identity, limit=limit, trace=trace)
    if document_candidates:
        log(f"  PDF CANDIDATOS: {len(document_candidates)}")
    for candidate in document_candidates:
        if candidate.url in seen_urls:
            continue
        seen_urls.add(candidate.url)
        try:
            doc_rec = process_pdf_document(identity, candidate.url, target_semantics=target_semantics, trace=trace)
            if not _log_source_decision(doc_rec, log):
                raise ValueError("SOURCE_VALIDATION_REJECTED: NO_POLICY_APPROVED_EVIDENCE")
            accepted.append(doc_rec)
            log(f"  PDF VALIDADO: {candidate.url}")
            if len(accepted) >= 3:
                break
        except Exception as exc:
            errors.append(f"document:{candidate.url}: {type(exc).__name__}: {exc}")
            _log_source_rejection(exc, log)
    for line in format_trace_lines(trace):
        log(line)
    return accepted


def scrape_item(
    item: BatchItem,
    out_dir: str,
    template_plan: dict | None = None,
    log=lambda m: None,
    source_strategy: SourceStrategy | None = None,
) -> ProductRecord | None:
    strategy = (source_strategy or SourceStrategy()).normalized()
    pipe = ProductPipeline()
    manual_urls = list(dict.fromkeys([u for u in ((item.source_urls or []) + ([item.source_url] if item.source_url else [])) if u]))
    eligible_manual_urls = [
        u for u in manual_urls
        if strategy.web or (strategy.pdf and _looks_like_pdf_url(u))
    ]
    manual_candidates = [
        type("Candidate", (), {"url": u, "likely_official": False, "score": 2.0, "ai_assisted": False, "manual_source": True})()
        for u in eligible_manual_urls
    ]
    free_candidates = search_web(item.identity, limit=18) if strategy.web else []
    known_manual = set(eligible_manual_urls)
    candidates = manual_candidates + _prioritize([c for c in free_candidates if getattr(c, "url", None) not in known_manual])
    if manual_urls:
        log(
            f"  fuentes manuales: {len(manual_urls)}; elegibles por estrategia={len(eligible_manual_urls)}; "
            "se validan antes de aceptar evidencia"
        )

    media_slots = int((template_plan or {}).get("media_slots", 0) or 0)
    target_semantics = list((template_plan or {}).get("scrape_semantics") or [])
    include_images = bool(media_slots) and strategy.web
    include_pdfs = strategy.pdf and bool((template_plan or {}).get("summary", {}).get("scrape_targets", 1))
    errors: list[str] = []
    accepted: list[ProductRecord] = []
    queue = list(candidates)
    seen_urls = {getattr(c, "url", "") for c in queue}
    manufacturer_followup_done = False
    cursor = 0
    max_validated_sources = 10

    while cursor < len(queue) and len(accepted) < max_validated_sources:
        candidate = queue[cursor]
        cursor += 1
        try:
            log(f"  probando: {candidate.url}")
            if strategy.pdf and _looks_like_pdf_url(candidate.url):
                rec = process_pdf_document(item.identity, candidate.url, target_semantics=target_semantics)
            else:
                if not strategy.web:
                    continue
                official_domain = _candidate_official_domain(candidate, item.identity, accepted)
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

            if not _log_source_decision(rec, log):
                raise ValueError("SOURCE_VALIDATION_REJECTED: NO_POLICY_APPROVED_EVIDENCE")
            if rec.identity.identifiers_conflicting:
                raise ValueError("SOURCE_VALIDATION_REJECTED: IDENTITY_CONFLICT legacy_identifiers")
            if accepted and not _cross_source_consistent(accepted[0], rec, candidate.url):
                raise ValueError("SOURCE_VALIDATION_REJECTED: CROSS_SOURCE_PRODUCT_CONFLICT")
            accepted.append(rec)
            log(f"  fuente validada: {(rec.fetch or {}).get('source_class', '?')} / {rec.identity.match_level}")

            if strategy.web and not manufacturer_followup_done:
                enriched = _enriched_identity(item, rec)
                if enriched:
                    followups = search_web(enriched, limit=20)
                    fresh = [c for c in followups if c.url not in seen_urls]
                    for c in fresh:
                        seen_urls.add(c.url)
                    queue[cursor:cursor] = _prioritize(fresh)
                    log(f"  búsqueda fabricante reforzada: {len(fresh)} candidatos nuevos")
                manufacturer_followup_done = True

            has_manufacturer = any((r.fetch or {}).get("source_class") == "manufacturer" for r in accepted)
            if has_manufacturer:
                _merged, partial_resolution = _resolution_for(accepted, template_plan)
                remaining = list(partial_resolution.get("research_terms") or [])
                log(f"  cobertura actual: {len(target_semantics) - len(remaining)}/{len(target_semantics)} semánticas; pendientes={len(remaining)}")
                if _coverage_sufficient(partial_resolution, has_manufacturer=True):
                    log("  cobertura suficiente con fabricante validado; se detiene PASS 1")
                    break
        except Exception as exc:
            errors.append(f"{candidate.url}: {type(exc).__name__}: {exc}")
            _log_source_rejection(exc, log)

    if not accepted and strategy.pdf:
        accepted.extend(_ingest_direct_documents(
            item.identity,
            target_semantics=target_semantics,
            seen_urls=seen_urls,
            errors=errors,
            log=log,
        ))

    if not accepted:
        log("  SIN FUENTE VALIDADA: " + (errors[-1] if errors else "no hubo candidatos"))
        return None

    rec = _merge_valid_records(accepted)
    resolution = analyze_resolution(rec, template_plan)
    gap_terms = list(resolution.get("research_terms") or [])

    if gap_terms and strategy.pdf:
        document_extra = _ingest_direct_documents(
            rec.identity,
            target_semantics=gap_terms,
            seen_urls=seen_urls,
            errors=errors,
            log=log,
        )
        if document_extra:
            accepted.extend(document_extra)
            rec = _merge_valid_records(accepted)
            resolution = analyze_resolution(rec, template_plan)
            gap_terms = list(resolution.get("research_terms") or [])
            log(f"  cobertura tras documentos: pendientes={len(gap_terms)}")

    if strategy.web and gap_terms:
        mode = "conflictos/huecos" if resolution.get("blocked") else "huecos"
        log(f"  segunda pasada por {mode}: {len(gap_terms)} campos/grupos pendientes")
        current_sources = set(rec.sources or [])
        total_extra = 0
        max_extra = 8

        for start in range(0, len(gap_terms), 4):
            if total_extra >= max_extra:
                break
            chunk = gap_terms[start:start + 4]
            log(f"    buscando específicamente: {', '.join(chunk)}")
            chunk_candidates = _prioritize(search_web_for_fields(rec.identity, chunk, limit=12))
            chunk_extra: list[ProductRecord] = []

            for candidate in chunk_candidates:
                if total_extra >= max_extra:
                    break
                if candidate.url in seen_urls or candidate.url in current_sources:
                    continue
                seen_urls.add(candidate.url)
                try:
                    official_domain = _candidate_official_domain(candidate, rec.identity, accepted)
                    gap_rec = pipe.process_url(
                        item.identity,
                        candidate.url,
                        official_domain=official_domain,
                        include_pdfs=include_pdfs,
                        include_images=include_images,
                        browser_fallback=True,
                        target_semantics=chunk,
                        media_slots=media_slots,
                    )
                    if not _log_source_decision(gap_rec, log, prefix="    "):
                        raise ValueError("SOURCE_VALIDATION_REJECTED: NO_POLICY_APPROVED_EVIDENCE")
                    if gap_rec.identity.identifiers_conflicting:
                        raise ValueError("SOURCE_VALIDATION_REJECTED: IDENTITY_CONFLICT legacy_identifiers")
                    if accepted and not _cross_source_consistent(accepted[0], gap_rec, candidate.url):
                        raise ValueError("SOURCE_VALIDATION_REJECTED: CROSS_SOURCE_PRODUCT_CONFLICT")
                    chunk_extra.append(gap_rec)
                    accepted.append(gap_rec)
                    total_extra += 1
                    log(f"    gap fuente validada: {(gap_rec.fetch or {}).get('source_class','?')} / {gap_rec.identity.match_level}")
                    if len(chunk_extra) >= 2:
                        break
                except Exception as exc:
                    errors.append(f"gap:{candidate.url}: {type(exc).__name__}: {exc}")
                    _log_source_rejection(exc, log, prefix="    ")

            if chunk_extra:
                rec = _merge_valid_records(accepted)
                resolution = analyze_resolution(rec, template_plan)
                gap_terms = list(resolution.get("research_terms") or [])
                if not gap_terms and not resolution.get("blocked"):
                    log("  PASS 3 completó todos los huecos resolubles")
                    break

    rec.evidence_graph = dict(rec.evidence_graph or {})
    rec.evidence_graph["resolution_audit"] = resolution
    rec.missing_fields = [row["semantic"] for row in resolution.get("fields", []) if row.get("status") == "INSUFFICIENT_EVIDENCE"]
    for issue in resolution.get("cross_field_issues", []):
        rec.warnings.append(f"cross_field:{issue.get('code')}")
    if resolution.get("blocked"):
        rec.warnings.append("final_material_conflict_after_targeted_research")

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", item.identity.mpn or item.identity.ean or item.identity.model or f"row_{item.row}")
    (Path(out_dir) / f"{stem}.json").write_text(rec.model_dump_json(indent=2), encoding="utf-8")
    return rec


def run_batch(
    template: str,
    output_dir: str,
    overwrite: bool = False,
    log=lambda m: None,
    manual_part_numbers: list[str] | None = None,
    manual_identities: list[ProductIdentity] | None = None,
    manual_source_urls: list[list[str]] | None = None,
    source_strategy: SourceStrategy | None = None,
) -> dict:
    strategy = (source_strategy or SourceStrategy()).normalized()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    template_plan = analyze_template_contract(template)
    (out / "template_contract.json").write_text(json.dumps(template_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    ps = template_plan["summary"]
    log(
        f"Contrato Excel: {ps['fields_total']} campos | {ps['scrape_targets']} datos de producto | "
        f"{ps['media_slots']} imágenes | {ps['seller_inputs']} datos del vendedor | "
        f"{ps['marketplace_inputs']} datos marketplace"
    )
    log(
        "Fuentes ejecución: "
        f"WEB={'ON' if strategy.web else 'OFF'} | PDF={'ON' if strategy.pdf else 'OFF'} | "
        f"OCR={'ON' if strategy.ocr else 'OFF'} | MISTRAL={'ON' if strategy.mistral else 'OFF'}"
    )

    manual_mode = bool(manual_identities or manual_part_numbers)
    if manual_identities:
        items = manual_identity_items(template, manual_identities, manual_source_urls)
    elif manual_part_numbers:
        items = manual_items(template, manual_part_numbers)
    else:
        items = detect_items(template)
    log(f"Productos a procesar: {len(items)}" + (" (entradas manuales: MPN/EAN/UPC/GTIN/nombre)" if manual_mode else " (detectados en Excel)"))

    records: list[ProductRecord] = []
    row_assignments: dict[tuple[str, int], ProductRecord] = {}
    failures: list[dict] = []
    for index, item in enumerate(items, 1):
        label = item.identity.mpn or item.identity.ean or item.identity.model or item.identity.product_name
        log(f"[{index}/{len(items)}] {label}")
        rec = scrape_item(
            item,
            str(out / "json"),
            template_plan=template_plan,
            log=log,
            source_strategy=strategy,
        )
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
        [],
        overwrite=overwrite,
        trace_path=trace,
        row_assignments=row_assignments,
    )
    resolution_summary = {
        str(item.identity.mpn or item.identity.ean or item.identity.model or item.identity.product_name):
        (row_assignments[(item.sheet, item.row)].evidence_graph or {}).get("resolution_audit", {})
        for item in items if (item.sheet, item.row) in row_assignments
    }
    resolution_file = out / "resolucion_campos.json"
    resolution_file.write_text(json.dumps(resolution_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    source_validation_summary = {
        "validated_sources": sum(int((rec.fetch or {}).get("validated_sources", 1) or 1) for rec in records),
        "manufacturer_sources": sum(int((rec.fetch or {}).get("manufacturer_sources", 1 if (rec.fetch or {}).get("source_class") == "manufacturer" else 0) or 0) for rec in records),
        "material_evidence": sum(len(rec.evidence or []) for rec in records),
        "final_specifications": sum(len(rec.specifications or {}) for rec in records),
    }
    summary = {
        "mode": "manual_product_identity" if manual_mode else "excel_detected",
        "source_strategy": strategy.as_options(),
        "template_contract": template_plan["summary"],
        "template_contract_file": str(out / "template_contract.json"),
        "products_detected": len(items),
        "products_scraped": len(records),
        "products_failed": len(failures),
        "failures": failures,
        "source_validation": source_validation_summary,
        "output_excel": output_xlsx,
        "trace": trace,
        "resolution": str(resolution_file),
        "mapping": report.get("summary", {}),
    }
    (out / "resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary