from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from product_intelligence.models import ProductIdentity
from product_intelligence.price_identity import competitor_key
from product_intelligence.price_workflow import run_price_product


BENCHMARK_DOMAINS = {
    "falabella.com.pe": "Falabella",
    "ripley.com.pe": "Ripley",
    "mercadolibre.com.pe": "Mercado Libre",
    "coolbox.pe": "Coolbox",
    "oechsle.pe": "Oechsle",
    "sodimac.com.pe": "Sodimac",
    "plazavea.com.pe": "Plaza Vea",
    "promart.pe": "Promart",
    "hiraoka.com.pe": "Hiraoka",
    "supertec.com.pe": "Supertec",
    "memorykings.pe": "Memory Kings",
    "impacto.com.pe": "Impacto",
    "baetech.pe": "BaeTech",
    "ntperu.com": "NTPeru",
    "gidat.pe": "Gidat",
    "computerhouse.pe": "Computer House",
    "unikstore.com.pe": "UnikStore",
    "famtec.pe": "Famtec",
    "compumarket.pe": "Compumarket",
    "sercoplus.com": "Sercoplus",
    "corporacionluana.pe": "Corporación Luana",
    "eac.com.pe": "EAC",
    "arteus.pe": "Arteus",
}
BENCHMARK_SOURCES = list(dict.fromkeys(BENCHMARK_DOMAINS.values()))
STATIC_STRUCTURED = {"Falabella", "Plaza Vea", "Oechsle"}


def host(value: str | None) -> str:
    return (urlparse(str(value or "")).hostname or "").casefold().removeprefix("www.")


def benchmark_for_host(value: str | None) -> str | None:
    hostname = host(value)
    if not hostname:
        return None
    for domain, source in BENCHMARK_DOMAINS.items():
        if hostname == domain or hostname.endswith("." + domain):
            return source
    return None


def benchmark_for_domain(value: str | None) -> str | None:
    raw = str(value or "").casefold().removeprefix("www.").strip(" /")
    if not raw:
        return None
    for domain, source in BENCHMARK_DOMAINS.items():
        if raw == domain or raw.endswith("." + domain):
            return source
    return None


