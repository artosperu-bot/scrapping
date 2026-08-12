from __future__ import annotations

import re
from typing import Any

from .attribute_resolver import iter_clean_evidence
from .canonical_facts import build_canonical_facts
from .field_derivations import *
from .field_derivations import derive_autonomy as _base_autonomy
from .field_derivations import derive_water_resistance as _base_water_resistance
from .field_derivations import derive_power_source as _base_power_source
from .normalize import key_norm


def _clean_text(rec: ProductRecord) -> str:
    parts=[]
    for ev,_q in iter_clean_evidence(rec):
        parts.append(f"{ev.attribute} {ev.raw_value} {ev.normalized_value}")
    for value in [rec.identity.product_name,rec.identity.model,rec.identity.brand]:
        if value:parts.append(str(value))
    return key_norm("\n".join(parts))


def derive_autonomy(rec: ProductRecord) -> Derived:
    direct=_base_autonomy(rec)
    if direct.value not in (None,""):
        return direct
    facts=build_canonical_facts(rec)
    runtime=facts["battery"].get("runtime_hours")
    if runtime is not None:
        value=f"{runtime:g} h" if isinstance(runtime,(int,float)) else f"{runtime} h"
        return Derived(value,.94,"FOUND_DERIVED:canonical_battery_runtime")
    if facts["connectivity"].get("wired") is True and facts["battery"].get("present") is False:
        return Derived(reason="NOT_APPLICABLE:wired_product_without_battery")
    return Derived(reason="INSUFFICIENT_EVIDENCE:autonomy_not_found")


def derive_water_resistance(rec: ProductRecord, options:list[Any]) -> Derived:
    direct=_base_water_resistance(rec,options)
    if direct.value not in (None,""):
        return direct

    option_map={key_norm(str(o)):str(o) for o in options}
    facts=build_canonical_facts(rec)
    water=facts["durability"].get("water_rating")
    rating=facts["durability"].get("ip_rating")
    if water and str(water).isdigit():
        water_code="IPX"+str(water)
        normalized=key_norm(water_code)
        for option_key,option in option_map.items():
            if option_key==normalized or option_key.startswith(normalized+" "):
                return Derived(option,.94,"FOUND_DERIVED:water_component_from_full_ip_rating",evidence_raw=rating)
        return Derived(reason=f"NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS:{water_code}")
    return direct


def _allowed_option(options:list[Any], *aliases:str) -> str | None:
    optmap={key_norm(str(o)):str(o) for o in options}
    for alias in aliases:
        if key_norm(alias) in optmap:
            return optmap[key_norm(alias)]
    return None


def derive_connectivity(rec: ProductRecord, options:list[Any]) -> Derived:
    """Map canonical transport facts to marketplace options without mixing technologies."""
    facts=build_canonical_facts(rec)
    c=facts["connectivity"]
    chosen=[]
    def add(*aliases):
        value=_allowed_option(options,*aliases)
        if value and value not in chosen: chosen.append(value)

    if c.get("usb_c"): add("USB-C","USB C")
    elif c.get("usb"): add("USB")
    if c.get("jack_3_5mm"): add("Auxiliar 3.5mm","3.5 mm")
    if c["bluetooth"].get("present") is True: add("Bluetooth")
    if c.get("rf_2_4ghz"):
        add("Radiofrecuencia (RF)","RF")
        add("Inalámbrico","WF wireless")
    elif c.get("wireless") is True and c["bluetooth"].get("present") is not False:
        add("Inalámbrico","WF wireless")
    if c.get("wifi"): add("Wifi","Wi-Fi","Wifi 6")
    if c.get("nfc"): add("NFC")
    if c.get("wired") is True: add("Alámbrico","Cableado")

    if chosen:
        return Derived(", ".join(chosen),.96,"FOUND_MAPPED:connectivity_from_canonical_facts")
    return Derived(reason="INSUFFICIENT_EVIDENCE:connectivity_not_proven")


def derive_power_source(rec: ProductRecord, options:list[Any]) -> Derived:
    direct=_base_power_source(rec,options)
    facts=build_canonical_facts(rec)
    battery=facts["battery"]
    conn=facts["connectivity"]

    if battery.get("present") is True and battery.get("rechargeable") is True:
        value=_allowed_option(options,"Batería recargable","Bateria recargable")
        if value:return Derived(value,.94,"FOUND_DERIVED:rechargeable_battery_fact")
    if direct.value not in (None,""):
        return direct

    if battery.get("present") is False and conn.get("wired") is True and (conn.get("usb_c") or conn.get("usb")):
        value=_allowed_option(options,"USB","USB-C","USB C")
        if value:return Derived(value,.94,"FOUND_DERIVED:wired_usb_without_battery")
        return Derived(reason="NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS:USB")
    return direct
