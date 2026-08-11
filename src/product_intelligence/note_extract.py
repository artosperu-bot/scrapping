from __future__ import annotations

import re

NOTE_PATTERNS = {
    "usage_limitation": [r"not intended for", r"not designed for", r"no esta destinado", r"no está destinado", r"not for server"],
    "performance_condition": [r"performance may vary", r"speed may vary", r"rendimiento puede variar", r"velocidad puede variar", r"based on .*performance"],
    "compatibility_advice": [r"consult your .*manufacturer", r"consulte .*fabricante", r"before installing"],
    "capacity_disclaimer": [r"actual available capacity", r"capacity .* formatting", r"capacidad real disponible"],
    "endurance_methodology": [r"total bytes written", r"jedec", r"jesd219"],
    "warranty_condition": [r"limited warranty", r"percentage used", r"garantia limitada", r"garantía limitada"],
}


def extract_technical_notes(text: str, source_url: str | None = None) -> list[dict]:
    clean = re.sub(r"\s+", " ", text or " ").strip()
    # split conservatively; keep notes short enough for auditing
    sentences = re.split(r"(?<=[.!?])\s+|\n+", clean)
    out=[]; seen=set()
    for sentence in sentences:
        s=sentence.strip()
        if len(s) < 18 or len(s) > 700:
            continue
        low=s.lower()
        for kind, pats in NOTE_PATTERNS.items():
            if any(re.search(p, low, re.I) for p in pats):
                key=(kind, low)
                if key not in seen:
                    seen.add(key)
                    out.append({"type":kind,"text":s,"source":source_url,"confidence":0.90})
                break
    return out
