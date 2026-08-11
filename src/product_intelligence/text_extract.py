from __future__ import annotations

import json
import re
from typing import Iterable

from .models import Evidence
from .normalize import ALIASES, canonical_key, key_norm

DASH = r"(?:-|–|—)"


def _compact(v: str) -> str:
    return re.sub(r"\s+", "", str(v).lower()).replace(",", "")


def _capacity_eq(a: str | None, b: str | None) -> bool:
    if not a or not b: return False
    aa, bb = _compact(a), _compact(b)
    # simple decimal equivalences common in storage labels
    swaps = {"1000gb":"1tb", "2000gb":"2tb", "4000gb":"4tb", "500gb":"500gb"}
    aa = swaps.get(aa, aa); bb = swaps.get(bb, bb)
    return aa == bb


def _ev(attr, value, source_url, source_type, match_level, confidence, selector=None):
    return Evidence(attribute=attr, raw_value=value, normalized_value=value, source_url=source_url,
                    source_type=source_type, match_level=match_level, confidence=confidence, selector=selector)


def extract_text_evidence(
    text: str,
    source_url: str,
    source_type: str,
    match_level: str,
    confidence: float,
    expected_capacity: str | None = None,
) -> list[Evidence]:
    """General line-oriented extractor for datasheets that do not use ':' separators.

    It uses the canonical multilingual vocabulary, not brand/model-specific selectors.
    It also preserves capacity-keyed read/write tables as structured additional evidence.
    """
    raw_lines=[re.sub(r"\s+", " ", x).strip() for x in (text or "").splitlines()]
    lines=[x for x in raw_lines if x]
    out=[]

    alias_pairs=[]
    for key, vals in ALIASES.items():
        for alias in [key.replace("_", " "), *vals]:
            alias_pairs.append((alias, key))
    alias_pairs.sort(key=lambda x: len(x[0]), reverse=True)

    readwrite_mode=False
    readwrite_rows=[]
    endurance_rows=[]
    for i,line in enumerate(lines):
        low=key_norm(line)
        if re.match(r"^sequential\s+read\s*/?\s*write", low) or re.match(r"^sequential\s+read\s+write", low):
            readwrite_mode=True
            continue

        if readwrite_mode:
            m=re.match(r"^\s*([0-9.]+\s*(?:GB|TB))\s*"+DASH+r"?\s*([0-9,]+)\s*/\s*([0-9,]+)\s*MB/s\s*$", line, re.I)
            if m:
                row={"capacity":m.group(1).replace(" ",""),"read_mb_s":int(m.group(2).replace(",","")),"write_mb_s":int(m.group(3).replace(",",""))}
                readwrite_rows.append(row)
                if _capacity_eq(expected_capacity,row["capacity"]):
                    out.append(_ev("sequential_read_speed",f'{row["read_mb_s"]} MB/s',source_url,source_type,match_level,confidence,"capacity_table"))
                    out.append(_ev("sequential_write_speed",f'{row["write_mb_s"]} MB/s',source_url,source_type,match_level,confidence,"capacity_table"))
                continue
            # Lines like "2TB - 4TB – 6,000/5,000MB/s"
            m=re.match(r"^\s*([0-9.]+\s*(?:GB|TB))\s*"+DASH+r"\s*([0-9.]+\s*(?:GB|TB))\s*"+DASH+r"\s*([0-9,]+)\s*/\s*([0-9,]+)\s*MB/s",line,re.I)
            if m:
                row={"capacity_range":[m.group(1).replace(" ",""),m.group(2).replace(" ","")],"read_mb_s":int(m.group(3).replace(",","")),"write_mb_s":int(m.group(4).replace(",",""))}
                readwrite_rows.append(row)
                continue
            # Stop when a new known spec label starts.
            if any(low.startswith(key_norm(a)+" ") or low==key_norm(a) for a,_ in alias_pairs):
                readwrite_mode=False

        matched=False
        for alias,key in alias_pairs:
            na=key_norm(alias)
            if low==na:
                # value may be on the next line if that line is not another label
                if i+1 < len(lines):
                    nxt=lines[i+1]
                    nnext=key_norm(nxt)
                    if not any(nnext==key_norm(a) for a,_ in alias_pairs):
                        out.append(_ev(key,nxt,source_url,source_type,match_level,confidence,"next_line"))
                matched=True; break
            if low.startswith(na+" "):
                # Preserve original spacing from line by cutting approximately at alias length.
                # Match normalized label tokens against punctuation/hyphen variations in source.
                toks=[re.escape(t) for t in na.split()]
                label_rx=r"^\s*" + r"[^A-Za-z0-9]+".join(toks)
                m=re.match(label_rx,line,re.I)
                if m:
                    value=line[m.end():].strip(" :\t")
                    value=re.sub(r"^[–—]\s*", "", value)
                else:
                    value=""
                if value:
                    out.append(_ev(key,value,source_url,source_type,match_level,confidence,"line_prefix"))
                matched=True; break

    # Capacity-keyed endurance/TBW tables often follow an Endurance heading.
    endurance_mode=False
    for line in lines:
        low=key_norm(line)
        if low.startswith("endurance") or low.startswith("total bytes written"):
            endurance_mode=True
            # Some PDFs put the first capacity on the same heading line.
        if endurance_mode:
            m=re.search(r"([0-9.]+\s*(?:GB|TB))\s*"+DASH+r"\s*([0-9,]+)\s*TB(?:W)?",line,re.I)
            if m:
                row={"capacity":m.group(1).replace(" ",""),"tbw":int(m.group(2).replace(",",""))}
                endurance_rows.append(row)
                if _capacity_eq(expected_capacity,row["capacity"]):
                    out.append(_ev("endurance_tbw",f'{row["tbw"]} TBW',source_url,source_type,match_level,min(1.0,confidence+0.02),"capacity_endurance_table"))
                continue
            if endurance_mode and any(low.startswith(key_norm(a)+" ") or low==key_norm(a) for a,_ in alias_pairs if key_norm(a) not in {"endurance","total bytes written","tbw"}):
                endurance_mode=False
    if endurance_rows:
        out.append(_ev("endurance_by_capacity",json.dumps(endurance_rows,ensure_ascii=False),source_url,source_type,match_level,confidence,"capacity_endurance_all"))

    if readwrite_rows:
        out.append(_ev("sequential_read_write_by_capacity",json.dumps(readwrite_rows,ensure_ascii=False),source_url,source_type,match_level,confidence,"capacity_table_all"))

    # Decompose common compound values into useful atomic attributes without losing raw evidence.
    extra=[]
    for e in list(out):
        k=canonical_key(e.attribute) or e.attribute
        v=str(e.normalized_value or "")
        if k in {"storage_temperature","operating_temperature"}:
            m=re.search(r"(-?\d+(?:\.\d+)?)\s*°?C\s*[~–—-]\s*(-?\d+(?:\.\d+)?)\s*°?C",v,re.I)
            if m:
                prefix="storage_temperature" if k=="storage_temperature" else "operating_temperature"
                extra += [_ev(prefix+"_min",m.group(1)+" °C",source_url,source_type,match_level,confidence,e.selector),
                          _ev(prefix+"_max",m.group(2)+" °C",source_url,source_type,match_level,confidence,e.selector)]
        elif k=="dimensions":
            nums=re.findall(r"(-?\d+(?:\.\d+)?)\s*mm",v,re.I)
            if len(nums)>=3:
                extra += [_ev("width",nums[0]+" mm",source_url,source_type,match_level,confidence,e.selector),
                          _ev("length",nums[1]+" mm",source_url,source_type,match_level,confidence,e.selector),
                          _ev("thickness",nums[2]+" mm",source_url,source_type,match_level,confidence,e.selector)]
        elif k=="vibration_non_operating":
            m=re.search(r"([0-9.]+\s*G).*?\(([0-9.]+\s*[-–—]\s*[0-9.]+\s*Hz)\)",v,re.I)
            if m:
                extra.append(_ev("vibration_frequency_range",m.group(2),source_url,source_type,match_level,confidence,e.selector))
        elif k=="warranty":
            dm=re.search(r"(\d+(?:\.\d+)?)\s*[- ]?year",v,re.I)
            if dm:
                extra.append(_ev("warranty_duration",dm.group(1)+" years",source_url,source_type,match_level,confidence,e.selector))
            if re.search(r"\blimited\b",v,re.I):
                extra.append(_ev("warranty_type","Limited warranty",source_url,source_type,match_level,confidence,e.selector))
            sm=re.search(r"(free\s+technical\s+support|technical\s+support)",v,re.I)
            if sm:
                extra.append(_ev("technical_support",sm.group(1),source_url,source_type,match_level,confidence,e.selector))
    out.extend(extra)

    # de-duplicate same attribute/value/source
    dedup=[]; seen=set()
    for e in out:
        key=(key_norm(e.attribute),str(e.normalized_value),e.source_url,e.selector)
        if key not in seen:
            seen.add(key); dedup.append(e)
    return dedup
