from importlib import import_module, util
from pathlib import Path
import fitz
from product_intelligence.models import ProductIdentity

def _module(name):
    full=f"product_intelligence.{name}"
    assert util.find_spec(full) is not None, f"missing module: {full}"
    return import_module(full)

def _pdf(path: Path, text: str):
    doc=fitz.open(); page=doc.new_page()
    if text: page.insert_text((72,72), text)
    doc.save(path); doc.close(); return path

def test_pdf_discovery_and_payload_detection():
    m=_module("pdf_evidence")
    html='<a href="/files/spec.pdf">Ficha técnica</a><a href="/download?id=7">Manual PDF</a>'
    rows=m.discover_pdf_candidates(html,"https://vendor.example/product")
    assert [r.url for r in rows]==["https://vendor.example/files/spec.pdf","https://vendor.example/download?id=7"]
    assert m.is_pdf_payload("application/octet-stream",b"%PDF-1.7\n")
    assert not m.is_pdf_payload("text/html",b"<html></html>")

def test_pdf_identity_accepts_exact_and_rejects_wrong_model():
    m=_module("pdf_evidence"); identity=ProductIdentity(brand="Acme",model="ZX-410",mpn="AC-ZX410")
    ok=m.validate_pdf_identity(identity,"ACME ZX-410 / AC-ZX410 Technical Specifications")
    wrong=m.validate_pdf_identity(identity,"ACME ZX-510 Technical Specifications")
    assert ok.accepted and ok.confidence>=.9
    assert not wrong.accepted

def test_extract_prefers_text_and_ocr_only_for_blank(tmp_path):
    m=_module("pdf_extract")
    pages=m.extract_pdf_pages(_pdf(tmp_path/"spec.pdf","Peso: 252 g\nImpedancia: 32 ohm"))
    assert pages[0].method=="TEXT" and "Peso" in pages[0].text
    calls=[]
    def ocr_page(page_number,image_bytes):
        calls.append((page_number,len(image_bytes))); return "Peso: 252 g"
    blank=m.extract_pdf_pages(_pdf(tmp_path/"scan.pdf",""),ocr_page=ocr_page)
    assert blank[0].method=="OCR" and blank[0].text=="Peso: 252 g" and calls[0][0]==1

def test_alignment_maps_aliases_keeps_provenance_and_rejects_unrelated(tmp_path):
    ex=_module("pdf_extract"); al=_module("pdf_attribute_alignment")
    pages=[ex.ExtractedPdfPage(page=2,text="Tiempo de reproducción de música: 22 horas\nPeso: 252 g",method="TEXT")]
    ev=al.align_pdf_attributes(pages,["Autonomía","Peso del producto"],"https://vendor.example/spec.pdf",str(tmp_path/"spec.pdf"))
    by={x.attribute:x for x in ev}
    assert by["Autonomía"].raw_value=="22 horas" and by["Peso del producto"].raw_value=="252 g"
    assert by["Autonomía"].page==2 and by["Autonomía"].source_type=="pdf"
    assert "method=TEXT" in (by["Autonomía"].selector or "") and "spec.pdf" in (by["Autonomía"].selector or "")
    unrelated=al.align_pdf_attributes([ex.ExtractedPdfPage(page=1,text="Tiempo de carga: 2 horas",method="TEXT")],["Peso del producto"],"x","x.pdf")
    assert unrelated==[]
