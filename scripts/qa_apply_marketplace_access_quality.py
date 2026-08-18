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


# Identifier validation is explicit and type-safe. Seller/manufacturer SKUs never become GTIN.
replace_once(
    "src/product_intelligence/identifiers.py",
    "def is_valid_gtin(value: str | None) -> bool:\n    return validate_gtin(value).valid\n\n\n",
    "def is_valid_gtin(value: str | None) -> bool:\n    return validate_gtin(value).valid\n\n\n"
    "def clean_gtin(value: str | None) -> str | None:\n"
    "    text = str(value or \"\").strip()\n"
    "    if not text or text.casefold() in {\"null\", \"none\", \"n/a\", \"na\", \"unknown\", \"-\"}:\n"
    "        return None\n"
    "    checked = validate_gtin(text)\n"
    "    return checked.value if checked.valid else None\n\n\n",
)

# Backward-compatible offer schema additions. Existing url/sku/publication_id remain available.
replace_once(
    "src/product_intelligence/price_models.py",
    "    publication_id: str | None = None\n    sku: str | None = None\n    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())\n    evidence: dict[str, Any] = field(default_factory=dict)\n\n    def to_dict(self) -> dict[str, Any]:\n        return asdict(self)\n",
    "    publication_id: str | None = None\n"
    "    sku: str | None = None\n"
    "    seller_id: str | None = None\n"
    "    seller_sku: str | None = None\n"
    "    marketplace_product_id: str | None = None\n"
    "    marketplace_listing_id: str | None = None\n"
    "    internal_product_id: str | None = None\n"
    "    direct_product_url: str | None = None\n"
    "    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())\n"
    "    evidence: dict[str, Any] = field(default_factory=dict)\n\n"
    "    def __post_init__(self) -> None:\n"
    "        if not self.direct_product_url:\n"
    "            self.direct_product_url = self.url\n\n"
    "    def to_dict(self) -> dict[str, Any]:\n"
    "        return asdict(self)\n",
)

