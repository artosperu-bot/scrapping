from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel

from .excel_mapper_v8 import fill_excel_v8
from .models import ProductIdentity, ProductRecord
from .pipeline import ProductPipeline

app = FastAPI(title="Product Intelligence API", version="0.10.0")


class ScrapeRequest(BaseModel):
    url: str
    identity: ProductIdentity
    official_domain: str | None = None
    include_pdfs: bool = True
    include_images: bool = True
    browser_fallback: bool = True


@app.get("/health")
def health():
    return {"ok": True, "version": "0.10.0"}


@app.post("/scrape", response_model=ProductRecord)
def scrape(req: ScrapeRequest):
    return ProductPipeline().process_url(
        req.identity,
        req.url,
        official_domain=req.official_domain,
        include_pdfs=req.include_pdfs,
        include_images=req.include_images,
        browser_fallback=req.browser_fallback,
    )


@app.post("/fill-excel")
async def fill_excel_endpoint(
    template: UploadFile = File(...),
    records_json: UploadFile = File(...),
    overwrite: bool = False,
):
    base = Path("output/api")
    base.mkdir(parents=True, exist_ok=True)
    template_path = base / (template.filename or "template.xlsx")
    json_path = base / (records_json.filename or "records.json")
    template_path.write_bytes(await template.read())
    json_path.write_bytes(await records_json.read())

    obj = json.loads(json_path.read_text(encoding="utf-8"))
    obj = [obj] if isinstance(obj, dict) else obj
    records = [ProductRecord.model_validate(x) for x in obj]
    out = base / "completed.xlsx"
    trace = base / "trace.json"
    report = fill_excel_v8(str(template_path), str(out), records, overwrite=overwrite, trace_path=str(trace))
    return {
        "output": str(out),
        "trace": str(trace),
        "cells_filled": report["summary"]["written_count"],
    }
