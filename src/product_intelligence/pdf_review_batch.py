from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
import re
from threading import RLock

from . import batch as batch_module
from .pdf_pipeline import discover_pdf_documents, resolve_pdf_identity


_BASE_SCRAPE_ITEM = batch_module.scrape_item
_BASE_RUN_BATCH = batch_module.run_batch
_BASE_PROCESS_PDF = batch_module.process_pdf_document
_RUN_LOCK = RLock()
_PLAN_LOCK = RLock()
_DESKTOP_REVIEWED_URLS: list[list[str]] = []
_DESKTOP_REVIEW_FLAGS: list[bool] = []
_PDF_DOWNLOAD_DIR: ContextVar[Path | None] = ContextVar("desktop_pdf_download_dir", default=None)


def set_desktop_review_plan(reviewed_pdf_urls_by_index, pdf_review_flags) -> None:
    """Snapshot the explicit user review decision for the next real Excel run."""
    global _DESKTOP_REVIEWED_URLS, _DESKTOP_REVIEW_FLAGS
    urls = [list(dict.fromkeys(str(u) for u in (rows or []) if str(u).strip())) for rows in (reviewed_pdf_urls_by_index or [])]
    flags = [bool(value) for value in (pdf_review_flags or [])]
    with _PLAN_LOCK:
        _DESKTOP_REVIEWED_URLS = urls
        _DESKTOP_REVIEW_FLAGS = flags


def _desktop_review_plan() -> tuple[list[list[str]], list[bool]]:
    with _PLAN_LOCK:
        return [list(rows) for rows in _DESKTOP_REVIEWED_URLS], list(_DESKTOP_REVIEW_FLAGS)


def _persistent_pdf_dir(out_dir: str, identity) -> Path:
    """Return the user-visible PDF evidence directory for one real desktop product."""
    root = Path(out_dir).parent
    raw = str(
        getattr(identity, "mpn", None)
        or getattr(identity, "ean", None)
        or getattr(identity, "upc", None)
        or getattr(identity, "gtin", None)
        or getattr(identity, "model", None)
        or getattr(identity, "product_name", None)
        or "producto"
    )
    label = re.sub(r"[^A-Za-z0-9._-]+", "_", raw)
    folder = root / "pdf_evidence" / label
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _shared_discover(identity, *args, **kwargs):
    limit = int(kwargs.pop("limit", 6) or 6)
    timeout = int(kwargs.pop("timeout", 8) or 8)
    trace = kwargs.pop("trace", None)
    _resolved, rows = discover_pdf_documents(identity, limit=limit, timeout=timeout, trace=trace)
    return rows


def _shared_process_pdf(identity, url, *args, **kwargs):
    """Keep enriched identity and retain the PDF when called by the real desktop batch."""
    download_dir = _PDF_DOWNLOAD_DIR.get()
    if download_dir is not None and kwargs.get("download_dir") is None:
        kwargs["download_dir"] = download_dir
    effective = resolve_pdf_identity(identity, timeout=8).identity
    return _BASE_PROCESS_PDF(effective, url, *args, **kwargs)


