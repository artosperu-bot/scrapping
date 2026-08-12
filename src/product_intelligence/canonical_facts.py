from __future__ import annotations

import re
from typing import Any

from .models import ProductRecord
from .normalize import canonical_key, key_norm


def _value(ev) -> str:
    return str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value or "").strip()


def _norm_bool(value: str) -> bool | None:
    n=key_norm(value)
    if n in {"yes","si","true","1","supported","included"}: return True
    if n in {"no","false","0","not supported","unsupported","none"}: return False
    return None


def build_canonical_facts(rec: ProductRecord) -> dict[str, Any]:
    """Build conservative reusable facts from already filtered/deduplicated evidence.

    This module does not know Falabella column names and does not write marketplace values.
    It only represents product reality in category-neutral concepts that later resolvers can
    map/derive/classify.
    """
    facts: dict[str, Any] = {
        "identity": {
            "brand": rec.identity.brand,
            "manufacturer": rec.identity.manufacturer,
            "model": rec.identity.model,
            "mpn": rec.identity.mpn,
            "gtin": rec.identity.gtin or rec.identity.ean or rec.identity.upc,
            "variant": rec.identity.variant,
            "color": rec.identity.color,
        },
        "connectivity": {
            "bluetooth": {"present": None, "version": None},
            "wired": None,
            "wireless": None,
            "usb": False,
            "usb_c": False,
            "rf_2_4ghz": False,
            "wifi": False,
            "nfc": False,
            "jack_3_5mm": False,
        },
        "battery": {"present": None, "rechargeable": None, "runtime_hours": None},
        "durability": {"ip_rating": None, "dust_rating": None, "water_rating": None},
        "form_factor": None,
        "color": {"raw": None, "base": None},
        "package": {"weight": None, "width": None, "length": None, "height": None},
        "product": {"weight": None, "dimensions": None},
    }

    texts=[]
    for ev in rec.evidence:
        attr=key_norm(ev.attribute)
        raw=_value(ev)
        val=key_norm(raw)
        ck=canonical_key(ev.attribute)
        texts.append(f"{attr} {val}")

        if ck in {"gtin","ean","upc"} and raw:
            facts["identity"]["gtin"] = raw
        elif ck == "brand" and raw and not facts["identity"]["brand"]:
            facts["identity"]["brand"] = raw
        elif ck == "model" and raw and not facts["identity"]["model"]:
            facts["identity"]["model"] = raw
        elif ck == "color" and raw:
            facts["color"]["raw"] = raw
        elif ck == "package_weight" and raw:
            facts["package"]["weight"] = raw
        elif ck == "package_width" and raw:
            facts["package"]["width"] = raw
        elif ck == "package_length" and raw:
            facts["package"]["length"] = raw
        elif ck == "package_height" and raw:
            facts["package"]["height"] = raw
        elif ck == "weight" and raw:
            facts["product"]["weight"] = raw
        elif ck == "dimensions" and raw:
            facts["product"]["dimensions"] = raw

        if "bluetooth" in attr:
            explicit=_norm_bool(raw)
            if explicit is not None:
                facts["connectivity"]["bluetooth"]["present"] = explicit
            m=re.search(r"(?:bluetooth\s*)?(\d(?:\.\d)?)",raw,re.I)
            if m and ("version" in attr or "bluetooth" in raw.lower()):
                facts["connectivity"]["bluetooth"]["version"] = m.group(1)
                facts["connectivity"]["bluetooth"]["present"] = True

        joined=f"{attr} {val}"
        if re.search(r"\busb[ -]?c\b",joined,re.I): facts["connectivity"]["usb_c"] = True
        elif re.search(r"\busb\b",joined,re.I): facts["connectivity"]["usb"] = True
        if re.search(r"\b3[., ]5\s*mm\b|headphone jack|audio jack",joined,re.I): facts["connectivity"]["jack_3_5mm"] = True
        if re.search(r"2[ .]?4\s*ghz|radio ?frequency|\brf\b",joined,re.I):
            facts["connectivity"]["rf_2_4ghz"] = True
            facts["connectivity"]["wireless"] = True
        if re.search(r"\bwi[ -]?fi\b",joined,re.I): facts["connectivity"]["wifi"] = True
        if re.search(r"\bnfc\b",joined,re.I): facts["connectivity"]["nfc"] = True
        if re.search(r"\bwired\b|cableado|al[aá]mbric",joined,re.I): facts["connectivity"]["wired"] = True
        if re.search(r"\bwireless\b|inal[aá]mbric",joined,re.I): facts["connectivity"]["wireless"] = True

        if re.search(r"battery|bater[ií]a",attr,re.I):
            if re.search(r"no battery|without battery|sin bater[ií]a|battery required\s*[:=]?\s*(?:no|false)",raw,re.I):
                facts["battery"]["present"] = False
            elif raw:
                facts["battery"]["present"] = True
            if re.search(r"recharge|recargable|lithium|li[ -]?ion",raw,re.I):
                facts["battery"]["rechargeable"] = True
        if ck == "battery_life" or re.search(r"battery life|play time|runtime|autonom",attr,re.I):
            m=re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hours?|horas?)\b",raw,re.I)
            if m:
                facts["battery"]["runtime_hours"] = float(m.group(1).replace(",","."))
                if facts["battery"]["present"] is None: facts["battery"]["present"] = True

        m=re.search(r"\bIP\s*([0-6X])([0-9K])\b",raw,re.I)
        if not m:
            m=re.search(r"\bIP\s*([0-6X])([0-9K])\b",ev.attribute,re.I)
        if m:
            rating=f"IP{m.group(1).upper()}{m.group(2).upper()}"
            facts["durability"]["ip_rating"] = rating
            facts["durability"]["dust_rating"] = None if m.group(1).upper()=="X" else m.group(1)
            facts["durability"]["water_rating"] = m.group(2)

        if re.search(r"\bin[ -]?ear\b|intraaural",joined,re.I): facts["form_factor"] = "in-ear"
        elif re.search(r"\bon[ -]?ear\b|supraaural",joined,re.I): facts["form_factor"] = "on-ear"
        elif re.search(r"\bover[ -]?ear\b|circumaural",joined,re.I): facts["form_factor"] = "over-ear"

    # Closed-world implications only when facts are explicit enough.
    bt=facts["connectivity"]["bluetooth"]
    if bt["version"] is not None: bt["present"] = True
    if facts["connectivity"]["usb_c"] or facts["connectivity"]["jack_3_5mm"]:
        if facts["connectivity"]["wired"] is None:
            facts["connectivity"]["wired"] = True
    if facts["battery"]["present"] is False:
        facts["battery"]["rechargeable"] = False
        facts["battery"]["runtime_hours"] = None
    return facts
