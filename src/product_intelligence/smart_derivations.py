from __future__ import annotations

import re
from typing import Any

from .attribute_resolver import iter_clean_evidence
from .field_derivations import *
from .field_derivations import derive_autonomy as _base_autonomy
from .field_derivations import derive_water_resistance as _base_water_resistance
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
    text=_clean_text(rec)
    wired=bool(re.search(r"\bwired\b|cableado|al[aá]mbric|usb[ -]?c wired",text,re.I))
    no_battery=bool(re.search(r"no battery|without battery|sin bater[ií]a|battery required\s*[:=]?\s*(no|false)",text,re.I))
    if wired and no_battery:
        return Derived(reason="NOT_APPLICABLE:wired_product_without_battery")
    return Derived(reason="INSUFFICIENT_EVIDENCE:autonomy_not_found")


def derive_water_resistance(rec: ProductRecord, options:list[Any]) -> Derived:
    direct=_base_water_resistance(rec,options)
    if direct.value not in (None,""):
        return direct

    option_map={key_norm(str(o)):str(o) for o in options}
    for ev,q in iter_clean_evidence(rec):
        attr=key_norm(ev.attribute)
        if not re.search(r"ip rating|ip code|certificaci[oó]n ip|water resistance|resistente al agua|^ip$",attr,re.I):
            continue
        value=str(ev.normalized_value if ev.normalized_value not in (None,"") else ev.raw_value)
        match=re.search(r"\bIP\s*([0-6])([0-9])\b",value,re.I)
        if not match:
            continue
        water_code="IPX"+match.group(2)
        normalized=key_norm(water_code)
        for option_key,option in option_map.items():
            if option_key==normalized or option_key.startswith(normalized+" "):
                return Derived(
                    option,
                    min(.98,max(.90,float(q or 0)+.02)),
                    "FOUND_DERIVED:water_component_from_full_ip_rating",
                    ev.source_url,
                    ev.attribute,
                    ev.raw_value,
                )
        return Derived(reason=f"NOT_AVAILABLE_IN_MARKETPLACE_OPTIONS:{water_code}")
    return direct
