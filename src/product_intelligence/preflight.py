from __future__ import annotations

from pathlib import Path
from typing import Any

from .discovery import build_query
from .intake_refinement import analyze_workbook_intake
from .template_contract import analyze_template_contract
from .extraction_strategy import extraction_plan


ACTION_BY_ROLE = {
    "IDENTITY": "VALIDAR / COMPLETAR",
    "SCRAPE_TARGET": "INVESTIGAR",
    "DERIVED_OUTPUT": "DERIVAR",
    "MEDIA_TARGET": "IMAGEN",
    "SELLER_INPUT": "DEJAR VACÍO / PROTEGER",
    "MARKETPLACE_INPUT": "DEJAR VACÍO / PROTEGER",
    "REVIEW_REQUIRED": "REVISAR",
}


def _product_label(identity) -> str:
    for key in ("mpn", "ean", "upc", "gtin", "sku", "model", "product_name"):
        value = getattr(identity, key, None)
        if value:
            return str(value)
    return ""


def analyze_workbook(template: str) -> dict[str, Any]:
    """Preflight the workbook without touching the web or modifying the Excel.

    The result is intentionally UI-friendly and includes the complete Excel-to-SEARCH
    decision trail. Query strings are previews only: this function never performs web
    discovery or scraping.
    """
    path = Path(template)
    if not path.exists():
        raise FileNotFoundError(template)

    intake = analyze_workbook_intake(template)
    contract = analyze_template_contract(template)

    products = []
    search_by_row: dict[tuple[str, int], tuple[bool, str]] = {}
    for item in intake.products:
        ident = item.identity
        query = build_query(ident)
        requested = bool(query.strip())
        search_by_row[(item.sheet, item.row)] = (requested, query)
        products.append({
            "sheet": item.sheet,
            "row": item.row,
            "identifier": _product_label(ident),
            "mpn": ident.mpn,
            "ean": ident.ean,
            "upc": ident.upc,
            "gtin": ident.gtin,
            "sku": ident.sku,
            "brand": ident.brand,
            "model": ident.model,
            "product_name": ident.product_name,
            "source_urls": list(item.source_urls or []),
            "identity_type": item.audit.get("identity_type"),
            "identity_value": item.audit.get("identity_selected"),
            "row_accepted": True,
            "search_requested": requested,
            "search_query": query,
            "search_executed": False,
        })

    intake_audit = intake.audit_dict()
    for sheet in intake_audit.get("sheets", []):
        sheet_name = sheet.get("sheet_detected")
        for row in sheet.get("rows", []):
            key = (sheet_name, row.get("product_row"))
            requested, query = search_by_row.get(key, (False, ""))
            row["search_requested"] = requested
            row["search_query"] = query
            row["search_executed"] = False
            if not row.get("row_accepted"):
                row["search_requested"] = False
                row["rejection_reason"] = row.get("rejection_reason") or "ROW_REJECTED_BEFORE_SEARCH"

    attributes = []
    for sheet in contract.get("sheets", []):
        for field in sheet.get("fields", []):
            role = field.get("role") or "REVIEW_REQUIRED"
            attributes.append({
                "sheet": field.get("sheet") or sheet.get("sheet"),
                "column": field.get("column"),
                "external_id": field.get("external_id"),
                "label": field.get("label"),
                "description": field.get("description"),
                "role": role,
                "action": ACTION_BY_ROLE.get(role, "REVISAR"),
                "required": bool(field.get("required")),
                "value_type": field.get("value_type"),
                "options_count": len(field.get("options") or []),
                "reason": field.get("reason"),
            })

    action_counts: dict[str, int] = {}
    for field in attributes:
        action_counts[field["action"]] = action_counts.get(field["action"], 0) + 1

    return {
        "template": str(path),
        "products": products,
        "attributes": attributes,
        "reference_sheets": contract.get("reference_sheets", []),
        "extraction_plan": extraction_plan(),
        "intake_audit": intake_audit,
        "summary": {
            **contract.get("summary", {}),
            "products_detected": len(products),
            "sheets_analyzed": len(intake.sheets),
            "product_sheets_detected": sum(1 for sheet in intake.sheets if sheet.accepted),
            "actions": action_counts,
        },
        "contract": contract,
    }
