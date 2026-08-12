from __future__ import annotations

import re
from typing import Any

from .models import ProductRecord
from .normalize import canonical_key, key_norm


def _value(ev) -> str:
    return str(ev.normalized_value if ev.normalized_value not in (None, "") else ev.raw_value or "").strip()


def _norm_bool(value: str) -> bool | None:
    n = key_norm(value)
    if n in {"yes", "si", "true", "1", "supported", "included"}:
        return True
    if n in {"no", "false", "0", "not supported", "unsupported", "none"}:
        return False
    return None


def _number(value: str) -> float | None:
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", str(value or ""))
    return float(m.group(1).replace(",", ".")) if m else None


def _gtin_type(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    return {8: "GTIN-8", 12: "GTIN-12", 13: "GTIN-13", 14: "GTIN-14"}.get(len(digits))


def _semantic_yes(attr: str, raw: str, *terms: str) -> bool:
    return any(term in attr for term in terms) and _norm_bool(raw) is True


def build_canonical_facts(rec: ProductRecord) -> dict[str, Any]:
    """Build conservative reusable product facts from filtered/deduplicated evidence.

    This layer is marketplace-neutral. It promotes raw evidence into canonical product
    concepts before any Falabella mapping occurs.
    """
    identity_gtin = rec.identity.gtin or rec.identity.ean or rec.identity.upc
    facts: dict[str, Any] = {
        "identity": {
            "brand": rec.identity.brand,
            "manufacturer": rec.identity.manufacturer,
            "model": rec.identity.model,
            "mpn": rec.identity.mpn,
            "gtin": identity_gtin,
            "gtin_type": _gtin_type(identity_gtin),
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
        "battery": {"present": None, "rechargeable": None, "runtime_hours": None, "capacity_mah": None},
        "durability": {"ip_rating": None, "dust_rating": None, "water_rating": None},
        "form_factor": None,
        "semantic_segment": None,
        "driver_size_mm": None,
        "color": {"raw": None, "base": None},
        "package": {"weight": None, "width": None, "length": None, "height": None, "contents": None},
        "product": {"weight": None, "weight_g": None, "dimensions": None},
        "features": [],
    }

    for ev in rec.evidence:
        attr = key_norm(ev.attribute)
        raw = _value(ev)
        val = key_norm(raw)
        ck = canonical_key(ev.attribute)

        if ck in {"gtin", "ean", "upc"} and raw:
            facts["identity"]["gtin"] = raw
            facts["identity"]["gtin_type"] = _gtin_type(raw)
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

        # Bluetooth promotion: the attribute itself is enough context for a bare version.
        if "bluetooth" in attr:
            explicit = _norm_bool(raw)
            if explicit is not None:
                facts["connectivity"]["bluetooth"]["present"] = explicit
            m = re.search(r"(?:bluetooth\s*)?(\d(?:\.\d)?)", raw, re.I)
            if m and ("version" in attr or attr == "bluetooth" or "bluetooth" in attr or "bluetooth" in raw.lower()):
                facts["connectivity"]["bluetooth"]["version"] = m.group(1)
                facts["connectivity"]["bluetooth"]["present"] = True

        joined = f"{attr} {val}"
        # Connectivity fields can directly prove Bluetooth even when no separate boolean exists.
        if "bluetooth" in val and any(x in attr for x in ["connect", "conexion", "technology", "wireless"]):
            facts["connectivity"]["bluetooth"]["present"] = True
            facts["connectivity"]["wireless"] = True
        if re.search(r"\busb[ -]?c\b", joined, re.I):
            facts["connectivity"]["usb_c"] = True
        elif re.search(r"\busb\b", joined, re.I):
            facts["connectivity"]["usb"] = True
        if re.search(r"\b3[., ]5\s*mm\b|headphone jack|audio jack", joined, re.I):
            facts["connectivity"]["jack_3_5mm"] = True
        if re.search(r"2[ .]?4\s*ghz|radio ?frequency|\brf\b", joined, re.I):
            facts["connectivity"]["rf_2_4ghz"] = True
            facts["connectivity"]["wireless"] = True
        if re.search(r"\bwi[ -]?fi\b", joined, re.I):
            facts["connectivity"]["wifi"] = True
        if re.search(r"\bnfc\b", joined, re.I):
            facts["connectivity"]["nfc"] = True
        if re.search(r"\bwired\b|cableado|al[aá]mbric", joined, re.I):
            facts["connectivity"]["wired"] = True
        if re.search(r"\bwireless\b|inal[aá]mbric", joined, re.I):
            facts["connectivity"]["wireless"] = True

        # A clean host-connectivity field containing only wireless transports can prove
        # that the device connection is not wired. Do not infer this from microphone cables.
        if any(x in attr for x in ["connectivity", "conectividad", "conexion", "connection type"]):
            host_wireless = bool(re.search(r"bluetooth|wireless|inal[aá]mbric|2[ .]?4\s*ghz|\brf\b", val, re.I))
            host_wired = bool(re.search(r"usb[ -]?c|3[., ]5\s*mm|wired|cableado|al[aá]mbric", val, re.I))
            if host_wireless and not host_wired:
                facts["connectivity"]["wireless"] = True
                if facts["connectivity"]["wired"] is None:
                    facts["connectivity"]["wired"] = False

        # Battery relations.
        if re.search(r"battery|bater[ií]a", attr, re.I):
            explicit = _norm_bool(raw)
            if re.search(r"no battery|without battery|sin bater[ií]a|battery required\s*[:=]?\s*(?:no|false)", raw, re.I):
                facts["battery"]["present"] = False
            elif explicit is True or raw:
                facts["battery"]["present"] = True
            if any(x in attr for x in ["recharge", "recargable"]):
                if explicit is not None:
                    facts["battery"]["rechargeable"] = explicit
            if re.search(r"recharge|recargable|lithium|li[ -]?ion", raw, re.I):
                facts["battery"]["rechargeable"] = True
            cap = re.search(r"(\d+(?:[.,]\d+)?)\s*mAh\b", raw, re.I)
            if cap:
                facts["battery"]["capacity_mah"] = float(cap.group(1).replace(",", "."))
                facts["battery"]["present"] = True

        if ck == "battery_life" or re.search(r"battery life|play time|runtime|autonom", attr, re.I):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hours?|horas?)\b", raw, re.I)
            runtime = float(m.group(1).replace(",", ".")) if m else _number(raw)
            if runtime is not None:
                facts["battery"]["runtime_hours"] = runtime
                if facts["battery"]["present"] is None:
                    facts["battery"]["present"] = True

        # IP rating promotion into independent dust/water components.
        m = re.search(r"\bIP\s*([0-6X])([0-9K])\b", raw, re.I)
        if not m:
            m = re.search(r"\bIP\s*([0-6X])([0-9K])\b", ev.attribute, re.I)
        if m:
            rating = f"IP{m.group(1).upper()}{m.group(2).upper()}"
            facts["durability"]["ip_rating"] = rating
            facts["durability"]["dust_rating"] = None if m.group(1).upper() == "X" else int(m.group(1))
            facts["durability"]["water_rating"] = int(m.group(2)) if m.group(2).isdigit() else m.group(2).upper()

        if re.search(r"\bin[ -]?ear\b|intraaural", joined, re.I):
            facts["form_factor"] = "in-ear"
        elif re.search(r"\bon[ -]?ear\b|supraaural", joined, re.I):
            facts["form_factor"] = "on-ear"
        elif re.search(r"\bover[ -]?ear\b|circumaural", joined, re.I):
            facts["form_factor"] = "over-ear"

        if any(x in attr for x in ["activity", "actividad", "sport", "segment", "use", "uso"]):
            if re.search(r"sport|deport", val, re.I):
                facts["semantic_segment"] = "sports"
            elif re.search(r"gaming|gamer|juego", val, re.I):
                facts["semantic_segment"] = "gaming"

        if re.search(r"driver|transductor|altavoz", attr, re.I):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*mm\b", raw, re.I)
            if m:
                facts["driver_size_mm"] = float(m.group(1).replace(",", "."))

        if ck == "weight" or re.fullmatch(r"(?:product )?weight|peso(?: del producto)?", attr):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*g\b", raw, re.I)
            if m:
                facts["product"]["weight_g"] = float(m.group(1).replace(",", "."))

        if any(x in attr for x in ["package contents", "contenido del paquete", "what's in the box", "included items"]):
            if raw:
                facts["package"]["contents"] = raw
        if any(x in attr for x in ["feature", "caracteristica"]):
            if raw and raw not in facts["features"]:
                facts["features"].append(raw)

    # Closed-world implications only when facts are explicit enough.
    bt = facts["connectivity"]["bluetooth"]
    if bt["version"] is not None:
        bt["present"] = True
        facts["connectivity"]["wireless"] = True
    if facts["connectivity"]["usb_c"] or facts["connectivity"]["jack_3_5mm"]:
        if facts["connectivity"]["wired"] is None:
            facts["connectivity"]["wired"] = True
    if facts["battery"]["runtime_hours"] is not None and facts["battery"]["present"] is None:
        facts["battery"]["present"] = True
    if facts["battery"]["present"] is False:
        facts["battery"]["rechargeable"] = False
        facts["battery"]["runtime_hours"] = None
    return facts


def canonical_invariant_errors(facts: dict[str, Any]) -> list[str]:
    """Return semantic inconsistencies that must never silently reach marketplace mapping."""
    errors: list[str] = []
    conn = facts.get("connectivity", {})
    bt = conn.get("bluetooth", {})
    battery = facts.get("battery", {})
    durability = facts.get("durability", {})

    if bt.get("version") is not None and bt.get("present") is not True:
        errors.append("bluetooth_version_without_presence")
    if durability.get("ip_rating") == "IP65" and durability.get("water_rating") != 5:
        errors.append("ip65_without_water_rating_5")
    if battery.get("runtime_hours") is not None and battery.get("present") is False:
        errors.append("battery_runtime_with_battery_absent")
    if conn.get("wired") is True and conn.get("wireless") is True and bt.get("present") is False and not conn.get("rf_2_4ghz"):
        errors.append("wired_and_wireless_without_wireless_transport")
    return errors
