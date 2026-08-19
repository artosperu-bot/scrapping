from pathlib import Path

PATH = Path("src/product_intelligence/price_workflow.py")
text = PATH.read_text(encoding="utf-8")

import_anchor = "from .price_source_capabilities import SourceCapabilityRegistry, detect_ecommerce_platform\n"
import_replacement = import_anchor + "from .product_classification import classify_product\n"
if "from .product_classification import classify_product\n" not in text:
    if import_anchor not in text:
        raise SystemExit("P8 patch abort: capability import anchor missing")
    text = text.replace(import_anchor, import_replacement, 1)

collector_anchor = "\ndef _remember_source_capability(registry, url: str, html: str, rows: list[PriceOffer], identity: ProductIdentity, discovery_method: str | None, *, success: bool) -> None:\n"
collector = r'''
def _collect_direct_source_offers(
    capabilities: list[dict],
    identity: ProductIdentity,
    emit,
    *,
    trace: PriceCoverageTrace | None = None,
    capability_registry: SourceCapabilityRegistry | None = None,
) -> list[PriceOffer]:
    """Freshly query proven source-native capabilities without cached product answers."""
    capabilities = [dict(row) for row in capabilities if row.get("domain") and row.get("direct_method")]
    if not capabilities:
        return []

    category = classify_product(identity).category

    def worker(capability: dict) -> list[PriceOffer]:
        domain = str(capability.get("domain") or "").strip().casefold().removeprefix("www.")
        method = str(capability.get("direct_method") or "").strip()
        platform = str(capability.get("platform") or "").strip() or None
        base_url = f"https://{domain}"
        channel = _channel_from_url(base_url)
        if trace:
            trace.record(channel, "FETCH_STARTED", url=base_url)
        emit(
            "source",
            channel=channel,
            domain=domain,
            status="fetching",
            method=method,
            recovery_method="DIRECT_SOURCE",
        )
        try:
            if method == "vtex_catalog":
                found = _try_vtex(base_url, identity, channel, timeout=10)
            else:
                found = []
            found = dedupe_offers(found)
            extraction = next((str(row.source_method or "").strip() for row in found if str(row.source_method or "").strip()), method or None)
            if capability_registry is not None:
                capability_registry.record(
                    domain,
                    platform=platform,
                    discovery_method=f"direct_{method}" if method else "direct_source",
                    extraction_method=extraction,
                    price_capable=True if found else None,
                    stock_capable=True if any(row.stock is not None or bool(row.availability) for row in found) else None,
                    seller_capable=True if any(bool(row.seller_display_name or row.seller_legal_name or row.seller_tax_id) for row in found) else None,
                    success=bool(found),
                    category=category,
                )
            if trace:
                trace.record(channel, "FETCH_OK", url=base_url)
                trace.record(channel, "IDENTITY_ACCEPTED" if found else "PARSER_ZERO_OFFERS", url=base_url)
            emit(
                "source",
                channel=channel,
                domain=domain,
                status="ok",
                offers=len(found),
                method=method,
                recovery_method="DIRECT_SOURCE",
            )
            return found
        except Exception as exc:
            if capability_registry is not None:
                try:
                    capability_registry.record(
                        domain,
                        platform=platform,
                        discovery_method=f"direct_{method}" if method else "direct_source",
                        success=False,
                        category=category,
                    )
                except Exception:
                    pass
            if trace:
                trace.record(channel, "FETCH_BLOCKED", url=base_url, detail=type(exc).__name__)
            emit(
                "source",
                channel=channel,
                domain=domain,
                status="error",
                method=method,
                recovery_method="DIRECT_SOURCE",
                terminal="DIRECT_SOURCE_FAILED",
                error=f"{type(exc).__name__}: {exc}",
            )
            return []

    rows: list[PriceOffer] = []
    workers = max(1, min(4, len(capabilities)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="price-direct-source") as pool:
        futures = [pool.submit(worker, capability) for capability in capabilities]
        for future in as_completed(futures):
            try:
                rows.extend(future.result())
            except Exception:
                # Worker already isolates expected source errors; this is a final
                # safety boundary so one source can never block the other lanes.
                continue
    return dedupe_offers(rows)

'''
if "def _collect_direct_source_offers(" not in text:
    if collector_anchor not in text:
        raise SystemExit("P8 patch abort: direct collector anchor missing")
    text = text.replace(collector_anchor, "\n" + collector + collector_anchor.lstrip("\n"), 1)

old_category = '            category=getattr(identity, "category", None),\n'
new_category = '            category=classify_product(identity).category,\n'
if old_category in text:
    text = text.replace(old_category, new_category, 1)
elif new_category not in text:
    raise SystemExit("P8 patch abort: category learning anchor missing")

lane_anchor = "    offers: list[PriceOffer] = []\n    learned_sources = load_validated_source_urls(output_root, identity)\n"
lane_replacement = '''    offers: list[PriceOffer] = []
    structured_domains = tuple(
        (urlparse(base_url).hostname or "").casefold().removeprefix("www.")
        for _channel, base_url in PERU_STRUCTURED_SOURCES
    )
    direct_capabilities = capability_registry.direct_candidates(
        working_identity,
        limit=max(1, min(8, max_sources // 6 or 1)),
        exclude_domains=structured_domains,
    )
    if direct_capabilities:
        emit(
            "source_routing",
            recovery_method="DIRECT_SOURCE",
            candidates=len(direct_capabilities),
            domains=[row.get("domain") for row in direct_capabilities],
        )
        offers.extend(_collect_direct_source_offers(
            direct_capabilities,
            working_identity,
            emit,
            trace=trace,
            capability_registry=capability_registry,
        ))
    learned_sources = load_validated_source_urls(output_root, identity)
'''
if "direct_capabilities = capability_registry.direct_candidates(" not in text:
    if lane_anchor not in text:
        raise SystemExit("P8 patch abort: run lane anchor missing")
    text = text.replace(lane_anchor, lane_replacement, 1)

PATH.write_text(text, encoding="utf-8")
print("P8_ACTIVE_SOURCE_ROUTING_PATCH=APPLIED")
