from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .price_channel_registry import TARGET_CHANNELS, build_channel_coverage, target_spec_for_name, target_spec_for_url
from .price_models import PriceOffer


FAILURE_STAGE = {
    "NOT_SEARCHED": "DISCOVERY_NOT_TARGETED",
    "QUERY_EXECUTED_NO_RESULT": "DISCOVERY",
    "URL_REJECTED_BY_RANKING": "RANKING",
    "URL_REJECTED_BY_DOMAIN": "DOMAIN_FILTER",
    "URL_DISCOVERED": "POST_DISCOVERY",
    "FETCH_BLOCKED": "ACCESS",
    "FETCH_TIMEOUT": "ACCESS",
    "FETCH_FAILED": "ACCESS",
    "ML_API_AUTH_FAILED": "AUTH",
    "PARSER_ZERO_OFFERS": "PARSER_EXTRACTION",
    "IDENTITY_REJECTED": "IDENTITY",
    "PRICE_NOT_FOUND": "PRICE_EXTRACTION",
    "PRICE_REJECTED": "PRICE_VALIDATION",
}

SEARCH_STAGES = {
    "QUERY_GENERATED", "QUERY_EXECUTED", "QUERY_EXECUTED_NO_RESULT", "RAW_RESULT_FOUND",
    "URL_REJECTED_BY_RANKING", "URL_REJECTED_BY_DOMAIN", "URL_DISCOVERED", "FETCH_STARTED",
    "FETCH_OK", "FETCH_BLOCKED", "FETCH_TIMEOUT", "FETCH_FAILED", "PARSER_STARTED", "PARSER_OK",
    "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED", "IDENTITY_REJECTED", "PRICE_EXTRACTED",
    "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED", "ML_API_AUTH_FAILED",
}
FETCHED_STAGES = {
    "FETCH_OK", "PARSER_STARTED", "PARSER_OK", "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED",
    "IDENTITY_REJECTED", "PRICE_EXTRACTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK",
    "OFFER_ACCEPTED", "OFFER_DEDUPED",
}
PARSED_STAGES = {
    "PARSER_OK", "PARSER_ZERO_OFFERS", "IDENTITY_ACCEPTED", "IDENTITY_REJECTED", "PRICE_EXTRACTED",
    "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED",
}
IDENTITY_ACCEPTED_STAGES = {
    "IDENTITY_ACCEPTED", "PRICE_EXTRACTED", "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK",
    "OFFER_ACCEPTED", "OFFER_DEDUPED",
}
PRICE_STAGES = {"PRICE_EXTRACTED", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED"}


def _key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _canonical_channel(channel: str | None, url: str | None = None) -> str:
    spec = target_spec_for_name(channel) or (target_spec_for_url(str(url or "")) if url else None)
    if spec:
        return spec.label
    return str(channel or "").strip()


def _offer_matches_channel(offer: PriceOffer, channel: str) -> bool:
    spec = target_spec_for_name(offer.channel) or target_spec_for_url(offer.url)
    if spec:
        return spec.label == channel
    return _key(offer.channel) == _key(channel)


class PriceTrace:
    """Append-only Price Intelligence diagnostics; observing never changes engine decisions."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._sequence = 0

    def record(self, stage: str, **payload: Any) -> dict[str, Any]:
        normalized = str(stage or "").strip().upper()
        if not normalized:
            raise ValueError("stage is required")
        self._sequence += 1
        row = {"seq": self._sequence, "stage": normalized, **payload}
        self.events.append(row)
        return row

    def funnel(self) -> dict[str, int]:
        stage_counts: dict[str, int] = defaultdict(int)
        unique_urls: dict[str, set[str]] = defaultdict(set)
        for event in self.events:
            stage = str(event.get("stage") or "")
            stage_counts[stage] += 1
            url = str(event.get("url") or "").strip()
            if url:
                unique_urls[stage].add(url)
        return {
            "queries": stage_counts["QUERY_EXECUTED"],
            "raw_results": stage_counts["RAW_RESULT_FOUND"],
            "urls_discovered": len(unique_urls["URL_DISCOVERED"]),
            "urls_fetched": len(unique_urls["FETCH_OK"]),
            "fetch_blocked": len(unique_urls["FETCH_BLOCKED"]),
            "fetch_timeouts": len(unique_urls["FETCH_TIMEOUT"]),
            "parser_zero_offers": stage_counts["PARSER_ZERO_OFFERS"],
            "identity_accepted": stage_counts["IDENTITY_ACCEPTED"],
            "identity_rejected": stage_counts["IDENTITY_REJECTED"],
            "prices_extracted": stage_counts["PRICE_EXTRACTED"],
            "prices_rejected": stage_counts["PRICE_REJECTED"],
            "offers_accepted": stage_counts["OFFER_ACCEPTED"],
            "offers_deduped": stage_counts["OFFER_DEDUPED"],
        }

    def query_report(self) -> list[dict[str, Any]]:
        return [dict(event) for event in self.events if event.get("stage") in {"QUERY_GENERATED", "QUERY_EXECUTED", "QUERY_EXECUTED_NO_RESULT"}]

    def coverage(self, offers: Iterable[PriceOffer]) -> dict[str, Any]:
        offer_list = list(offers)
        legacy = build_channel_coverage(offer_list)
        observed_names = {
            _canonical_channel(event.get("channel"), event.get("url"))
            for event in self.events
            if _canonical_channel(event.get("channel"), event.get("url"))
        }
        target_names = [spec.label for spec in TARGET_CHANNELS]
        individual_offer_names = {
            str(offer.channel or "").strip()
            for offer in offer_list
            if not (target_spec_for_name(offer.channel) or target_spec_for_url(offer.url))
        }
        names = list(dict.fromkeys([*target_names, *sorted(observed_names - set(target_names)), *sorted(individual_offer_names)]))

        channels: list[dict[str, Any]] = []
        for name in names:
            events = [event for event in self.events if _canonical_channel(event.get("channel"), event.get("url")) == name]
            rows = [offer for offer in offer_list if _offer_matches_channel(offer, name)]
            stages = [str(event.get("stage") or "") for event in events]
            last_stage = stages[-1] if stages else "NOT_SEARCHED"
            if rows:
                all_out = all(
                    str(row.availability or "").casefold().endswith("outofstock") or (row.stock is not None and row.stock <= 0)
                    for row in rows
                )
                last_stage = "OUT_OF_STOCK" if all_out else "OFFER_ACCEPTED"

            urls = list(dict.fromkeys(str(event.get("url") or "") for event in events if event.get("url")))
            sellers = sorted({
                str(row.seller_display_name or row.seller_legal_name or "").strip()
                for row in rows
                if str(row.seller_display_name or row.seller_legal_name or "").strip()
            })
            stocks = [row.stock for row in rows if row.stock is not None]
            channels.append({
                "channel": name,
                "status": last_stage,
                "final_status": last_stage,
                "failure_stage": None if last_stage in {"OFFER_ACCEPTED", "OUT_OF_STOCK"} else FAILURE_STAGE.get(last_stage),
                "searched": any(stage in SEARCH_STAGES for stage in stages),
                "raw_hit": "RAW_RESULT_FOUND" in stages,
                "url_found": bool(urls) or any(stage in {"URL_DISCOVERED", *FETCHED_STAGES} for stage in stages),
                "fetched": any(stage in FETCHED_STAGES for stage in stages),
                "parsed": any(stage in PARSED_STAGES for stage in stages),
                "identity_valid": bool(rows) or any(stage in IDENTITY_ACCEPTED_STAGES for stage in stages),
                "price_found": bool(rows) or any(stage in PRICE_STAGES for stage in stages),
                "stock": stocks or None,
                "seller": sellers or None,
                "urls": urls,
                "offers": [row.to_dict() for row in rows],
            })

        return {
            "channels": channels,
            "individual_stores": legacy.get("individual_stores", []),
            "individual_store_count": legacy.get("individual_store_count", 0),
            "events": [dict(event) for event in self.events],
            "funnel": self.funnel(),
            "queries": self.query_report(),
        }
