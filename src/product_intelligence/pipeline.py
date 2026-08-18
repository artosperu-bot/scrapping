from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .models import ProductIdentity, ProductRecord, Evidence
from .identity import compare_identity
from .html_extract import extract_page, identity_from_page, table_evidence, structured_evidence
from .pdf_extract import download_bytes, extract_pdf_bytes
from .pdf_document_preflight import extract_verified_pdf_bytes
from .record_builder import build_record_strict
from .source_policy import classify_source
from .web_fetch import fetch_page, fetch_browser
from .note_extract import extract_technical_notes
from .text_extract import extract_text_evidence
from .source_extract import source_evidence
from .media_discovery import discover_media, build_site_profile
from .evidence_graph import build_evidence_graph
from .target_extract import extract_target_evidence
from .extraction_strategy import browser_decision, extraction_plan
from .page_type import classify_page_type
from .identity_gate import assess_identity
from .source_authority import classify_source_authority
from .source_signals import derive_observed_identity, derive_page_signals, derive_authority_signals
from .evidence_policy import decide_evidence


ACCEPTABLE_MEDIA_SCOPES = {"EXACT_VARIANT", "EXACT_PRODUCT"}


def _policy_method(ev: Evidence) -> str:
    source_type = str(ev.source_type or "").lower()
    selector = str(ev.selector or "").lower()
    if "pdf" in source_type:
        return "pdf_native"
    if "json" in source_type or selector.startswith("embedded:") or selector.startswith("json:"):
        return "jsonld"
    if selector in {"line_prefix", "next_line", "target_next_line"}:
        return "clean_dom"
    return "clean_dom"


