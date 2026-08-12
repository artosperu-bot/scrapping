from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .models import ProductIdentity, ProductRecord, Evidence
from .identity import compare_identity
from .html_extract import extract_page, identity_from_page, table_evidence, structured_evidence
from .pdf_extract import extract_pdf
from .record_builder import build_record_strict
from .source_policy import classify_source
from .web_fetch import fetch_page, fetch_browser
from .note_extract import extract_technical_notes
from .text_extract import extract_text_evidence
from .source_extract import source_evidence
from .media_discovery import discover_media, build_site_profile
from .evidence_graph import build_evidence_graph
from .target_extract import extract_target_evidence


ACCEPTABLE_MEDIA_SCOPES = {"EXACT_VARIANT", "EXACT_PRODUCT"}


class ProductPipeline:
    def process_url(
        self,
        expected: ProductIdentity,
        url: str,
        official_domain: str | None = None,
        include_pdfs: bool = True,
        include_images: bool = True,
        browser_fallback: bool = True,
        target_semantics: list[str] | None = None,
        media_slots: int = 0,
    ) -> ProductRecord:
        # Fast identity preflight first. A rich Chromium pass is expensive and should run
        # only after this URL has proved that it is the requested product.
        fetch = fetch_page(url, browser_fallback=browser_fallback)
        if fetch.status_code >= 400:
            raise ValueError(f"Fuente no accesible: HTTP {fetch.status_code} ({fetch.method}). No se intenta eludir controles del sitio.")

        terms = [expected.brand, expected.product_name, expected.model, expected.mpn, expected.ean, expected.upc, expected.gtin, expected.capacity, expected.variant, expected.color]
        page = extract_page(fetch.html, fetch.final_url, [x for x in terms if x])
        candidate = identity_from_page(page, expected=expected, source_url=fetch.final_url)
        source_class = classify_source(fetch.final_url, official_domain)
        # On a validated manufacturer page, schema.org Product.sku is a strong variant identifier.
        # When the user supplied an MPN and the page exposes only SKU, compare them rather than silently
        # copying the expected MPN into the candidate. This catches regional/color variant mismatches.
        if source_class == "manufacturer" and expected.mpn and not candidate.mpn and candidate.sku:
            candidate.mpn = candidate.sku
        candidate = compare_identity(expected, candidate)

        has_strong_target = any([expected.mpn, expected.ean, expected.upc, expected.gtin])
        required = {
            "manufacturer": ({"EXACT"} if has_strong_target else {"EXACT", "HIGH"}),
            "secondary": {"EXACT"},
            "marketplace": {"EXACT"},
        }[source_class]
        if candidate.match_level not in required:
            raise ValueError(
                f"Fuente rechazada: clase={source_class}, identidad={candidate.match_level}, "
                f"confirmados={candidate.identifiers_confirmed}, conflictos={candidate.identifiers_conflicting}"
            )

        # Once identity is proven, enrich the same public product page with a normal browser
        # when the Excel asks for a gallery. This activates lazy-loaded images and captures
        # JSON/XHR/media without spending Chromium time on rejected search candidates.
        if media_slots > 1 and fetch.method != "playwright":
            try:
                rich = fetch_browser(fetch.final_url, timeout=45, activate_lazy_media=True)
                if rich.status_code and rich.status_code < 400:
                    fetch = rich
                    page = extract_page(fetch.html, fetch.final_url, [x for x in terms if x])
                    rich_candidate = identity_from_page(page, expected=expected, source_url=fetch.final_url)
                    if source_class == "manufacturer" and expected.mpn and not rich_candidate.mpn and rich_candidate.sku:
                        rich_candidate.mpn = rich_candidate.sku
                    rich_candidate = compare_identity(expected, rich_candidate)
                    if rich_candidate.match_level in required:
                        candidate = rich_candidate
            except Exception as exc:
                fetch.warnings.append(f"validated_browser_enrichment_failed:{type(exc).__name__}")

        for field in ["brand", "manufacturer", "product_name", "model", "mpn", "sku", "ean", "upc", "gtin", "variant", "capacity", "color", "region"]:
            if getattr(candidate, field, None) is None and getattr(expected, field, None) is not None:
                setattr(candidate, field, getattr(expected, field))

        base = .985 if candidate.match_level == "EXACT" else .92
        if source_class != "manufacturer":
            base = min(base, .82)
        html_type = "official_html" if source_class == "manufacturer" else f"{source_class}_html"
        evidence = table_evidence(fetch.html, fetch.final_url, candidate.match_level, base, source_type=html_type)
        evidence += structured_evidence(page, fetch.final_url, candidate.match_level, min(.99, base + .02), html_type)
        evidence += extract_text_evidence(page.get("text", ""), fetch.final_url, html_type, candidate.match_level, max(.60, base-.08), expected_capacity=candidate.capacity or expected.capacity)
        evidence += extract_target_evidence(
            page.get("text", ""), target_semantics, fetch.final_url, html_type,
            candidate.match_level, max(.60, base-.06),
        )

        # Raw source / "view-source + Ctrl+F" layer. This runs only AFTER identity validation,
        # so hidden JSON/config/data-* values can enrich specs without letting a search redirect,
        # query-string echo or unrelated page establish product identity.
        if source_class == "manufacturer":
            evidence += source_evidence(
                fetch.html,
                fetch.final_url,
                candidate,
                candidate.match_level,
                min(.94, base - .015),
            )

        from .media_discovery import validate_resource_identity
        for response in fetch.json_responses[:30]:
            from .structured_extract import flatten_pairs
            try:
                import json as _json
                preview=_json.dumps(response.get("data"),ensure_ascii=False)[:120000]
            except Exception:
                preview=str(response.get("data"))[:120000]
            rscope, rconf, _rev, _rconflicts = validate_resource_identity(
                response.get("url") or fetch.final_url, candidate,
                found_on_validated_product_page=True, surrounding_text=preview,
            )
            if rscope not in {"EXACT_VARIANT","EXACT_PRODUCT"} or _rconflicts:
                continue
            for path, value in flatten_pairs(response.get("data"), max_depth=4):
                leaf = path.split(".")[-1]
                if len(leaf) > 2 and len(str(value)) <= 300:
                    evidence.append(Evidence(
                        attribute=leaf, raw_value=value, normalized_value=value,
                        source_url=response.get("url"), source_type=f"{source_class}_xhr_json",
                        selector=f"json:{path}", match_level=candidate.match_level,
                        confidence=max(.58, min(base - .02, rconf)),
                    ))

        sources = [fetch.final_url]
        pdf_notes=[]
        if include_pdfs and source_class == "manufacturer":
            for pdf in page["pdfs"][:12]:
                try:
                    pdf_text, ev = extract_pdf(pdf, candidate.match_level, min(base, .96))
                    pscope, pconf, _pev, pconflicts = validate_resource_identity(
                        pdf, candidate, found_on_validated_product_page=True, surrounding_text=pdf_text[:160000]
                    )
                    if pscope not in {"EXACT_VARIANT","EXACT_PRODUCT"} or pconflicts:
                        continue
                    # Cap PDF evidence confidence by resource-identity confidence.
                    for _e in ev:
                        _e.confidence=min(float(_e.confidence or 0),float(pconf))
                    evidence.extend(ev)
                    evidence.extend(extract_text_evidence(pdf_text, pdf, "official_pdf", candidate.match_level, min(base,.95,pconf), expected_capacity=candidate.capacity or expected.capacity))
                    evidence.extend(extract_target_evidence(
                        pdf_text, target_semantics, pdf, "official_pdf", candidate.match_level, min(base,.94,pconf)
                    ))
                    pdf_notes.extend(extract_technical_notes(pdf_text,pdf))
                    sources.append(pdf)
                except Exception:
                    continue

        rec = build_record_strict(candidate, evidence, sources)

        # General media discovery: resource provenance + identity scope.
        media = discover_media(
            fetch.html,
            fetch.final_url,
            candidate,
            network_resources=fetch.network_resources,
            page_is_validated=True,
        )
        for _m in media:
            _m["source_class"] = source_class
            _m["source_page"] = fetch.final_url
        rec.media = media
        # Excel-safe default: only exact product/variant media is auto-fill eligible.
        rec.images = [m for m in media if include_images and m.get("media_type") == "image" and m.get("scope") in ACCEPTABLE_MEDIA_SCOPES and m.get("confidence",0) >= .80 and m.get("autofill_eligible")]
        rec.videos = [m for m in media if m.get("media_type") == "video" and m.get("scope") in ACCEPTABLE_MEDIA_SCOPES and m.get("confidence",0) >= .80 and m.get("autofill_eligible")]
        rec.site_profile = build_site_profile(fetch.final_url, media, fetch.json_responses)
        rec.technical_notes = extract_technical_notes(page.get("text", ""), fetch.final_url) + pdf_notes
        rec.fetch = {
            "method": fetch.method,
            "status_code": fetch.status_code,
            "final_url": fetch.final_url,
            "source_class": source_class,
            "json_responses_captured": len(fetch.json_responses),
            "network_resources_captured": len(fetch.network_resources),
            "raw_source_evidence": sum(1 for e in rec.evidence if e.source_type == "official_source_html"),
            "target_semantics_requested": list(target_semantics or []),
            "media_slots_requested": int(media_slots or 0),
        }
        rec.warnings.extend(fetch.warnings)
        unverified = sum(1 for m in media if m.get("scope") == "UNVERIFIED")
        if unverified:
            rec.warnings.append(f"media_unverified_not_autofilled:{unverified}")
        family_only = sum(1 for m in media if m.get("scope") == "PRODUCT_FAMILY")
        if family_only:
            rec.warnings.append(f"family_media_not_autofilled:{family_only}")
        if source_class != "manufacturer":
            rec.warnings.append("secondary_source: technical values accepted only after EXACT identity validation")

        rejected_audit = (rec.evidence_graph or {}).get("rejected_evidence", [])
        rec.evidence_graph = build_evidence_graph(
            rec.identity.model_dump(),
            rec.sources,
            [e.model_dump() for e in rec.evidence],
            rec.media,
        )
        if rejected_audit:
            rec.evidence_graph["rejected_evidence"] = rejected_audit
        return rec

    def process_official_url(self, expected: ProductIdentity, url: str, include_pdfs: bool = True) -> ProductRecord:
        domain = (urlparse(url).hostname or "").removeprefix("www.")
        return self.process_url(expected, url, official_domain=domain, include_pdfs=include_pdfs)

    @staticmethod
    def save_json(record: ProductRecord, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(record.model_dump_json(indent=2), encoding="utf-8")