# Structured marketplace adapters preserve identifiers by semantic type.
replace_once(
    "src/product_intelligence/price_adapters.py",
    "from .models import ProductIdentity\n",
    "from .identifiers import clean_gtin\nfrom .models import ProductIdentity\n",
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    '        "gtin": attrs.get("GTIN") or attrs.get("EAN"),\n        "title": row.get("title"),\n',
    '        "gtin": clean_gtin(attrs.get("GTIN") or attrs.get("EAN") or attrs.get("UPC")),\n'
    '        "ean": clean_gtin(attrs.get("EAN")),\n'
    '        "upc": clean_gtin(attrs.get("UPC")),\n'
    '        "title": row.get("title"),\n',
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    "        seller = row.get(\"seller\") if isinstance(row.get(\"seller\"), dict) else {}\n        out.append(PriceOffer(\n",
    "        seller = row.get(\"seller\") if isinstance(row.get(\"seller\"), dict) else {}\n"
    "        seller_id = seller.get(\"id\") or row.get(\"seller_id\")\n"
    "        listing_id = str(row.get(\"id\") or \"\") or None\n"
    "        catalog_id = str(row.get(\"catalog_product_id\") or \"\") or None\n"
    "        direct_url = str(row.get(\"permalink\") or \"\")\n"
    "        out.append(PriceOffer(\n",
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    "            url=str(row.get(\"permalink\") or \"\"),\n            confidence=score,\n",
    "            url=direct_url,\n"
    "            confidence=score,\n",
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    "            publication_id=str(row.get(\"id\") or \"\") or None,\n            evidence=evidence,\n",
    "            publication_id=listing_id,\n"
    "            seller_id=str(seller_id) if seller_id is not None else None,\n"
    "            marketplace_product_id=catalog_id,\n"
    "            marketplace_listing_id=listing_id,\n"
    "            direct_product_url=direct_url,\n"
    "            evidence=evidence,\n",
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    "    if expected and any(expected in _norm(candidate) for candidate in candidates if candidate):\n        evidence[\"mpn\"] = identity.mpn\n    return evidence\n",
    "    if expected and any(expected in _norm(candidate) for candidate in candidates if candidate):\n"
    "        evidence[\"mpn\"] = identity.mpn\n"
    "    verified = clean_gtin(item.get(\"ean\"))\n"
    "    if verified:\n"
    "        evidence[\"gtin\"] = verified\n"
    "        if len(verified) == 12:\n"
    "            evidence[\"upc\"] = verified\n"
    "        elif len(verified) == 13:\n"
    "            evidence[\"ean\"] = verified\n"
    "    return evidence\n",
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    "                    publication_id=str(product.get(\"productId\") or \"\") or None,\n                    sku=sku,\n                    evidence=evidence,\n",
    "                    publication_id=str(product.get(\"productId\") or \"\") or None,\n"
    "                    sku=sku,\n"
    "                    seller_id=str(seller.get(\"sellerId\") or \"\") or None,\n"
    "                    seller_sku=sku,\n"
    "                    marketplace_product_id=str(product.get(\"productId\") or \"\") or None,\n"
    "                    direct_product_url=product_url,\n"
    "                    evidence=evidence,\n",
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    '        barcode = str(variant.get("barcode") or "").strip()\n        evidence = {\n            "mpn": identity.mpn if expected_mpn and _norm(sku) == expected_mpn else None,\n            "gtin": barcode or None,\n',
    '        barcode = str(variant.get("barcode") or "").strip()\n'
    '        verified_barcode = clean_gtin(barcode)\n'
    '        evidence = {\n'
    '            "mpn": identity.mpn if expected_mpn and _norm(sku) == expected_mpn else None,\n'
    '            "gtin": verified_barcode,\n'
    '            "upc": verified_barcode if verified_barcode and len(verified_barcode) == 12 else None,\n'
    '            "ean": verified_barcode if verified_barcode and len(verified_barcode) == 13 else None,\n',
)
replace_once(
    "src/product_intelligence/price_adapters.py",
    "            publication_id=str(payload.get(\"id\") or \"\") or None,\n            sku=sku or (str(variant.get(\"id\") or \"\") or None),\n            evidence=evidence,\n",
    "            publication_id=str(payload.get(\"id\") or \"\") or None,\n"
    "            sku=sku or (str(variant.get(\"id\") or \"\") or None),\n"
    "            seller_sku=sku or None,\n"
    "            internal_product_id=str(payload.get(\"id\") or \"\") or None,\n"
    "            direct_product_url=source_url,\n"
    "            evidence=evidence,\n",
)

