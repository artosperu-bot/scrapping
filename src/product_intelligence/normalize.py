from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from .models import Evidence, ProductRecord, ProductIdentity

# Canonical vocabulary is intentionally language-neutral. Add aliases, not product rules.
ALIASES = {
    "mpn": ["mpn", "manufacturer part number", "part number", "part no", "pn", "codigo fabricante", "código fabricante"],
    "ean": ["ean", "ean13", "ean-13", "codigo ean", "código ean", "codigo de barras", "código de barras", "barcode"],
    "upc": ["upc", "upc-a"],
    "gtin": ["gtin", "gtin14", "gtin-14", "global trade item number"],
    "model": ["model", "modelo", "model number", "numero de modelo", "número de modelo"],
    "brand": ["brand", "marca", "manufacturer", "fabricante"],
    "capacity": ["capacity", "capacities", "capacidad", "capacidades", "storage capacity", "capacidad almacenamiento", "capacidad de almacenamiento"],
    "form_factor": ["form factor", "factor de forma", "formato"],
    "interface": ["interface", "interfaz", "host interface", "conexion", "conexión", "connectivity"],
    "sequential_read_speed": ["sequential read", "sequential read speed", "sequential reading", "lectura secuencial", "velocidad de lectura secuencial"],
    "sequential_write_speed": ["sequential write", "sequential write speed", "sequential writing", "escritura secuencial", "velocidad de escritura secuencial"],
    "nand_type": ["nand", "nand type", "flash type", "tipo nand", "tipo de nand", "memoria nand"],
    "endurance_tbw": ["total bytes written", "tbw", "endurance tbw", "resistencia tbw", "bytes escritos totales"],
    "storage_temperature": ["storage temperature", "temperatura de almacenamiento"],
    "storage_temperature_min": ["minimum storage temperature", "storage temperature min", "temperatura minima de almacenamiento", "temperatura mínima de almacenamiento"],
    "storage_temperature_max": ["maximum storage temperature", "storage temperature max", "temperatura maxima de almacenamiento", "temperatura máxima de almacenamiento"],
    "operating_temperature": ["operating temperature", "temperatura de funcionamiento", "temperatura operativa"],
    "operating_temperature_min": ["minimum operating temperature", "operating temperature min", "temperatura minima de funcionamiento", "temperatura mínima de funcionamiento"],
    "operating_temperature_max": ["maximum operating temperature", "operating temperature max", "temperatura maxima de funcionamiento", "temperatura máxima de funcionamiento"],
    "dimensions": ["dimensions", "dimension", "dimensiones", "product dimensions", "size", "medidas"],
    "width": ["width", "ancho"],
    "length": ["length", "largo", "longitud"],
    "height": ["height", "alto", "altura"],
    "thickness": ["thickness", "espesor", "grosor"],
    "weight": ["weight", "peso", "net weight", "peso neto"],
    "vibration_non_operating": ["vibration non-operating", "non-operating vibration", "vibracion sin funcionamiento", "vibración sin funcionamiento"],
    "vibration_frequency_range": ["vibration frequency range", "rango frecuencia vibracion", "rango de frecuencia de vibración"],
    "mtbf": ["mtbf", "mean time between failures", "tiempo medio entre fallos", "tiempo medio entre fallas"],
    "warranty": ["warranty", "warranty/support", "garantia", "garantía", "garantia del producto", "garantía del producto"],
    "warranty_duration": ["warranty duration", "duracion de garantia", "duración de garantía"],
    "warranty_type": ["warranty type", "tipo de garantia", "tipo de garantía"],
    "technical_support": ["technical support", "soporte tecnico", "soporte técnico"],
    "ram": ["ram", "memoria ram", "system memory"],
    "battery_capacity": ["battery capacity", "capacidad de batería", "capacidad bateria"],
    "processor": ["processor", "cpu", "procesador", "chipset"],
    "screen": ["display", "screen", "pantalla"],
    "color": ["color", "colour", "color variant", "variant color", "color de la variante", "colorvariant", "color basic variant", "colorbasico variant", "colorbasicvariant"],
    "country_of_origin": ["country of origin", "country of production", "pais de produccion", "país de producción", "pais de origen", "país de origen"],
    "package_contents": ["package contents", "what's in the box", "included accessories", "contenido del paquete", "contenido de la caja"],

    "bluetooth": ["bluetooth", "cuenta con bluetooth", "has bluetooth"],
    "battery_life": ["battery life", "autonomy", "autonomia", "autonomía", "duracion de bateria", "duración de batería"],
    "power": ["power", "audio power", "potencia", "potencia de audio", "speaker power"],
    "headphone_type": ["headphone type", "tipo de auricular", "earphone type"],
    "water_resistance": ["water resistance", "water resistant", "resistente al agua", "resistencia al agua"],
    "power_source": ["power source", "alimentacion", "alimentación", "tipo de alimentacion"],
    "output_type": ["output type", "tipo de salida", "audio output"],
    "features": ["features", "characteristics", "caracteristicas", "características"],
    "package_width": ["package width", "packed width", "ancho del paquete", "ancho embalado"],
    "package_length": ["package length", "packed length", "largo del paquete", "largo embalado"],
    "package_height": ["package height", "packed height", "alto del paquete", "alto embalado"],
    "package_weight": ["package weight", "shipping weight", "gross weight", "peso del paquete", "peso embalado"],
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def key_norm(s: str) -> str:
    s = _strip_accents(str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def canonical_key(label: str) -> str | None:
    n = key_norm(label)
    for key, vals in ALIASES.items():
        if n == key_norm(key) or any(n == key_norm(v) for v in vals):
            return key
    return None


def build_record(identity: ProductIdentity, evidence: list[Evidence], sources: list[str]) -> ProductRecord:
    grouped = defaultdict(list)
    additional: dict[str, list[Evidence]] = {}
    for ev in evidence:
        ck = canonical_key(ev.attribute)
        if ck:
            grouped[ck].append(ev)
        else:
            additional.setdefault(ev.attribute, []).append(ev)

    specs = {}
    conflicts = []
    for key, evs in grouped.items():
        evs = sorted(evs, key=lambda e: e.confidence, reverse=True)
        top = evs[0]
        specs[key] = {
            "value": top.normalized_value,
            "raw_value": top.raw_value,
            "unit": top.unit,
            "source": top.source_url,
            "source_type": top.source_type,
            "selector": top.selector,
            "confidence": top.confidence,
        }
        vals = {str(e.normalized_value).strip().lower() for e in evs if e.normalized_value is not None}
        if len(vals) > 1:
            conflicts.append({"attribute": key, "values": [
                {"value": e.normalized_value, "source": e.source_url, "confidence": e.confidence}
                for e in evs[:12]
            ]})
    return ProductRecord(
        identity=identity,
        specifications=specs,
        additional_attributes=additional,
        evidence=evidence,
        sources=list(dict.fromkeys(sources)),
        conflicts=conflicts,
    )