def _source_decision_dict(page_assessment, identity_assessment, authority_assessment) -> dict:
    return {
        "page_type": page_assessment.page_type,
        "page_type_confidence": page_assessment.confidence,
        "page_type_reasons": list(page_assessment.reasons),
        "material_allowed": bool(page_assessment.material_allowed),
        "identity": identity_assessment.status,
        "identity_confidence": identity_assessment.confidence,
        "identity_reasons": list(identity_assessment.reasons),
        "identity_matched": list(identity_assessment.matched_identifiers),
        "identity_conflicts": list(identity_assessment.conflicting_identifiers),
        "authority": authority_assessment.source_class,
        "authority_confidence": authority_assessment.confidence,
        "authority_reasons": list(authority_assessment.reasons),
    }


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
        fetch = fetch_page(url, browser_fallback=browser_fallback)
        if fetch.status_code >= 400:
            raise ValueError(f"Fuente no accesible: HTTP {fetch.status_code} ({fetch.method}). No se intenta eludir controles del sitio.")

        terms = [expected.brand, expected.product_name, expected.model, expected.mpn, expected.ean, expected.upc, expected.gtin, expected.capacity, expected.variant, expected.color]
        page = extract_page(fetch.html, fetch.final_url, [x for x in terms if x])

        # NEW: admission is based on what the page actually says, before requested values are
        # copied into the candidate for downstream compatibility.
        observed = derive_observed_identity(expected, page)
        page_assessment = classify_page_type(derive_page_signals(fetch.html, fetch.final_url, page))
        identity_assessment = assess_identity(expected, observed)
        authority_assessment = classify_source_authority(
            derive_authority_signals(expected, fetch.html, fetch.final_url, page)
        )
        source_decision = _source_decision_dict(page_assessment, identity_assessment, authority_assessment)

        if not page_assessment.material_allowed:
            raise ValueError(
                f"SOURCE_VALIDATION_REJECTED: PAGE_TYPE_NOT_MATERIAL page_type={page_assessment.page_type} "
                f"identity={identity_assessment.status} authority={authority_assessment.source_class}"
            )
        if identity_assessment.status in {"CONFLICT", "AMBIGUOUS", "INSUFFICIENT"}:
            reason = "IDENTITY_CONFLICT" if identity_assessment.status == "CONFLICT" else "IDENTITY_NOT_STRONG_ENOUGH"
            raise ValueError(
                f"SOURCE_VALIDATION_REJECTED: {reason} identity={identity_assessment.status} "
                f"reasons={','.join(identity_assessment.reasons)}"
            )

        candidate = identity_from_page(page, expected=expected, source_url=fetch.final_url)

        # Legacy source classification remains as a weak routing hint only. A caller-supplied
        # official_domain can no longer manufacture authority by itself.
        legacy_source_class = classify_source(fetch.final_url, official_domain)
        if authority_assessment.source_class in {"manufacturer", "manufacturer_support"}:
            source_class = "manufacturer"
        elif legacy_source_class == "marketplace" or authority_assessment.source_class == "marketplace":
            source_class = "marketplace"
        else:
            source_class = "secondary"

        if source_class == "manufacturer" and expected.mpn and not candidate.mpn and candidate.sku:
            candidate.mpn = candidate.sku
        candidate = compare_identity(expected, candidate)

        # Existing comparison remains a secondary safety net, but the new observed-identity gate
        # above is the load-bearing admission check.
        if candidate.identifiers_conflicting:
            raise ValueError(
                f"SOURCE_VALIDATION_REJECTED: LEGACY_IDENTIFIER_CONFLICT conflicts={candidate.identifiers_conflicting}"
            )

        decision = browser_decision(fetch.html, target_semantics, media_slots)
        if fetch.method == "playwright":
            browser_reason = "browser_used_by_initial_fetch"
        else:
            browser_reason = decision.reason
        if browser_fallback and decision.needed and fetch.method != "playwright":
            try:
                rich = fetch_browser(
                    fetch.final_url,
                    timeout=45,
                    activate_lazy_media=bool(int(media_slots or 0) > 1),
                )
                if rich.status_code and rich.status_code < 400:
                    rich_page = extract_page(rich.html, rich.final_url, [x for x in terms if x])
                    rich_observed = derive_observed_identity(expected, rich_page)
                    rich_page_assessment = classify_page_type(derive_page_signals(rich.html, rich.final_url, rich_page))
                    rich_identity_assessment = assess_identity(expected, rich_observed)
                    rich_authority = classify_source_authority(
                        derive_authority_signals(expected, rich.html, rich.final_url, rich_page)
                    )
                    if rich_page_assessment.material_allowed and rich_identity_assessment.status in {"EXACT", "COMPATIBLE"}:
                        rich_candidate = identity_from_page(rich_page, expected=expected, source_url=rich.final_url)
                        if rich_authority.source_class in {"manufacturer", "manufacturer_support"} and expected.mpn and not rich_candidate.mpn and rich_candidate.sku:
                            rich_candidate.mpn = rich_candidate.sku
                        rich_candidate = compare_identity(expected, rich_candidate)
                        if not rich_candidate.identifiers_conflicting:
                            fetch = rich
                            page = rich_page
                            candidate = rich_candidate
                            page_assessment = rich_page_assessment
                            identity_assessment = rich_identity_assessment
                            authority_assessment = rich_authority
                            source_decision = _source_decision_dict(page_assessment, identity_assessment, authority_assessment)
                            if authority_assessment.source_class in {"manufacturer", "manufacturer_support"}:
                                source_class = "manufacturer"
                            elif authority_assessment.source_class == "marketplace":
                                source_class = "marketplace"
                            else:
                                source_class = "secondary"
                            browser_reason = decision.reason
                        else:
                            fetch.warnings.append("rendered_identity_revalidation_failed")
                    else:
                        fetch.warnings.append("rendered_source_validation_failed")
            except Exception as exc:
                fetch.warnings.append(f"validated_browser_enrichment_failed:{type(exc).__name__}")

        # Requested values may now be copied only after the observed source passed the identity gate.
        for field in ["brand", "manufacturer", "product_name", "model", "mpn", "sku", "ean", "upc", "gtin", "variant", "capacity", "color", "region"]:
            if getattr(candidate, field, None) is None and getattr(expected, field, None) is not None:
                setattr(candidate, field, getattr(expected, field))

        base = .985 if identity_assessment.status == "EXACT" else .90
        if source_class != "manufacturer":
            base = min(base, .82)
        html_type = "official_html" if source_class == "manufacturer" else f"{source_class}_html"

        evidence = structured_evidence(page, fetch.final_url, candidate.match_level, min(.99, base + .02), html_type)
        evidence += table_evidence(fetch.html, fetch.final_url, candidate.match_level, base, source_type=html_type)
        evidence += extract_target_evidence(
            page.get("text", ""), target_semantics, fetch.final_url, html_type,
            candidate.match_level, max(.60, base-.06),
        )
        evidence += extract_text_evidence(page.get("text", ""), fetch.final_url, html_type, candidate.match_level, max(.60, base-.08), expected_capacity=candidate.capacity or expected.capacity)

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
                preview = _json.dumps(response.get("data"), ensure_ascii=False)[:120000]
            except Exception:
                preview = str(response.get("data"))[:120000]
            rscope, rconf, _rev, _rconflicts = validate_resource_identity(
                response.get("url") or fetch.final_url, candidate,
                found_on_validated_product_page=True, surrounding_text=preview,
            )
            if rscope not in {"EXACT_VARIANT", "EXACT_PRODUCT"} or _rconflicts:
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
        pdf_notes = []
        followed_document_pages = 0
        followed_pdfs = 0

        def _bind_pdf_evidence(items, match, confidence_cap: float) -> list[Evidence]:
            bound: list[Evidence] = []
            for ev in list(items or []):
                ev.confidence = min(float(ev.confidence or 0), float(confidence_cap))
                ev.document_relationship = match.relationship
                ev.document_scope = match.document_scope
                ev.hard_conflicts = list(match.hard_conflicts)
                ev.positive_evidence = list(match.positive_evidence)
                ev.negative_evidence = list(match.negative_evidence)
                bound.append(ev)
            return bound

        def consume_pdf(pdf_url: str, parent_source_url: str | None = None):
            nonlocal followed_pdfs
            try:
                # Download once. The first pass reads native text/metadata only and
                # cannot invoke OCR. Full extraction is enabled only after the exact
                # product-document relationship is accepted.
                data = download_bytes(pdf_url)
                verified = extract_verified_pdf_bytes(
                    candidate,
                    data,
                    pdf_url,
                    full_extract=extract_pdf_bytes,
                    match_level=candidate.match_level,
                    confidence=min(base, .96),
                    parent_source_url=parent_source_url or fetch.final_url,
                    focus_terms=target_semantics,
                )
                if not verified.accepted:
                    return

                pdf_text = verified.text
                match = verified.match
                pconf = float(match.confidence)
                ev = _bind_pdf_evidence(verified.evidence, match, pconf)
                evidence.extend(ev)

                target_ev = extract_target_evidence(
                    pdf_text, target_semantics, pdf_url, "official_pdf", candidate.match_level, min(base, .94, pconf)
                )
                text_ev = extract_text_evidence(
                    pdf_text, pdf_url, "official_pdf", candidate.match_level, min(base, .95, pconf),
                    expected_capacity=candidate.capacity or expected.capacity,
                )
                evidence.extend(_bind_pdf_evidence(target_ev, match, pconf))
                evidence.extend(_bind_pdf_evidence(text_ev, match, pconf))
                pdf_notes.extend(extract_technical_notes(pdf_text, pdf_url))
                if pdf_url not in sources:
                    sources.append(pdf_url)
                followed_pdfs += 1
            except Exception:
                return

        if include_pdfs and source_class == "manufacturer":
            seen_pdfs = set()
            for pdf in page.get("pdfs", [])[:12]:
                if pdf not in seen_pdfs:
                    seen_pdfs.add(pdf)
                    consume_pdf(pdf, fetch.final_url)

            base_host = (urlparse(fetch.final_url).hostname or "").lower().removeprefix("www.")
            for doc_url in page.get("document_links", [])[:6]:
                try:
                    doc_host = (urlparse(doc_url).hostname or "").lower().removeprefix("www.")
                    if not doc_host or not (doc_host == base_host or doc_host.endswith("." + base_host) or base_host.endswith("." + doc_host)):
                        continue
                    doc_fetch = fetch_page(doc_url, browser_fallback=False)
                    if doc_fetch.status_code >= 400:
                        continue
                    doc_page = extract_page(doc_fetch.html, doc_fetch.final_url, [x for x in terms if x])
                    doc_page_assessment = classify_page_type(derive_page_signals(doc_fetch.html, doc_fetch.final_url, doc_page))
                    doc_observed = derive_observed_identity(expected, doc_page)
                    doc_identity_assessment = assess_identity(expected, doc_observed)
                    if doc_page_assessment.page_type not in {"SUPPORT_PRODUCT", "PRODUCT", "PRODUCT_VARIANT"}:
                        continue
                    if doc_identity_assessment.status not in {"EXACT", "COMPATIBLE"}:
                        continue
                    followed_document_pages += 1
                    sources.append(doc_fetch.final_url)
                    doc_level = "EXACT" if doc_identity_assessment.status == "EXACT" else "HIGH"
                    doc_conf = min(.94, base)
                    evidence.extend(structured_evidence(doc_page, doc_fetch.final_url, doc_level, doc_conf, "official_support_html"))
                    evidence.extend(table_evidence(doc_fetch.html, doc_fetch.final_url, doc_level, doc_conf, source_type="official_support_html"))
                    evidence.extend(extract_target_evidence(doc_page.get("text", ""), target_semantics, doc_fetch.final_url, "official_support_html", doc_level, min(.92, doc_conf)))
                    evidence.extend(extract_text_evidence(doc_page.get("text", ""), doc_fetch.final_url, "official_support_html", doc_level, min(.92, doc_conf), expected_capacity=candidate.capacity or expected.capacity))
                    for pdf in doc_page.get("pdfs", [])[:12]:
                        if pdf not in seen_pdfs:
                            seen_pdfs.add(pdf)
                            consume_pdf(pdf, doc_fetch.final_url)
                except Exception:
                    continue

        # Final evidence admission is fail-closed. Page and identity are common to the source;
        # extraction method/semantic/confidence are fact-specific.
        policy_accepted: list[Evidence] = []
        policy_rejected: list[dict] = []
        for ev in evidence:
            ev_source_class = authority_assessment.source_class
            if "pdf" in str(ev.source_type or "").lower() and source_class == "manufacturer":
                ev_source_class = "official_pdf"
            policy = decide_evidence(
                page_type=page_assessment.page_type,
                identity_status=identity_assessment.status,
                source_class=ev_source_class,
                extraction_method=_policy_method(ev),
                semantic=ev.attribute,
                confidence=float(ev.confidence or 0.0),
            )
            ev.identity_status = identity_assessment.status
            ev.authority = ev_source_class
            ev.policy_allowed = bool(policy.allowed)
            if policy.allowed:
                policy_accepted.append(ev)
            else:
                policy_rejected.append({
                    "attribute": ev.attribute,
                    "value": ev.raw_value,
                    "source": ev.source_url,
                    "reason": policy.reason,
                })
        evidence = policy_accepted

        rec = build_record_strict(candidate, evidence, sources)

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
        rec.images = [m for m in media if include_images and m.get("media_type") == "image" and m.get("scope") in ACCEPTABLE_MEDIA_SCOPES and m.get("confidence", 0) >= .80 and m.get("autofill_eligible")]
        rec.videos = [m for m in media if m.get("media_type") == "video" and m.get("scope") in ACCEPTABLE_MEDIA_SCOPES and m.get("confidence", 0) >= .80 and m.get("autofill_eligible")]
        rec.site_profile = build_site_profile(fetch.final_url, media, fetch.json_responses)
        rec.technical_notes = extract_technical_notes(page.get("text", ""), fetch.final_url) + pdf_notes
        rec.fetch = {
            "method": fetch.method,
            "status_code": fetch.status_code,
            "final_url": fetch.final_url,
            "source_class": source_class,
            "source_decision": source_decision,
            "json_responses_captured": len(fetch.json_responses),
            "network_resources_captured": len(fetch.network_resources),
            "raw_source_evidence": sum(1 for e in rec.evidence if e.source_type == "official_source_html"),
            "official_document_pages_followed": followed_document_pages,
            "official_pdfs_followed": followed_pdfs,
            "target_semantics_requested": list(target_semantics or []),
            "media_slots_requested": int(media_slots or 0),
            "extraction_order": extraction_plan(),
            "browser_enrichment": {
                "used": fetch.method == "playwright",
                "reason": browser_reason,
                "static_target_hits": decision.target_hits,
                "target_total": decision.target_total,
            },
        }
        rec.warnings.extend(fetch.warnings)
        unverified = sum(1 for m in media if m.get("scope") == "UNVERIFIED")
        if unverified:
            rec.warnings.append(f"media_unverified_not_autofilled:{unverified}")
        family_only = sum(1 for m in media if m.get("scope") == "PRODUCT_FAMILY")
        if family_only:
            rec.warnings.append(f"family_media_not_autofilled:{family_only}")
        if source_class != "manufacturer":
            rec.warnings.append("secondary_source: technical values accepted only after source validation")

        rejected_audit = (rec.evidence_graph or {}).get("rejected_evidence", [])
        rec.evidence_graph = build_evidence_graph(
            rec.identity.model_dump(),
            rec.sources,
            [e.model_dump() for e in rec.evidence],
            rec.media,
        )
        combined_rejected = list(rejected_audit) + policy_rejected
        if combined_rejected:
            rec.evidence_graph["rejected_evidence"] = combined_rejected[:500]
        rec.evidence_graph["source_decision"] = source_decision
        rec.evidence_graph["source_validation_counts"] = {
            "policy_evidence_accepted": len(policy_accepted),
            "policy_evidence_rejected": len(policy_rejected),
        }
        return rec

    def process_official_url(self, expected: ProductIdentity, url: str, include_pdfs: bool = True) -> ProductRecord:
        domain = (urlparse(url).hostname or "").removeprefix("www.")
        return self.process_url(expected, url, official_domain=domain, include_pdfs=include_pdfs)

    @staticmethod
    def save_json(record: ProductRecord, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(record.model_dump_json(indent=2), encoding="utf-8")