# JSON-LD evidence uses only checksum-valid GTIN/UPC/EAN values and generic HTML avoids
# obvious shipping/installment/unit amounts before considering a selling price.
replace_once(
    "src/product_intelligence/price_discovery.py",
    "from .discovery import search_web, search_web_query\nfrom .models import ProductIdentity\n",
    "from .discovery import search_web, search_web_query\nfrom .identifiers import clean_gtin\nfrom .models import ProductIdentity\n",
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    "def _seller_from_text(text: str) -> str | None:\n",
    "def _first_verified_gtin(*values) -> str | None:\n"
    "    for value in values:\n"
    "        cleaned = clean_gtin(value)\n"
    "        if cleaned:\n"
    "            return cleaned\n"
    "    return None\n\n\n"
    "def _html_selling_price(text: str) -> float | None:\n"
    "    pattern = re.compile(r\"(?:S/\\.?|S\\s*/|PEN\\s*)\\s*([0-9]{1,7}(?:[.,][0-9]{1,2})?)\", re.I)\n"
    "    bad_before = (\"envío\", \"envio\", \"delivery\", \"shipping\", \"cuota\", \"cuotas\", \"mensual\", \"mes\", \"unidad\", \"unitario\", \"cupón\", \"cupon\")\n"
    "    bad_after = (\"/kg\", \"por kg\", \"por kilo\", \"/unidad\", \"por unidad\")\n"
    "    for match in pattern.finditer(text or \"\"):\n"
    "        before = (text[max(0, match.start() - 20):match.start()] or \"\").casefold()\n"
    "        after = (text[match.end():match.end() + 22] or \"\").casefold()\n"
    "        if any(marker in before for marker in bad_before) or any(marker in after for marker in bad_after):\n"
    "            continue\n"
    "        value = _money(match.group(1))\n"
    "        if value and value > 0:\n"
    "            return value\n"
    "    return None\n\n\n"
    "def _seller_from_text(text: str) -> str | None:\n",
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    '                "gtin": node.get("gtin13") or node.get("gtin12") or node.get("gtin14") or node.get("gtin8") or node.get("gtin"),\n                "title": node.get("name") or base_evidence.get("title"),\n',
    '                "gtin": _first_verified_gtin(node.get("gtin13"), node.get("gtin12"), node.get("gtin14"), node.get("gtin8"), node.get("gtin")),\n'
    '                "upc": clean_gtin(node.get("gtin12")),\n'
    '                "ean": clean_gtin(node.get("gtin13")),\n'
    '                "title": node.get("name") or base_evidence.get("title"),\n',
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    "                    sku=str(node.get(\"sku\") or \"\") or None,\n                    evidence=evidence,\n",
    "                    sku=str(node.get(\"sku\") or \"\") or None,\n"
    "                    seller_sku=str(node.get(\"sku\") or \"\") or None,\n"
    "                    direct_product_url=urljoin(url, offer_url),\n"
    "                    evidence=evidence,\n",
)
replace_once(
    "src/product_intelligence/price_discovery.py",
    "    if not meta_price:\n        match_price = re.search(r\"(?:S/\\.?|S\\s*/|PEN\\s*)\\s*([0-9]{1,6}(?:[.,][0-9]{1,2})?)\", page_text, re.I)\n        meta_price = _money(match_price.group(1)) if match_price else None\n",
    "    if not meta_price:\n        meta_price = _html_selling_price(page_text)\n",
)

# Dedupe respects explicit marketplace seller identity before display-name heuristics.
replace_once(
    "src/product_intelligence/price_identity.py",
    "def competitor_key(row: PriceOffer) -> str:\n    tax_id = _norm(row.seller_tax_id)\n    if tax_id:\n        return f\"tax:{tax_id}\"\n    channel = _seller_key(row.channel)\n",
    "def competitor_key(row: PriceOffer) -> str:\n"
    "    tax_id = _norm(row.seller_tax_id)\n"
    "    if tax_id:\n"
    "        return f\"tax:{tax_id}\"\n"
    "    channel = _seller_key(row.channel)\n"
    "    seller_id = _norm(row.seller_id)\n"
    "    if seller_id:\n"
    "        return f\"sellerid:{channel}:{seller_id}\"\n",
)
replace_once(
    "src/product_intelligence/price_identity.py",
    "        locator = canonical if specific_pdp else (row.publication_id or row.sku or canonical)\n",
    "        locator = canonical if specific_pdp else (row.marketplace_listing_id or row.publication_id or row.internal_product_id or row.sku or canonical)\n",
)

