from __future__ import annotations

from dataclasses import dataclass
import re

from .models import ProductIdentity
from .normalize import key_norm


@dataclass(frozen=True)
class ProductClassification:
    category: str
    confidence: float
    signals: tuple[str, ...]


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", key_norm(str(value or "")).replace("_", " ").replace("-", " ")).strip()


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def classify_product(
    identity: ProductIdentity,
    *,
    description: str | None = None,
    required_fields=(),
) -> ProductClassification:
    """Classify by generic product/category signals, never by brand.

    This is intentionally conservative. A low-signal product remains GENERAL; no
    category guess can weaken the downstream product identity or evidence gates.
    """
    identity_text = " ".join(
        str(value or "")
        for value in (identity.product_name, identity.model, identity.variant)
        if value
    )
    text = _norm(f"{identity_text} {description or ''}")
    fields = _norm(" ".join(str(field or "") for field in required_fields or ()))
    combined = f"{text} {fields}".strip()

    profiles: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("ELECTRONIC_COMPONENT", ("electronic component", "integrated circuit", "microcontroller", "transistor", "mosfet", "resistor", "capacitor", "diode", "regulator ic", "sensor ic")),
        ("PC_COMPONENT", ("pc memory component", "ram module", "memory module", "ddr4", "ddr5", "ssd", "nvme", "graphics card", "gpu", "motherboard", "pc component")),
        ("PRINTER", ("printer", "impresora", "multifunction printer", "laser printer", "inkjet printer", "print resolution", "toner", "ink cartridge")),
        ("SMARTPHONE", ("smartphone", "cell phone", "mobile phone", "telefono movil", "teléfono móvil", "celular")),
        ("COMPUTER", ("laptop", "notebook", "desktop pc", "laptop pc", "workstation", "all in one pc", "computer")),
        ("NETWORK", ("wifi router", "wi fi router", "router", "network switch", "ethernet switch", "access point", "network equipment", "mesh wifi")),
        ("AUDIO", ("headphones", "headphone", "headset", "earbuds", "earphones", "speaker", "microphone", "audio device")),
        ("ACCESSORY", ("mouse accessory", "wireless mouse", "computer mouse", "keyboard", "dock", "docking station", "charger", "charging cable", "usb cable", "accessory")),
    )

    for category, terms in profiles:
        matched = tuple(term for term in terms if term in combined)
        if matched:
            confidence = min(1.0, .82 + .05 * max(0, len(matched) - 1))
            return ProductClassification(category, confidence, matched)

    return ProductClassification("GENERAL", .55 if combined else .25, ("NO_STRONG_CATEGORY_SIGNAL",))
