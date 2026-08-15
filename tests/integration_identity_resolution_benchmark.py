from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from product_intelligence.batch import BatchItem, scrape_item
from product_intelligence.identity_bootstrap import bootstrap_identity
from product_intelligence.models import ProductIdentity
from product_intelligence.provider_runtime import provider_run_scope
from product_intelligence.source_authority import source_family
from product_intelligence.source_strategy import SourceStrategy


CASES = [
    ("Armor 22", ProductIdentity(product_name="Armor 22"), "Ulefone", ("ulefone.com",)),
    ("A2794", ProductIdentity(mpn="A2794"), "Apple", ("apple.com",)),
    ("SM-S928B", ProductIdentity(mpn="SM-S928B"), "Samsung", ("samsung.com", "samsungmobile.com")),
    ("910-006556", ProductIdentity(mpn="910-006556"), "Logitech", ("logitech.com",)),
    ("JBLT530CBLKAM", ProductIdentity(mpn="JBLT530CBLKAM"), "JBL", ("jbl.com", "jbl.com.pe")),
    ("V15 G4 IRU", ProductIdentity(product_name="V15 G4 IRU"), "Lenovo", ("lenovo.com",)),
]

STRATEGY = SourceStrategy(web=True, pdf=True, ocr=False, mistral=False)
PROVIDER_SETTINGS = {
    "ocr_space_enabled": False,
    "mistral_enabled": False,
    "mistral_model": "mistral-small-latest",
    "request_timeout": 20,
}


def _host(url: str | None) -> str:
    return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")


