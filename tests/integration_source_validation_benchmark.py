from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from product_intelligence.batch import BatchItem, scrape_item
from product_intelligence.identity_gate import ObservedIdentity, assess_identity
from product_intelligence.models import ProductIdentity
from product_intelligence.normalize import key_norm
from product_intelligence.provider_runtime import provider_run_scope
from product_intelligence.source_authority import source_family
from product_intelligence.source_strategy import SourceStrategy


REGRESSION6 = [
    ("audio", ProductIdentity(brand="JBL", model="Tune 530C", mpn="JBLT530CBLKAM"), ("jbl.com", "jbl.com.pe")),
    ("mouse", ProductIdentity(brand="Logitech", model="MX Master 3S", mpn="910-006556"), ("logitech.com",)),
    ("cable", ProductIdentity(brand="Apple", model="240W USB-C Charge Cable", mpn="A2794"), ("apple.com",)),
    ("smartphone", ProductIdentity(brand="Samsung", model="Galaxy S24 Ultra", mpn="SM-S928B"), ("samsung.com", "samsungmobile.com")),
    ("laptop", ProductIdentity(brand="Lenovo", model="V15 G4 IRU"), ("lenovo.com",)),
    ("rugged_phone", ProductIdentity(brand="Ulefone", model="Armor 22"), ("ulefone.com",)),
]