def scrape_item_with_review(
    item,
    out_dir: str,
    *,
    approved_urls: list[str] | tuple[str, ...] | None,
    enforced: bool,
    **kwargs,
):
    """Run one existing scrape item with an optional user-enforced PDF allow-list.

    `enforced=True` means REVIEW_CONFIRMED. An empty approved list is therefore a
    valid explicit decision and must never restart automatic PDF discovery.
    """
    token = None
    if _PDF_DOWNLOAD_DIR.get() is None:
        token = _PDF_DOWNLOAD_DIR.set(_persistent_pdf_dir(out_dir, item.identity))

    try:
        if not enforced:
            return _BASE_SCRAPE_ITEM(item, out_dir, **kwargs)

        approved = list(dict.fromkeys(str(url).strip() for url in (approved_urls or []) if str(url).strip()))
        approved_set = set(approved)

        existing = [
            str(url).strip()
            for url in (getattr(item, "source_urls", None) or [])
            if str(url).strip() and not batch_module._looks_like_pdf_url(str(url).strip())
        ]
        source_url = getattr(item, "source_url", None)
        if source_url and batch_module._looks_like_pdf_url(source_url) and source_url not in approved_set:
            source_url = None
        reviewed_item = replace(
            item,
            source_url=source_url,
            source_urls=list(dict.fromkeys([*existing, *approved])),
        )

        with _RUN_LOCK:
            original_pipeline = batch_module.ProductPipeline
            original_ingest = batch_module._ingest_direct_documents
            original_process_pdf = batch_module.process_pdf_document

            class ReviewedProductPipeline(original_pipeline):
                def process_url(self, *args, **process_kwargs):
                    process_kwargs["include_pdfs"] = False
                    return super().process_url(*args, **process_kwargs)

            def no_automatic_documents(*_args, **_kwargs):
                return []

            def reviewed_process_pdf(identity, url, *args, **process_kwargs):
                if str(url) not in approved_set:
                    raise ValueError("PDF_NOT_SELECTED_BY_USER")
                from .pdf_review import provenance_for_review_url

                provenance = provenance_for_review_url(str(url))
                if provenance is not None:
                    process_kwargs["provenance"] = provenance
                download_dir = _PDF_DOWNLOAD_DIR.get()
                if download_dir is not None and process_kwargs.get("download_dir") is None:
                    process_kwargs["download_dir"] = download_dir
                effective = resolve_pdf_identity(identity, timeout=8).identity
                # Use the processor active when this reviewed call began. Tests and
                # downstream adapters may intentionally replace it; selection semantics
                # must not bypass that binding.
                return original_process_pdf(effective, url, *args, **process_kwargs)

            batch_module.ProductPipeline = ReviewedProductPipeline
            batch_module._ingest_direct_documents = no_automatic_documents
            batch_module.process_pdf_document = reviewed_process_pdf
            try:
                return _BASE_SCRAPE_ITEM(reviewed_item, out_dir, **kwargs)
            finally:
                batch_module.ProductPipeline = original_pipeline
                batch_module._ingest_direct_documents = original_ingest
                batch_module.process_pdf_document = original_process_pdf
    finally:
        if token is not None:
            _PDF_DOWNLOAD_DIR.reset(token)


def run_batch_with_review(*args, reviewed_pdf_urls_by_index=None, pdf_review_flags=None, **kwargs):
    """Real desktop batch wrapper.

    Both AUTOMATIC and REVIEWED modes use the same identity-first document discovery
    and the same PDF identity validator. Every PDF actually processed by the desktop
    is retained under `<output>/pdf_evidence/<product>/`. Reviewed mode additionally
    enforces the user's exact allow-list.
    """
    if reviewed_pdf_urls_by_index is None and pdf_review_flags is None:
        reviewed_pdf_urls_by_index, pdf_review_flags = _desktop_review_plan()

    urls_plan = [list(rows or []) for rows in (reviewed_pdf_urls_by_index or [])]
    flags_plan = [bool(value) for value in (pdf_review_flags or [])]

    with _RUN_LOCK:
        original_scrape = batch_module.scrape_item
        original_discover = batch_module.discover_product_documents
        original_process_pdf = batch_module.process_pdf_document
        cursor = {"value": 0}

        batch_module.discover_product_documents = _shared_discover
        batch_module.process_pdf_document = _shared_process_pdf

        def desktop_scrape(item, out_dir, **scrape_kwargs):
            index = cursor["value"]
            cursor["value"] += 1
            approved = urls_plan[index] if index < len(urls_plan) else []
            enforced = flags_plan[index] if index < len(flags_plan) else False
            token = _PDF_DOWNLOAD_DIR.set(_persistent_pdf_dir(out_dir, item.identity))
            try:
                if enforced:
                    return scrape_item_with_review(
                        item,
                        out_dir,
                        approved_urls=approved,
                        enforced=True,
                        **scrape_kwargs,
                    )
                return _BASE_SCRAPE_ITEM(item, out_dir, **scrape_kwargs)
            finally:
                _PDF_DOWNLOAD_DIR.reset(token)

        batch_module.scrape_item = desktop_scrape

        try:
            return _BASE_RUN_BATCH(*args, **kwargs)
        finally:
            batch_module.scrape_item = original_scrape
            batch_module.discover_product_documents = original_discover
            batch_module.process_pdf_document = original_process_pdf