# OAuth store tolerates an unavailable OS keyring by using a process-memory state plus
# explicit environment configuration. Nothing is logged and no secret is hardcoded.
replace_once(
    "src/product_intelligence/mercadolibre_oauth.py",
    "import json\nimport threading\n",
    "import json\nimport os\nimport threading\n",
)
replace_once(
    "src/product_intelligence/mercadolibre_oauth.py",
    "    def __init__(self, key: str = ML_OAUTH_STATE_KEY):\n        self.key = key\n\n    def load(self) -> MercadoLibreOAuthState | None:\n        raw = load_value(self.key)\n        if not raw:\n            return None\n",
    "    def __init__(self, key: str = ML_OAUTH_STATE_KEY):\n"
    "        self.key = key\n"
    "        self._volatile_state: MercadoLibreOAuthState | None = None\n\n"
    "    @staticmethod\n"
    "    def _environment_state() -> MercadoLibreOAuthState | None:\n"
    "        client_id = str(os.environ.get(\"MERCADOLIBRE_CLIENT_ID\") or \"\").strip()\n"
    "        client_secret = str(os.environ.get(\"MERCADOLIBRE_CLIENT_SECRET\") or \"\").strip()\n"
    "        refresh_token = str(os.environ.get(\"MERCADOLIBRE_REFRESH_TOKEN\") or \"\").strip()\n"
    "        access_token = str(os.environ.get(\"MERCADOLIBRE_ACCESS_TOKEN\") or \"\").strip()\n"
    "        if not any((client_id, client_secret, refresh_token, access_token)):\n"
    "            return None\n"
    "        return MercadoLibreOAuthState(\n"
    "            client_id=client_id, client_secret=client_secret, refresh_token=refresh_token, access_token=access_token,\n"
    "            expires_at=str(os.environ.get(\"MERCADOLIBRE_EXPIRES_AT\") or \"\").strip(),\n"
    "            updated_at=datetime.now(timezone.utc).isoformat(),\n"
    "        )\n\n"
    "    def load(self) -> MercadoLibreOAuthState | None:\n"
    "        if self._volatile_state is not None:\n"
    "            return self._volatile_state\n"
    "        try:\n"
    "            raw = load_value(self.key)\n"
    "        except Exception:\n"
    "            raw = None\n"
    "        if not raw:\n"
    "            return self._environment_state()\n",
)
replace_once(
    "src/product_intelligence/mercadolibre_oauth.py",
    "        except (TypeError, ValueError, json.JSONDecodeError):\n            return None\n\n    def save(self, state: MercadoLibreOAuthState) -> None:\n        save_value(self.key, json.dumps(asdict(state), ensure_ascii=False, separators=(\",\", \":\")))\n\n    def clear(self) -> None:\n        delete_value(self.key)\n",
    "        except (TypeError, ValueError, json.JSONDecodeError):\n"
    "            return self._environment_state()\n\n"
    "    def save(self, state: MercadoLibreOAuthState) -> None:\n"
    "        self._volatile_state = state\n"
    "        try:\n"
    "            save_value(self.key, json.dumps(asdict(state), ensure_ascii=False, separators=(\",\", \":\")))\n"
    "        except Exception:\n"
    "            return\n\n"
    "    def clear(self) -> None:\n"
    "        self._volatile_state = None\n"
    "        try:\n"
    "            delete_value(self.key)\n"
    "        except Exception:\n"
    "            return\n",
)
replace_once(
    "src/product_intelligence/mercadolibre_oauth.py",
    "        expiry = _parse_expiry(state.expires_at)\n        if expiry is None:\n            return True\n",
    "        expiry = _parse_expiry(state.expires_at)\n"
    "        if expiry is None:\n"
    "            # Unknown expiry is not proof of expiry. Use the token once; a 401 causes\n"
    "            # the API client to refresh and retry exactly once.\n"
    "            return False\n",
)

