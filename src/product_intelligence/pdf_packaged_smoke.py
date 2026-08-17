from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Iterable

from .part_number_pdf_search import search_product_pdfs_by_part_number


REPORT_FILENAME = "pdf-packaged-smoke.json"
QUERY_LIMIT = 8


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "product").strip()) or "product"


def validate_physical_pdf_paths(paths: Iterable[str | Path]) -> list[str]:
    """Return absolute PDF paths or fail if any reported evidence is not physically present."""
    resolved: list[str] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"physical_pdf_invalid_suffix:{path}")
        if not path.is_file():
            raise ValueError(f"physical_pdf_missing:{path}")
        resolved.append(str(path.resolve()))
    if not resolved:
        raise ValueError("physical_pdf_missing_all")
    return resolved


def build_smoke_report(*, output_dir: str | Path, products: list[dict]) -> dict:
    status = "PASS" if products and all(str(item.get("status") or "") == "PASS" for item in products) else "FAIL"
    return {
        "schema_version": 1,
        "status": status,
        "output_dir": str(Path(output_dir).resolve()),
        "products": products,
    }


def _identity_payload(result) -> dict:
    resolved = result.resolved
    identity = resolved.identity
    return {
        "brand": identity.brand,
        "model": identity.model or identity.product_name,
        "mpn": identity.mpn,
        "ean": identity.ean,
        "upc": identity.upc,
        "gtin": identity.gtin,
        "official_domain": resolved.official_domain,
        "status": resolved.status,
        "confidence": resolved.confidence,
    }


def run_product_smoke(part_number: str, output_dir: str | Path, *, timeout: int = 10) -> dict:
    """Run the production P60 entrypoint once and certify its retained physical PDFs."""
    part = str(part_number or "").strip()
    if not part:
        return {
            "part_number": part,
            "status": "FAIL",
            "query_count": 0,
            "query_limit": QUERY_LIMIT,
            "validated_count": 0,
            "physical_pdf_paths": [],
            "error": "part_number_required",
        }

    root = Path(output_dir).resolve()
    cache_dir = root / "pdf_evidence" / _safe_identifier(part)
    cache_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    logs: list[str] = []

    try:
        result = search_product_pdfs_by_part_number(
            part,
            cache_dir,
            limit=QUERY_LIMIT,
            timeout=max(1, int(timeout)),
            log=logs.append,
            on_event=events.append,
        )
        query_events = [event for event in events if str(event.get("type") or "") == "query"]
        queries = [str(event.get("query") or "") for event in query_events]
        query_count = len(query_events)
        accepted_paths = [str(row.inspection.local_path) for row in result.candidates]
        physical_paths = validate_physical_pdf_paths(accepted_paths)
        accepted_urls = [str(row.inspection.final_url or row.candidate.url or "") for row in result.candidates]

        failures: list[str] = []
        if query_count > QUERY_LIMIT:
            failures.append(f"query_budget_exceeded:{query_count}>{QUERY_LIMIT}")
        if result.validated_count < 1:
            failures.append("validated_pdf_required")
        if len(physical_paths) != int(result.validated_count):
            failures.append(
                f"physical_pdf_count_mismatch:{len(physical_paths)}!={int(result.validated_count)}"
            )

        payload = {
            "part_number": part,
            "status": "FAIL" if failures else "PASS",
            "identity": _identity_payload(result),
            "query_count": query_count,
            "query_limit": QUERY_LIMIT,
            "queries": queries,
            "discovered_count": int(result.discovered_count),
            "downloaded_count": int(result.downloaded_count),
            "validated_count": int(result.validated_count),
            "rejected_count": int(result.rejected_count),
            "duplicate_count": int(result.duplicate_count),
            "page_limit_rejected_count": int(result.page_limit_rejected_count),
            "accepted_urls": accepted_urls,
            "physical_pdf_paths": physical_paths,
            "cache_dir": str(cache_dir),
        }
        if failures:
            payload["error"] = ";".join(failures)
        return payload
    except Exception as exc:
        query_events = [event for event in events if str(event.get("type") or "") == "query"]
        return {
            "part_number": part,
            "status": "FAIL",
            "query_count": len(query_events),
            "query_limit": QUERY_LIMIT,
            "queries": [str(event.get("query") or "") for event in query_events],
            "validated_count": 0,
            "physical_pdf_paths": [],
            "cache_dir": str(cache_dir),
            "error": f"{type(exc).__name__}:{exc}",
            "log_tail": logs[-40:],
        }


def run_packaged_pdf_smoke(
    output_dir: str | Path,
    part_numbers: Iterable[str],
    *,
    timeout: int = 10,
) -> dict:
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    products = [run_product_smoke(part, root, timeout=timeout) for part in part_numbers]
    report = build_smoke_report(output_dir=root, products=products)
    report_path = root / REPORT_FILENAME
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Certify packaged P60 PDF execution and retained physical PDFs.")
    parser.add_argument("output_dir", help="Directory where PDF evidence and the JSON report will be retained.")
    parser.add_argument("part_numbers", nargs="+", help="One or more product identifiers/part numbers to certify.")
    parser.add_argument("--timeout", type=int, default=10, help="Per-network-operation timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = run_packaged_pdf_smoke(args.output_dir, args.part_numbers, timeout=max(1, args.timeout))
    return 0 if report.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
