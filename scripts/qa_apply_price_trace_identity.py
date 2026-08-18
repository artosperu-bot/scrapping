from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"expected source block not found: {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "src/product_intelligence/price_workflow.py",
    "from .mercadolibre_oauth import build_mercadolibre_api_client\nfrom .models import ProductIdentity\n",
    "from .identity_bootstrap import bootstrap_identity\nfrom .mercadolibre_oauth import build_mercadolibre_api_client\nfrom .models import ProductIdentity\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers\nfrom .web_fetch import fetch_page\n",
    "from .price_peru_coverage import discover_additional_peru_pdps, discover_general_peru_retailers\nfrom .price_trace import PriceTrace\nfrom .web_fetch import fetch_page\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "def _query(identity: ProductIdentity) -> str:\n    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or \"\").strip()\n\n\n",
    "def _query(identity: ProductIdentity) -> str:\n    return str(identity.mpn or identity.ean or identity.upc or identity.gtin or identity.model or identity.product_name or \"\").strip()\n\n\n"
    "def _resolve_price_identity(identity: ProductIdentity) -> tuple[ProductIdentity, dict]:\n"
    "    if not _query(identity):\n"
    "        return identity, {\"status\": \"IDENTITY_UNRESOLVED\", \"confidence\": 0.0, \"reason\": \"NO_IDENTITY_SIGNAL\", \"official_domain_hint\": None}\n"
    "    if identity.brand and (identity.model or identity.product_name) and (identity.mpn or identity.ean or identity.upc or identity.gtin):\n"
    "        return identity, {\"status\": \"ALREADY_RESOLVED\", \"confidence\": float(identity.confidence or 1.0), \"reason\": \"INPUT_HAS_STRONG_IDENTITY\", \"official_domain_hint\": None}\n"
    "    try:\n"
    "        result = bootstrap_identity(identity, limit_per_query=14, timeout=8)\n"
    "    except Exception as exc:\n"
    "        return identity, {\"status\": \"IDENTITY_UNRESOLVED\", \"confidence\": 0.0, \"reason\": f\"BOOTSTRAP_ERROR:{type(exc).__name__}\", \"official_domain_hint\": None}\n"
    "    resolved = getattr(result, \"identity\", None) or identity\n"
    "    status = str(getattr(result, \"status\", \"IDENTITY_UNRESOLVED\") or \"IDENTITY_UNRESOLVED\")\n"
    "    if status != \"RESOLVED\":\n"
    "        resolved = identity\n"
    "    return resolved, {\n"
    "        \"status\": status,\n"
    "        \"confidence\": float(getattr(result, \"confidence\", 0.0) or 0.0),\n"
    "        \"reason\": str(getattr(result, \"reason\", \"\") or \"\"),\n"
    "        \"official_domain_hint\": getattr(result, \"official_domain_hint\", None),\n"
    "    }\n\n\n",
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    "def run_price_product(identity: ProductIdentity, output_root: str | Path, *, on_event=None, max_sources: int = 48) -> list[PriceOffer]:\n"
    "    def emit(event_type: str, **payload):\n"
    "        if on_event:\n"
    "            on_event({\"type\": event_type, \"identity\": identity.model_dump(), **payload})\n\n"
    "    offers: list[PriceOffer] = []\n",
    "def run_price_product(identity: ProductIdentity, output_root: str | Path, *, on_event=None, max_sources: int = 48) -> list[PriceOffer]:\n"
    "    input_identity = identity\n"
    "    identity, identity_resolution = _resolve_price_identity(input_identity)\n"
    "    trace = PriceTrace()\n\n"
    "    def emit(event_type: str, **payload):\n"
    "        if event_type == \"page\":\n"
    "            status = str(payload.get(\"status\") or \"\").lower()\n"
    "            channel = payload.get(\"channel\")\n"
    "            url = payload.get(\"url\")\n"
    "            if status == \"fetching\":\n"
    "                trace.record(\"URL_DISCOVERED\", channel=channel, url=url)\n"
    "                trace.record(\"FETCH_STARTED\", channel=channel, url=url)\n"
    "            elif status == \"parsed\":\n"
    "                trace.record(\"FETCH_OK\", channel=channel, url=url)\n"
    "                trace.record(\"PARSER_STARTED\", channel=channel, url=url)\n"
    "                if int(payload.get(\"offers\") or 0) > 0:\n"
    "                    trace.record(\"PARSER_OK\", channel=channel, url=url, offers=int(payload.get(\"offers\") or 0))\n"
    "                else:\n"
    "                    trace.record(\"PARSER_ZERO_OFFERS\", channel=channel, url=url)\n"
    "            elif status in {\"error\", \"browser_error\"}:\n"
    "                trace.record(\"FETCH_FAILED\", channel=channel, url=url, error=payload.get(\"error\"))\n"
    "        if on_event:\n"
    "            on_event({\"type\": event_type, \"identity\": identity.model_dump(), **payload})\n\n"
    "    emit(\"identity\", input_identity=input_identity.model_dump(), resolved_identity=identity.model_dump(), **identity_resolution)\n"
    "    offers: list[PriceOffer] = []\n",
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    "    for channel, base_url in PERU_STRUCTURED_SOURCES:\n        try:\n            rows = _try_vtex(base_url, identity, channel)\n",
    "    for channel, base_url in PERU_STRUCTURED_SOURCES:\n        trace.record(\"QUERY_EXECUTED\", channel=channel, query=_query(identity), method=\"structured_direct\")\n        try:\n            rows = _try_vtex(base_url, identity, channel)\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "            offers.extend(rows)\n            emit(\"source\", channel=channel, status=\"ok\", offers=len(rows), method=\"structured_direct\")\n",
    "            offers.extend(rows)\n            if rows:\n                for row in rows:\n                    trace.record(\"IDENTITY_ACCEPTED\", channel=channel, url=row.url, identity_match=row.identity_match)\n                    trace.record(\"PRICE_EXTRACTED\", channel=channel, url=row.url, price=row.selling_price, currency=row.currency)\n            else:\n                trace.record(\"QUERY_EXECUTED_NO_RESULT\", channel=channel, query=_query(identity), method=\"structured_direct\")\n            emit(\"source\", channel=channel, status=\"ok\", offers=len(rows), method=\"structured_direct\")\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "    try:\n        ml = _try_mercadolibre(identity)\n",
    "    trace.record(\"QUERY_EXECUTED\", channel=\"Mercado Libre\", query=_query(identity), method=\"mercadolibre_mpe\")\n    try:\n        ml = _try_mercadolibre(identity)\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "        offers.extend(ml)\n        emit(\"source\", channel=\"MercadoLibre\", status=\"ok\", offers=len(ml), method=\"mercadolibre_mpe\")\n",
    "        offers.extend(ml)\n        if ml:\n            for row in ml:\n                trace.record(\"IDENTITY_ACCEPTED\", channel=\"Mercado Libre\", url=row.url, identity_match=row.identity_match)\n                trace.record(\"PRICE_EXTRACTED\", channel=\"Mercado Libre\", url=row.url, price=row.selling_price, currency=row.currency)\n        else:\n            trace.record(\"QUERY_EXECUTED_NO_RESULT\", channel=\"Mercado Libre\", query=_query(identity), method=\"mercadolibre_mpe\")\n        emit(\"source\", channel=\"MercadoLibre\", status=\"ok\", offers=len(ml), method=\"mercadolibre_mpe\")\n",
)

# Explicit identity resolution happens once in Price. Generic discovery must not silently
# bootstrap a second time when the explicit resolver remained unresolved.
replace_once(
    "src/product_intelligence/discovery.py",
    "def search_web(identity:ProductIdentity,limit:int=12,timeout:int=10,budget_tracker:SearchBudgetTracker|None=None,query_quota:int|None=None)->list[SearchCandidate]:",
    "def search_web(identity:ProductIdentity,limit:int=12,timeout:int=10,budget_tracker:SearchBudgetTracker|None=None,query_quota:int|None=None,allow_identity_bootstrap:bool=True)->list[SearchCandidate]:",
)
replace_once(
    "src/product_intelligence/discovery.py",
    "    effective_identity,official_hint=_bootstrap_unknown_identity(identity,timeout)\n",
    "    effective_identity,official_hint=_bootstrap_unknown_identity(identity,timeout) if allow_identity_bootstrap else (identity,None)\n",
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    "def discover_price_sources(\n    identity: ProductIdentity,\n    limit: int = 24,\n    *,\n    priority_domains: tuple[str, ...] = PERU_PRICE_DOMAINS,\n) -> list[str]:",
    "def discover_price_sources(\n    identity: ProductIdentity,\n    limit: int = 24,\n    *,\n    priority_domains: tuple[str, ...] = PERU_PRICE_DOMAINS,\n    allow_identity_bootstrap: bool = True,\n) -> list[str]:",
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    "    candidates = search_web(identity, limit=max(limit * 3, 24))\n",
    "    candidates = search_web(identity, limit=max(limit * 3, 24), allow_identity_bootstrap=allow_identity_bootstrap)\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "            base_sources = discover_price_sources(identity, limit=max_sources)\n",
    "            base_sources = discover_price_sources(identity, limit=max_sources, allow_identity_bootstrap=False)\n",
)

# Record discovered URLs without turning the trace into a discovery seed.
replace_once(
    "src/product_intelligence/price_workflow.py",
    "            marketplace_sources = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)))\n            emit(\"source\", channel=\"peru_directed\", status=\"ok\", offers=0, urls=len(marketplace_sources), method=\"targeted_pdp\")\n",
    "            marketplace_sources = discover_additional_peru_pdps(identity, limit_per_domain=max(4, min(10, max_sources // 4 or 4)))\n            for url in marketplace_sources:\n                trace.record(\"URL_DISCOVERED\", channel=_channel_from_url(url), url=url, method=\"targeted_pdp\")\n            emit(\"source\", channel=\"peru_directed\", status=\"ok\", offers=0, urls=len(marketplace_sources), method=\"targeted_pdp\")\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "                retail_sources = discover_general_peru_retailers(identity, limit=max(10, max_sources // 2))\n                emit(\"source\", channel=\"peru_retail\", status=\"ok\", offers=0, urls=len(retail_sources), method=\"identifier_and_alias_retail\")\n",
    "                retail_sources = discover_general_peru_retailers(identity, limit=max(10, max_sources // 2))\n                for url in retail_sources:\n                    trace.record(\"URL_DISCOVERED\", channel=_channel_from_url(url), url=url, method=\"identifier_and_alias_retail\")\n                emit(\"source\", channel=\"peru_retail\", status=\"ok\", offers=0, urls=len(retail_sources), method=\"identifier_and_alias_retail\")\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "            base_sources = discover_price_sources(identity, limit=max_sources, allow_identity_bootstrap=False)\n            emit(\"source\", channel=\"web\", status=\"ok\", offers=0, urls=len(base_sources), method=\"generic_peru\")\n",
    "            base_sources = discover_price_sources(identity, limit=max_sources, allow_identity_bootstrap=False)\n            for url in base_sources:\n                trace.record(\"URL_DISCOVERED\", channel=_channel_from_url(url), url=url, method=\"generic_peru\")\n            emit(\"source\", channel=\"web\", status=\"ok\", offers=0, urls=len(base_sources), method=\"generic_peru\")\n",
)

replace_once(
    "src/product_intelligence/price_workflow.py",
    "    coverage = build_channel_coverage(valid)\n",
    "    for row in valid:\n        trace.record(\"OFFER_ACCEPTED\", channel=row.channel, url=row.url, price=row.selling_price, currency=row.currency, seller=row.seller_display_name, identity_match=row.identity_match)\n    coverage = trace.coverage(valid)\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "        target_channels_found=sum(1 for row in coverage[\"channels\"] if row[\"status\"] == \"FOUND\"),\n",
    "        target_channels_found=sum(1 for row in coverage[\"channels\"] if row.get(\"final_status\") in {\"OFFER_ACCEPTED\", \"OUT_OF_STOCK\"}),\n",
)

print("PRICE_TRACE_IDENTITY_PATCH=APPLIED")