# Access is classified before parsing. Browser fallback remains legitimate; if it still
# returns 401/403/429 the result is FETCH_BLOCKED rather than PARSER_ZERO.
replace_once(
    "src/product_intelligence/price_workflow.py",
    "from .mercadolibre_oauth import build_mercadolibre_api_client\n",
    "from .mercadolibre_oauth import MercadoLibreAuthError, build_mercadolibre_api_client\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "BROWSER_PRICE_CHANNELS = {\"Ripley\", \"MercadoLibre\", \"Mercado Libre\", \"JBL Perú\"}\n\n\n",
    "BROWSER_PRICE_CHANNELS = {\"Ripley\", \"MercadoLibre\", \"Mercado Libre\", \"JBL Perú\"}\n\n\n"
    "class PriceFetchBlocked(RuntimeError):\n"
    "    def __init__(self, status_code: int, url: str):\n"
    "        self.status_code = int(status_code)\n"
    "        self.url = str(url)\n"
    "        super().__init__(f\"HTTP {self.status_code}\")\n\n\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "    final_url = str(getattr(fetched, \"final_url\", None) or url)\n    html = str(getattr(fetched, \"html\", \"\") or \"\")\n    page_rows = extract_page_offers(html, final_url, identity, channel=channel)\n",
    "    final_url = str(getattr(fetched, \"final_url\", None) or url)\n"
    "    status_code = int(getattr(fetched, \"status_code\", 0) or 0)\n"
    "    if status_code in {401, 403, 429}:\n"
    "        raise PriceFetchBlocked(status_code, final_url)\n"
    "    if status_code >= 400:\n"
    "        raise requests.HTTPError(f\"HTTP {status_code}\")\n"
    "    html = str(getattr(fetched, \"html\", \"\") or \"\")\n"
    "    page_rows = extract_page_offers(html, final_url, identity, channel=channel)\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "        except Exception as exc:\n            emit(\"page\", url=url, channel=channel, status=\"error\", error=f\"{type(exc).__name__}: {exc}\")\n    return rows\n\n\ndef _has_trusted_offer",
    "        except PriceFetchBlocked as exc:\n"
    "            emit(\"page\", url=url, channel=channel, status=\"blocked\", http_status=exc.status_code, error=str(exc))\n"
    "        except requests.Timeout as exc:\n"
    "            emit(\"page\", url=url, channel=channel, status=\"timeout\", error=f\"{type(exc).__name__}: {exc}\")\n"
    "        except Exception as exc:\n"
    "            emit(\"page\", url=url, channel=channel, status=\"error\", error=f\"{type(exc).__name__}: {exc}\")\n"
    "    return rows\n\n\ndef _has_trusted_offer",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "            elif status in {\"error\", \"browser_error\"}:\n                trace.record(\"FETCH_FAILED\", channel=channel, url=url, error=payload.get(\"error\"))\n",
    "            elif status == \"blocked\":\n"
    "                trace.record(\"FETCH_BLOCKED\", channel=channel, url=url, http_status=payload.get(\"http_status\"), error=payload.get(\"error\"))\n"
    "            elif status == \"timeout\":\n"
    "                trace.record(\"FETCH_TIMEOUT\", channel=channel, url=url, error=payload.get(\"error\"))\n"
    "            elif status in {\"error\", \"browser_error\"}:\n"
    "                trace.record(\"FETCH_FAILED\", channel=channel, url=url, error=payload.get(\"error\"))\n",
)
replace_once(
    "src/product_intelligence/price_workflow.py",
    "    except Exception as exc:\n        emit(\"source\", channel=\"MercadoLibre\", status=\"error\", error=f\"{type(exc).__name__}: {exc}\")\n\n    retail_sources",
    "    except MercadoLibreAuthError as exc:\n"
    "        trace.record(\"ML_API_AUTH_FAILED\", channel=\"Mercado Libre\", code=exc.code, http_status=exc.http_status)\n"
    "        emit(\"source\", channel=\"MercadoLibre\", status=\"auth_failed\", error_code=exc.code)\n"
    "    except Exception as exc:\n"
    "        emit(\"source\", channel=\"MercadoLibre\", status=\"error\", error=f\"{type(exc).__name__}: {exc}\")\n\n"
    "    retail_sources",
)

# Coverage understands ML auth as a terminal source state, not NO_HAY.
replace_once(
    "src/product_intelligence/price_trace.py",
    '    "FETCH_FAILED": "ACCESS",\n',
    '    "FETCH_FAILED": "ACCESS",\n    "ML_API_AUTH_FAILED": "AUTH",\n',
)
replace_once(
    "src/product_intelligence/price_trace.py",
    '    "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED",\n}',
    '    "PRICE_NOT_FOUND", "PRICE_REJECTED", "OUT_OF_STOCK", "OFFER_ACCEPTED", "OFFER_DEDUPED", "ML_API_AUTH_FAILED",\n}',
)

print("MARKETPLACE_ACCESS_QUALITY_PATCH=APPLIED")
