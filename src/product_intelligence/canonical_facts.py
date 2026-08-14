from __future__ import annotations

import re
from typing import Any

from .models import ProductRecord
from .normalize import canonical_key, key_norm
from .source_authority import effective_quality


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


def _bluetooth_version(attribute: str, raw: str) -> str | None:
    """Return a Bluetooth protocol version only from version-shaped evidence."""
    attr = key_norm(attribute)
    raw_text = str(raw or "").strip()
    if re.search(r"bluetooth\s*(?:version|versi[oó]n)", attr, re.I) or attr in {"bluetooth", "bluetooth version", "version bluetooth", "version de bluetooth"}:
        m = re.fullmatch(r"\s*(?:bluetooth\s*)?(\d(?:\.\d)?)\s*", raw_text, re.I)
        return m.group(1) if m else None
    m = re.search(r"\bbluetooth\s*(?:version\s*)?(\d(?:\.\d)?)\b", raw_text, re.I)
    return m.group(1) if m else None


def _host_connectivity_attribute(attribute: str) -> bool:
    attr = key_norm(attribute)
    return any(x in attr for x in [
        "connectivity", "conectividad", "conexion", "connection", "interface", "interfaz",
        "audio connector", "connector", "conector", "host port", "host interface",
        "wireless", "network", "red inalambrica", "red inalámbrica",
    ])


def _charging_or_accessory_context(attribute: str, raw: str) -> bool:
    joined = key_norm(f"{attribute} {raw}")
    return any(x in joined for x in [
        "charging", "charge cable", "charging cable", "cable de carga", "recarga",
        "package contents", "what s in the box", "contenido del paquete", "included items",
        "battery charging", "usb charging",
    ])


def _proprietary_rf_context(attribute: str, raw: str) -> bool:
    joined = key_norm(f"{attribute} {raw}")
    if "bluetooth" in joined and not re.search(
        r"dongle|receiver|receptor|wireless adapter|adaptador|proprietary|propietari|usb wireless",
        joined,
        re.I,
    ):
        return False
    return bool(re.search(r"\b(?:rf|radio ?frequency|2[ .]?4\s*ghz)\b", joined, re.I))


def _select_authoritative_candidate(canonical: str, candidates: list[tuple[Any, Any]], *, min_confidence: float = .70):
    """Choose a value only when its evidence is eligible and strictly strongest."""
    ranked = []
    for ev, value in candidates:
        confidence = float(getattr(ev, "confidence", 0.0) or 0.0)
        if confidence < min_confidence:
            continue
        rank, quality = effective_quality(canonical, ev, confidence)
        ranked.append(((rank, quality), value))
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0], reverse=True)
    top_score, top_value = ranked[0]
    if len(ranked) > 1:
        second_score, second_value = ranked[1]
        if second_value != top_value and second_score == top_score:
            return None
    return top_value


def build_canonical_facts(rec: ProductRecord) -> dict[str, Any]:
    """Build conservative reusable product facts from filtered/deduplicated evidence."""
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
    runtime_candidates = []
    ip_candidates = []

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

        if "bluetooth" in attr:
            explicit = _norm_bool(raw)
            if explicit is not None and not re.search(r"power|signal|frequency|frecuencia|transmitter|transmisor|dbm|mw", attr, re.I):
                facts["connectivity"]["bluetooth"]["present"] = explicit
            version = _bluetooth_version(ev.attribute, raw)
            if version:
                facts["connectivity"]["bluetooth"]["version"] = version
                facts["connectivity"]["bluetooth"]["present"] = True

        joined = f"{attr} {val}"
        if "bluetooth" in val and any(x in attr for x in ["connect", "conexion", "technology", "wireless"]):
            facts["connectivity"]["bluetooth"]["present"] = True
            facts["connectivity"]["wireless"] = True

        host_connectivity = _host_connectivity_attribute(ev.attribute)
        accessory_context = _charging_or_accessory_context(ev.attribute, raw)
        if host_connectivity and not accessory_context and re.search(r"\busb[ -]?c\b", joined, re.I):
            facts["connectivity"]["usb_c"] = True
        elif host_connectivity and not accessory_context and re.search(r"\busb\b", joined, re.I):
            facts["connectivity"]["usb"] = True
        if host_connectivity and re.search(r"\b3[., ]5\s*mm\b|headphone jack|audio jack", joined, re.I):
            facts["connectivity"]["jack_3_5mm"] = True
        if _proprietary_rf_context(ev.attribute, raw):
            facts["connectivity"]["rf_2_4ghz"] = True
            facts["connectivity"]["wireless"] = True
        if host_connectivity and re.search(r"\bwi[ -]?fi\b", joined, re.I):
            facts["connectivity"]["wifi"] = True
        if host_connectivity and re.search(r"\bnfc\b", joined, re.I):
            facts["connectivity"]["nfc"] = True
        if host_connectivity and re.search(r"\bwired\b|cableado|al[aá]mbric", joined, re.I):
            facts["connectivity"]["wired"] = True
        if re.search(r"\bwireless\b|inal[aá]mbric", joined, re.I):
            facts["connectivity"]["wireless"] = True

        if any(x in attr for x in ["connectivity", "conectividad", "conexion", "connection type"]):
            host_wireless = bool(re.search(r"bluetooth|wireless|inal[aá]mbric|2[ .]?4\s*ghz|\brf\b", val, re.I))
            host_wired = bool(re.search(r"usb[ -]?c|3[., ]5\s*mm|wired|cableado|al[aá]mbric", val, re.I))
            if host_wireless and not host_wired:
                facts["connectivity"]["wireless"] = True

        if re.search(r"battery|bater[ií]a", attr, re.I):
            explicit = _norm_bool(raw)
            battery_context = f"{attr} {val}"
            if explicit is False or re.search(r"no battery|without battery|sin bater[ií]a|battery required\s*(?:no|false)", battery_context, re.I):
                facts["battery"]["present"] = False
            elif explicit is True or raw:
                facts["battery"]["present"] = True
            if any(x in attr for x in ["recharge", "recargable"]) and explicit is not None:
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
                runtime_candidates.append((ev, runtime))

        m = re.search(r"\bIP\s*([0-6X])([0-9K])\b", raw, re.I)
        if not m:
            m = re.search(r"\bIP\s*([0-6X])([0-9K])\b", ev.attribute, re.I)
        if m:
            rating = f"IP{m.group(1).upper()}{m.group(2).upper()}"
            dust = m.group(1).upper()
            water = m.group(2).upper()
            ip_candidates.append((ev, (rating, None if dust == "X" else int(dust), int(water) if water.isdigit() else water)))

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

    runtime = _select_authoritative_candidate("battery_life", runtime_candidates)
    if runtime is not None:
        facts["battery"]["runtime_hours"] = runtime
        if facts["battery"]["present"] is None:
            facts["battery"]["present"] = True

    ip = _select_authoritative_candidate("ip_rating", ip_candidates)
    if ip is not None:
        rating, dust, water = ip
        facts["durability"]["ip_rating"] = rating
        facts["durability"]["dust_rating"] = dust
        facts["durability"]["water_rating"] = water

    bt = facts["connectivity"]["bluetooth"]
    if bt["version"] is not None:
        bt["present"] = True
        facts["connectivity"]["wireless"] = True
    if facts["connectivity"]["usb_c"] or facts["connectivity"]["jack_3_5mm"]:
        if facts["connectivity"]["wired"] is None:
            facts["connectivity"]["wired"] = True
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
