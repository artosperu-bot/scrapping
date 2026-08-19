from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    warm = [row for row in reports if str(row.get("label", "")).startswith("warm")]
    if len(warm) != 3:
        raise SystemExit(f"Expected exactly 3 warm reports, got {len(warm)}")

    source_names = list(warm[0]["source_status"])
    accepted_frequency = {
        source: sum(source in row["accepted_benchmark_sources"] for row in warm)
        for source in source_names
    }
    semantic_frequency = {
        source: sum(row["source_status"].get(source, "MISS") != "MISS" for row in warm)
        for source in source_names
    }
    buckets = {str(count): sorted(source for source, hits in accepted_frequency.items() if hits == count) for count in range(4)}
    semantic_buckets = {str(count): sorted(source for source, hits in semantic_frequency.items() if hits == count) for count in range(4)}

    pairs = []
    for left, right in combinations(warm, 2):
        accepted_left = set(left["accepted_benchmark_sources"])
        accepted_right = set(right["accepted_benchmark_sources"])
        semantic_left = set(left["semantic_benchmark_sources"])
        semantic_right = set(right["semantic_benchmark_sources"])
        pairs.append({
            "runs": [left["label"], right["label"]],
            "accepted_jaccard": round(jaccard(accepted_left, accepted_right), 4),
            "semantic_jaccard": round(jaccard(semantic_left, semantic_right), 4),
        })

    accepted_counts = [row["accepted_benchmark_count"] for row in warm]
    semantic_counts = [row["semantic_benchmark_count"] for row in warm]
    provider_only = set()
    direct_source = set()
    marketplace_api = set()
    mixed = set()
    for row in warm:
        for source in row["accepted_benchmark_sources"]:
            route = str(row["source_recovery_method"].get(source, "NONE"))
            if route.startswith("MULTIPLE"):
                mixed.add(source)
            elif route == "DIRECT_SOURCE":
                direct_source.add(source)
            elif route in {"MARKETPLACE_API", "STRUCTURED_API"}:
                marketplace_api.add(source)
            elif route == "OPEN_PROVIDER":
                provider_only.add(source)

    # Never double-count a source into provider-only when another run proved a
    # provider-independent lane for the same source.
    provider_only -= direct_source | marketplace_api | mixed

    summary = {
        "cold": next((row for row in reports if row.get("label") == "cold"), None),
        "warm_runs": [{
            "label": row["label"],
            "accepted": row["accepted_benchmark_count"],
            "semantic": row["semantic_benchmark_count"],
            "stores": row["unique_store_count"],
            "sellers": row["unique_seller_count"],
            "runtime_seconds": row["runtime_seconds"],
            "logical_network_requests": row["logical_network_requests"],
            "query_requests": row["query_requests"],
            "direct_fetch_operations": row["direct_fetch_operations"],
            "accepted_sources": row["accepted_benchmark_sources"],
            "semantic_sources": row["semantic_benchmark_sources"],
            "direct_source_candidates": row["direct_source_candidates"],
            "direct_source_successes": row["direct_source_successes"],
        } for row in warm],
        "accepted_hit_frequency": accepted_frequency,
        "accepted_frequency_buckets": buckets,
        "semantic_hit_frequency": semantic_frequency,
        "semantic_frequency_buckets": semantic_buckets,
        "jaccard_pairs": pairs,
        "accepted_worst": min(accepted_counts),
        "accepted_median": sorted(accepted_counts)[1],
        "accepted_best": max(accepted_counts),
        "semantic_worst": min(semantic_counts),
        "semantic_median": sorted(semantic_counts)[1],
        "semantic_best": max(semantic_counts),
        "provider_independence": {
            "provider_only": sorted(provider_only),
            "direct_source": sorted(direct_source),
            "marketplace_or_structured_api": sorted(marketplace_api),
            "mixed": sorted(mixed),
            "provider_only_count": len(provider_only),
            "direct_source_count": len(direct_source),
            "marketplace_or_structured_api_count": len(marketplace_api),
            "mixed_count": len(mixed),
        },
        "previous_single_run_accepted_baseline": 7,
        "p7_cumulative_accepted_reference": 13,
        "p7_cumulative_semantic_reference": 18,
        "strong_stability_worst_not_below_previous_baseline": min(accepted_counts) >= 7,
        "median_moves_toward_p7_cumulative": sorted(accepted_counts)[1] > 7,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