def audit_capability_seed(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("P8 seed must be a source capability object")
    rendered = json.dumps(data, ensure_ascii=False).casefold()
    forbidden = ("sa400s37", "kingston", "https://", "http://", "/producto/", "/product/")
    leaked = [token for token in forbidden if token in rendered]
    if leaked:
        raise SystemExit(f"P8 seed contains product/PDP-specific material: {leaked}")
    for domain, row in data.items():
        if not isinstance(row, dict) or str(row.get("domain") or domain).casefold() != str(domain).casefold():
            raise SystemExit(f"Invalid source capability row: {domain}")
    return data


def status_table(offers, events):
    statuses = {source: "MISS" for source in BENCHMARK_SOURCES}
    methods = {source: set() for source in BENCHMARK_SOURCES}

    for source in STATIC_STRUCTURED:
        methods[source].add("STRUCTURED_API")
    methods["Mercado Libre"].add("MARKETPLACE_API")

    for event in events:
        if event.get("type") == "source_routing" and event.get("recovery_method") == "DIRECT_SOURCE":
            for domain in event.get("domains") or []:
                source = benchmark_for_domain(domain)
                if source:
                    methods[source].add("DIRECT_SOURCE")
        if event.get("type") == "source":
            source = benchmark_for_domain(event.get("domain"))
            if not source:
                channel = str(event.get("channel") or "").casefold().replace(" ", "")
                for candidate in BENCHMARK_SOURCES:
                    if candidate.casefold().replace(" ", "") == channel:
                        source = candidate
                        break
            if not source:
                continue
            if event.get("recovery_method") == "DIRECT_SOURCE":
                methods[source].add("DIRECT_SOURCE")
                if event.get("status") == "error":
                    statuses[source] = "DIRECT_SOURCE_FAILED"
                elif event.get("status") == "ok" and not event.get("offers") and statuses[source] == "MISS":
                    statuses[source] = "DIRECT_SOURCE_ZERO_OFFERS"
            elif event.get("method") == "structured_direct":
                methods[source].add("STRUCTURED_API")
                if event.get("status") == "error":
                    statuses[source] = "STRUCTURED_ACCESS_ERROR"
                elif event.get("status") == "ok" and not event.get("offers") and statuses[source] == "MISS":
                    statuses[source] = "STRUCTURED_ZERO_OFFERS"
            if event.get("terminal"):
                statuses[source] = str(event["terminal"])
        elif event.get("type") == "page":
            source = benchmark_for_host(event.get("url"))
            if not source:
                continue
            methods[source].add("OPEN_PROVIDER")
            if event.get("status") == "error":
                statuses[source] = "DISCOVERED_FETCH_ERROR"
            elif event.get("status") == "parsed" and not event.get("offers") and statuses[source] in {"MISS", "DISCOVERED_FETCH_ERROR"}:
                statuses[source] = "DISCOVERED_ZERO_OFFERS"

    for row in offers:
        source = benchmark_for_host(row.url)
        if source:
            statuses[source] = "OFFER"
            if not methods[source]:
                methods[source].add("OPEN_PROVIDER")

    recovery = {}
    for source, values in methods.items():
        if not values:
            recovery[source] = "NONE"
        elif len(values) == 1:
            recovery[source] = next(iter(values))
        else:
            recovery[source] = "MULTIPLE:" + "+".join(sorted(values))
    return statuses, recovery


def run(label: str, output: Path, seed_capabilities: Path | None, report_path: Path) -> dict:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    seed_domains = []
    if seed_capabilities is not None:
        seed = audit_capability_seed(seed_capabilities)
        seed_domains = sorted(seed)
        target = output / "price_intelligence" / "source_capabilities.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed_capabilities, target)
        # Critical P8 invariant: only capability memory is present at run start.
        for forbidden_name in ("source_bindings.json", "latest.json", "history.jsonl", "sellers.json", "channel_coverage.json"):
            assert not (target.parent / forbidden_name).exists(), forbidden_name

    identity = ProductIdentity(mpn="SA400S37/960G")
    raw = identity.model_dump()
    assert raw["mpn"] == "SA400S37/960G"
    assert all(value in (None, "", [], 0, 0.0, "LOW") for key, value in raw.items() if key != "mpn"), raw

    events = []
    started = time.monotonic()
    # Deliberately use the production default source budget. Reproducibility must
    # come from routing intelligence, not a larger search allowance.
    offers = run_price_product(identity, output, on_event=lambda event: events.append(dict(event)))
    runtime = round(time.monotonic() - started, 3)

    statuses, recovery = status_table(offers, events)
    accepted_sources = sorted({source for row in offers if (source := benchmark_for_host(row.url))})
    semantic_sources = sorted(source for source, status in statuses.items() if status != "MISS")
    offer_hosts = sorted({host(row.url) for row in offers if host(row.url)})
    sellers = sorted({competitor_key(row) for row in offers if competitor_key(row)})

    query_requests = sum(1 for event in events if event.get("type") == "query")
    page_fetch_operations = sum(1 for event in events if event.get("type") == "page" and event.get("status") == "fetching")
    direct_fetch_operations = sum(
        1 for event in events
        if event.get("type") == "source" and event.get("recovery_method") == "DIRECT_SOURCE" and event.get("status") == "fetching"
    )
    structured_fetch_operations = sum(
        1 for event in events
        if event.get("type") == "source" and event.get("method") == "structured_direct" and event.get("status") in {"ok", "error"}
    )
    logical_network_requests = query_requests + page_fetch_operations + direct_fetch_operations + structured_fetch_operations

    report = {
        "label": label,
        "input_identity": raw,
        "memory_mode": "COLD_EMPTY" if seed_capabilities is None else "WARM_SOURCE_CAPABILITY_ONLY",
        "seed_domains": seed_domains,
        "runtime_seconds": runtime,
        "offers": [row.to_dict() for row in offers],
        "offer_count": len(offers),
        "accepted_benchmark_sources": accepted_sources,
        "accepted_benchmark_count": len(accepted_sources),
        "semantic_benchmark_sources": semantic_sources,
        "semantic_benchmark_count": len(semantic_sources),
        "unique_store_hosts": offer_hosts,
        "unique_store_count": len(offer_hosts),
        "unique_seller_count": len(sellers),
        "query_requests": query_requests,
        "page_fetch_operations": page_fetch_operations,
        "direct_fetch_operations": direct_fetch_operations,
        "structured_fetch_operations": structured_fetch_operations,
        "logical_network_requests": logical_network_requests,
        "request_metric_note": "logical high-level engine operations, not raw browser subrequests",
        "source_status": statuses,
        "source_recovery_method": recovery,
        "direct_source_candidates": [
            domain
            for event in events
            if event.get("type") == "source_routing" and event.get("recovery_method") == "DIRECT_SOURCE"
            for domain in (event.get("domains") or [])
        ],
        "direct_source_successes": sorted({
            benchmark_for_domain(event.get("domain")) or str(event.get("domain") or "")
            for event in events
            if event.get("type") == "source"
            and event.get("recovery_method") == "DIRECT_SOURCE"
            and event.get("status") == "ok"
            and int(event.get("offers") or 0) > 0
        }),
        "events": events,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"events", "offers", "source_status", "source_recovery_method"}}, ensure_ascii=False, indent=2))
    print("SOURCE_STATUS=" + json.dumps(statuses, ensure_ascii=False, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--seed-capabilities", type=Path)
    args = parser.parse_args()
    run(args.label, args.output, args.seed_capabilities, args.report)


if __name__ == "__main__":
    main()