TEN_BRAND = REGRESSION6 + [
    ("ssd", ProductIdentity(brand="Kingston", model="NV2 1TB", mpn="SNV2S/1000G"), ("kingston.com",)),
    ("networking", ProductIdentity(brand="TP-Link", model="Archer AX55"), ("tp-link.com",)),
    ("monitor", ProductIdentity(brand="Dell", model="P2422H"), ("dell.com",)),
    ("printer", ProductIdentity(brand="Brother", model="HL-L2460DW"), ("brother.com",)),
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


def _is_official_host(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _evidence_observed_identity(rec) -> ObservedIdentity:
    models: list[str] = []
    names: list[str] = []
    brands: list[str] = []
    mpns: list[str] = []
    gtins: list[str] = []
    eans: list[str] = []
    upcs: list[str] = []
    for ev in rec.evidence or []:
        attr = key_norm(str(ev.attribute or ""))
        value = str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value or "").strip()
        if not value:
            continue
        if attr in {"model", "modelo"}:
            models.append(value)
        elif attr in {"name", "product name", "nombre", "nombre producto"}:
            names.append(value)
        elif attr in {"brand", "marca"}:
            brands.append(value)
        elif attr in {"mpn", "manufacturer part number", "part number"}:
            mpns.append(value)
        elif attr in {"gtin", "gtin14"}:
            gtins.append(value)
        elif attr in {"ean", "gtin13"}:
            eans.append(value)
        elif attr in {"upc", "gtin12"}:
            upcs.append(value)
    return ObservedIdentity(
        brand=brands[0] if brands else None,
        model=models[0] if models else None,
        product_name=names[0] if names else None,
        mpns=tuple(dict.fromkeys(mpns)),
        gtins=tuple(dict.fromkeys(gtins)),
        eans=tuple(dict.fromkeys(eans)),
        upcs=tuple(dict.fromkeys(upcs)),
    )


def _known_non_material_url(url: str | None) -> bool:
    path = (urlparse(str(url or "")).path or "").lower()
    return any(token in path for token in (
        "/privacy", "/terms", "/cookies", "/legal", "/search", "/login", "/account", "/signin",
        "/software-update", "/firmware-update", "/release-notes", "/update/",
    ))


def _explicit_failure(logs: list[str]) -> bool:
    joined = "\n".join(logs)
    useful_markers = (
        "SOURCE_VALIDATION_REJECTED",
        "PDF_SEARCH",
        "PDF CANDIDATOS",
        "PDF VALIDADO",
        "Fuente no accesible",
        "PDF rechazado por identidad",
        "identificadores en conflicto",
        "fuente exacta contiene el identificador",
        "HTTP ",
    )
    return any(marker in joined for marker in useful_markers)


def run_set(name: str) -> dict:
    corpus = REGRESSION6 if name == "regression6" else TEN_BRAND
    provider_events: list[dict] = []
    rows: list[dict] = []

    def audit(event: str, data: dict):
        provider_events.append({"event": event, **data})

    contamination = 0
    false_manufacturer = 0
    non_material_evidence = 0
    useful_or_explicit = 0

    with provider_run_scope(PROVIDER_SETTINGS, audit=audit):
        for index, (category, identity, official_domains) in enumerate(corpus, 1):
            label = identity.mpn or identity.model or identity.product_name or f"product-{index}"
            logs: list[str] = []
            started = time.monotonic()
            try:
                with TemporaryDirectory(prefix=f"source-validation-{index}-") as tmp:
                    rec = scrape_item(
                        BatchItem(row=index, sheet="BENCHMARK", identity=identity),
                        tmp,
                        template_plan=None,
                        log=logs.append,
                        source_strategy=STRATEGY,
                    )
                elapsed = round(time.monotonic() - started, 2)
                if rec is None:
                    explicit = _explicit_failure(logs)
                    if explicit:
                        useful_or_explicit += 1
                    rows.append({
                        "category": category,
                        "brand": identity.brand,
                        "label": label,
                        "status": "FAIL_CLOSED" if explicit else "NO_RESULT",
                        "elapsed_seconds": elapsed,
                        "material_evidence": 0,
                        "explicit_reason": explicit,
                        "logs": logs[-80:],
                    })
                    continue

                material_evidence = len(rec.evidence or [])
                if material_evidence > 0:
                    useful_or_explicit += 1

                observed = _evidence_observed_identity(rec)
                has_observed_identity = any([
                    observed.brand, observed.model, observed.product_name,
                    observed.mpns, observed.gtins, observed.eans, observed.upcs,
                ])
                identity_assessment = assess_identity(identity, observed) if has_observed_identity else None
                contaminated = bool(identity_assessment and identity_assessment.status == "CONFLICT")
                if contaminated:
                    contamination += 1

                false_mfg_urls: list[str] = []
                non_material_urls: list[str] = []
                for ev in rec.evidence or []:
                    url = str(ev.source_url or "")
                    host = _host(url)
                    if source_family(ev) == "manufacturer" and host and not _is_official_host(host, official_domains):
                        false_mfg_urls.append(url)
                    if _known_non_material_url(url):
                        non_material_urls.append(url)
                false_mfg_urls = list(dict.fromkeys(false_mfg_urls))
                non_material_urls = list(dict.fromkeys(non_material_urls))
                false_manufacturer += len(false_mfg_urls)
                non_material_evidence += len(non_material_urls)

                rows.append({
                    "category": category,
                    "brand": identity.brand,
                    "label": label,
                    "status": "SCRAPED",
                    "elapsed_seconds": elapsed,
                    "material_evidence": material_evidence,
                    "specification_count": len(rec.specifications or {}),
                    "source_count": len(set(rec.sources or [])),
                    "resolved_identity": rec.identity.model_dump(),
                    "observed_identity_assessment": (
                        {
                            "status": identity_assessment.status,
                            "confidence": identity_assessment.confidence,
                            "reasons": list(identity_assessment.reasons),
                        }
                        if identity_assessment else None
                    ),
                    "contaminated": contaminated,
                    "false_manufacturer_urls": false_mfg_urls,
                    "non_material_evidence_urls": non_material_urls,
                    "sources": rec.sources,
                    "warnings": rec.warnings,
                    "logs": logs[-100:],
                })
            except Exception as exc:
                explicit = True
                useful_or_explicit += 1
                rows.append({
                    "category": category,
                    "brand": identity.brand,
                    "label": label,
                    "status": "ERROR_FAIL_CLOSED",
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "material_evidence": 0,
                    "explicit_reason": explicit,
                    "error": f"{type(exc).__name__}: {exc}",
                    "logs": logs[-100:],
                })

    forbidden_events = [event for event in provider_events if event.get("event") in {
        "OCR_PROVIDER_SELECTED", "OCR_SPACE_USED", "MISTRAL_DESCRIPTION_REQUESTED", "MISTRAL_DESCRIPTION_ACCEPTED",
    }]
    coverage_ratio = useful_or_explicit / len(corpus) if corpus else 0.0
    summary = {
        "set": name,
        "strategy": STRATEGY.as_options(),
        "products": len(corpus),
        "scraped": sum(1 for row in rows if row["status"] == "SCRAPED"),
        "fail_closed": sum(1 for row in rows if "FAIL_CLOSED" in row["status"]),
        "no_result": sum(1 for row in rows if row["status"] == "NO_RESULT"),
        "cross_product_contamination_count": contamination,
        "false_manufacturer_count": false_manufacturer,
        "non_material_evidence_count": non_material_evidence,
        "useful_or_explicit_count": useful_or_explicit,
        "useful_or_explicit_ratio": round(coverage_ratio, 3),
        "ocr_or_mistral_executed": bool(forbidden_events),
        "forbidden_provider_events": forbidden_events,
        "total_elapsed_seconds": round(sum(float(row.get("elapsed_seconds", 0)) for row in rows), 2),
    }
    payload = {"summary": summary, "products": rows, "provider_events": provider_events}
    Path("source-validation-benchmark.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SOURCE_VALIDATION_SUMMARY=" + json.dumps(summary, ensure_ascii=False))
    for row in rows:
        print(json.dumps({k: v for k, v in row.items() if k != "logs"}, ensure_ascii=False))

    hard_fail = (
        bool(forbidden_events)
        or contamination != 0
        or false_manufacturer != 0
        or non_material_evidence != 0
        or coverage_ratio < 0.80
    )
    return {"exit_code": 1 if hard_fail else 0, **payload}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=("regression6", "ten_brand"), default="regression6")
    args = parser.parse_args()
    result = run_set(args.set)
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
