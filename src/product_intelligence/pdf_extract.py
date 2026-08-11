from __future__ import annotations
import io, re, requests
import fitz
from .models import Evidence
from .web_fetch import UA

def download_bytes(url: str, timeout: int=35) -> bytes:
    r=requests.get(url, timeout=timeout, headers={"User-Agent": UA})
    r.raise_for_status(); return r.content

def extract_pdf(url: str, match_level: str="HIGH", confidence: float=.90) -> tuple[str, list[Evidence]]:
    data=download_bytes(url)
    doc=fitz.open(stream=data, filetype="pdf")
    pages=[]; evidence=[]
    for i,page in enumerate(doc):
        txt=page.get_text("text") or ""
        pages.append(txt)
        # conservative key:value lines; keeps raw evidence instead of hallucinating schema
        for line in txt.splitlines():
            m=re.match(r"^\s*([^:]{2,80})\s*:\s*(.{1,180})\s*$", line)
            if m:
                evidence.append(Evidence(attribute=m.group(1).strip(), raw_value=m.group(2).strip(), normalized_value=m.group(2).strip(),
                                         source_url=url, source_type="official_pdf", page=i+1, match_level=match_level, confidence=confidence))
    return "\n".join(pages), evidence

def optional_docling_extract(path: str) -> str | None:
    try:
        from docling.document_converter import DocumentConverter
        result=DocumentConverter().convert(path)
        return result.document.export_to_markdown()
    except Exception:
        return None
