from __future__ import annotations

from dataclasses import replace
from threading import RLock

from . import batch as batch_module


_BASE_SCRAPE_ITEM = batch_module.scrape_item
_BASE_RUN_BATCH = batch_module.run_batch
_RUN_LOCK = RLock()
_PLAN_LOCK = RLock()
_DESKTOP_REVIEWED_URLS: list[list[str]] = []
_DESKTOP_REVIEW_FLAGS: list[bool] = []


def set_desktop_review_plan(reviewed_pdf_urls_by_index, pdf_review_flags) -> None:
    """Snapshot the UI review plan for the next desktop Excel run."""
    global _DESKTOP_REVIEWED_URLS, _DESKTOP_REVIEW_FLAGS
    urls = [list(dict.fromkeys(str(u) for u in (rows or []) if str(u).strip())) for rows in (reviewed_pdf_urls_by_index or [])]
    flags = [bool(value) for value in (pdf_review_flags or [])]
    with _PLAN_LOCK:
        _DESKTOP_REVIEWED_URLS = urls
        _DESKTOP_REVIEW_FLAGS = flags


def _desktop_review_plan() -> tuple[list[list[str]], list[bool]]:
    with _PLAN_LOCK:
        return [list(rows) for rows in _DESKTOP_REVIEWED_URLS], list(_DESKTOP_REVIEW_FLAGS)


def scrape_item_with_review(
    item,
    out_dir: str,
    *,
    approved_urls: list[str] | tuple[str, ...] | None,
    enforced: bool,
    **kwargs,
):
    """Run one existing scrape item with an optional user-enforced PDF allow-list.

    Web/HTML acquisition is untouched. For an enforced product only, approved PDFs are
    inserted as explicit manual candidates, HTML pages cannot auto-follow PDFs, and
    direct/gap PDF discovery returns no additional documents.
    """
    if not enforced:
        return _BASE_SCRAPE_ITEM(item, out_dir, **kwargs)

    approved = list(dict.fromkeys(str(url).strip() for url in (approved_urls or []) if str(url).strip()))
    existing = list(getattr(item, "source_urls", None) or [])
    reviewed_item = replace(item, source_urls=list(dict.fromkeys([*existing, *approved])))

    with _RUN_LOCK:
        original_pipeline = batch_module.ProductPipeline
        original_ingest = batch_module._ingest_direct_documents

        class ReviewedProductPipeline(original_pipeline):
            def process_url(self, *args, **process_kwargs):
                process_kwargs["include_pdfs"] = False
                return super().process_url(*args, **process_kwargs)

        def no_automatic_documents(*_args, **_kwargs):
            return []

        batch_module.ProductPipeline = ReviewedProductPipeline
        batch_module._ingest_direct_documents = no_automatic_documents
        try:
            return _BASE_SCRAPE_ITEM(reviewed_item, out_dir, **kwargs)
        finally:
            batch_module.ProductPipeline = original_pipeline
            batch_module._ingest_direct_documents = original_ingest


def run_batch_with_review(*args, reviewed_pdf_urls_by_index=None, pdf_review_flags=None, **kwargs):
    """Desktop-compatible `run_batch` wrapper with per-product PDF review enforcement."""
    if reviewed_pdf_urls_by_index is None and pdf_review_flags is None:
        reviewed_pdf_urls_by_index, pdf_review_flags = _desktop_review_plan()

    urls_plan = [list(rows or []) for rows in (reviewed_pdf_urls_by_index or [])]
    flags_plan = [bool(value) for value in (pdf_review_flags or [])]
    if not any(flags_plan):
        return _BASE_RUN_BATCH(*args, **kwargs)

    with _RUN_LOCK:
        original_scrape = batch_module.scrape_item
        cursor = {"value": 0}

        def reviewed_scrape(item, out_dir, **scrape_kwargs):
            index = cursor["value"]
            cursor["value"] += 1
            approved = urls_plan[index] if index < len(urls_plan) else []
            enforced = flags_plan[index] if index < len(flags_plan) else False
            return scrape_item_with_review(
                item,
                out_dir,
                approved_urls=approved,
                enforced=enforced,
                **scrape_kwargs,
            )

        batch_module.scrape_item = reviewed_scrape
        try:
            return _BASE_RUN_BATCH(*args, **kwargs)
        finally:
            batch_module.scrape_item = original_scrape