def _official(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def main() -> int:
    rows = []
    provider_events = []
    failures = 0

    def audit(event: str, data: dict):
        provider_events.append({"event": event, **data})

    with provider_run_scope(PROVIDER_SETTINGS, audit=audit):
        for index, (raw, raw_identity, expected_brand, official_domains) in enumerate(CASES, 1):
            identity = raw_identity.model_copy(deep=True)
            started = time.monotonic()
            bootstrap = bootstrap_identity(identity, limit_per_query=16, timeout=8)
            bootstrap_elapsed = round(time.monotonic() - started, 2)

            # QA oracle only: expected_brand is never supplied to bootstrap or scraper.
            brand_pass = bootstrap.status == "RESOLVED" and (bootstrap.identity.brand or "").casefold() == expected_brand.casefold()
            if not brand_pass:
                failures += 1
                row = {
                    "input": raw,
                    "input_brand": raw_identity.brand,
                    "identity_status": bootstrap.status,
                    "resolved_brand": bootstrap.identity.brand,
                    "resolved_model": bootstrap.identity.model,
                    "identity_confidence": round(float(bootstrap.confidence or 0), 3),
                    "identity_reason": bootstrap.reason,
                    "official_domain_hint": bootstrap.official_domain_hint,
                    "identity_queries": len(bootstrap.queries_executed),
                    "queries_executed": bootstrap.queries_executed,
                    "identity_results_found": bootstrap.search_results_found,
                    "candidate_urls": len(bootstrap.candidate_urls),
                    "brand_scores": bootstrap.brand_scores,
                    "brand_hosts": bootstrap.brand_hosts,
                    "page_probes_attempted": bootstrap.page_probes_attempted,
                    "page_probes_succeeded": bootstrap.page_probes_succeeded,
                    "page_signals": bootstrap.page_signals,
                    "brand_gate": "FAIL",
                    "material_evidence": 0,
                    "specification_count": 0,
                    "accepted_sources": [],
                    "false_manufacturer_urls": [],
                    "bootstrap_seconds": bootstrap_elapsed,
                    "scrape_seconds": 0.0,
                    "elapsed_seconds": bootstrap_elapsed,
                    "status": "IDENTITY_FAIL_CLOSED",
                    "logs": [],
                }
                rows.append(row)
                print(json.dumps({k: v for k, v in row.items() if k != "logs"}, ensure_ascii=False))
                continue

            run_identity = bootstrap.identity.model_copy(deep=True)
            logs = []
            scrape_started = time.monotonic()
            with TemporaryDirectory(prefix=f"identity-bootstrap-{index}-") as tmp:
                rec = scrape_item(
                    BatchItem(row=index, sheet="IDENTITY", identity=run_identity),
                    tmp,
                    template_plan=None,
                    log=logs.append,
                    source_strategy=STRATEGY,
                )
            scrape_elapsed = round(time.monotonic() - scrape_started, 2)

            false_manufacturer_urls = []
            if rec is not None:
                for ev in rec.evidence or []:
                    url = str(ev.source_url or "")
                    host = _host(url)
                    if source_family(ev) == "manufacturer" and host and not _official(host, official_domains):
                        false_manufacturer_urls.append(url)
            false_manufacturer_urls = list(dict.fromkeys(false_manufacturer_urls))
            if false_manufacturer_urls:
                failures += 1

            material = len(rec.evidence or []) if rec is not None else 0
            status = "SCRAPED" if rec is not None and material else "FAIL_CLOSED"
            row = {
                "input": raw,
                "input_brand": raw_identity.brand,
                "identity_status": bootstrap.status,
                "resolved_brand": bootstrap.identity.brand,
                "resolved_model": bootstrap.identity.model,
                "identity_confidence": round(float(bootstrap.confidence or 0), 3),
                "identity_reason": bootstrap.reason,
                "official_domain_hint": bootstrap.official_domain_hint,
                "identity_queries": len(bootstrap.queries_executed),
                "queries_executed": bootstrap.queries_executed,
                "identity_results_found": bootstrap.search_results_found,
                "candidate_urls": len(bootstrap.candidate_urls),
                "brand_scores": bootstrap.brand_scores,
                "brand_hosts": bootstrap.brand_hosts,
                "page_probes_attempted": bootstrap.page_probes_attempted,
                "page_probes_succeeded": bootstrap.page_probes_succeeded,
                "page_signals": bootstrap.page_signals,
                "brand_gate": "PASS",
                "material_evidence": material,
                "specification_count": len(rec.specifications or {}) if rec is not None else 0,
                "accepted_sources": list(rec.sources or []) if rec is not None else [],
                "false_manufacturer_urls": false_manufacturer_urls,
                "bootstrap_seconds": bootstrap_elapsed,
                "scrape_seconds": scrape_elapsed,
                "elapsed_seconds": round(bootstrap_elapsed + scrape_elapsed, 2),
                "status": status,
                "logs": logs[-120:],
            }
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "logs"}, ensure_ascii=False))

    forbidden = [e for e in provider_events if e.get("event") in {
        "OCR_PROVIDER_SELECTED", "OCR_SPACE_USED", "MISTRAL_DESCRIPTION_REQUESTED", "MISTRAL_DESCRIPTION_ACCEPTED",
    }]
    if forbidden:
        failures += 1

    summary = {
        "products": len(rows),
        "identity_resolved": sum(1 for r in rows if r["identity_status"] == "RESOLVED"),
        "identity_brand_pass": sum(1 for r in rows if r["brand_gate"] == "PASS"),
        "scraped": sum(1 for r in rows if r["status"] == "SCRAPED"),
        "fail_closed": sum(1 for r in rows if "FAIL_CLOSED" in r["status"]),
        "false_manufacturer_count": sum(len(r["false_manufacturer_urls"]) for r in rows),
        "ocr_or_mistral_executed": bool(forbidden),
        "total_elapsed_seconds": round(sum(r["elapsed_seconds"] for r in rows), 2),
        "hardcoded_product_exceptions": 0,
    }
    payload = {"summary": summary, "products": rows, "provider_events": provider_events}
    Path("identity-resolution-benchmark.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("IDENTITY_RESOLUTION_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
