from pathlib import Path

CAP = Path("src/product_intelligence/price_source_capabilities.py")
WORK = Path("src/product_intelligence/price_workflow.py")

cap = CAP.read_text(encoding="utf-8")

if "from threading import Lock\n" not in cap:
    anchor = "from pathlib import Path\n"
    if anchor not in cap:
        raise SystemExit("P8 persistence patch abort: pathlib import anchor missing")
    cap = cap.replace(anchor, anchor + "from threading import Lock\n", 1)

if "self._write_lock = Lock()" not in cap:
    anchor = '        self.path = root / "price_intelligence" / "source_capabilities.json"\n'
    if anchor not in cap:
        raise SystemExit("P8 persistence patch abort: registry init anchor missing")
    cap = cap.replace(anchor, anchor + "        self._write_lock = Lock()\n", 1)

if "with self._write_lock:" not in cap:
    record_pos = cap.find("\n    def record(\n")
    if record_pos < 0:
        record_pos = cap.find("    def record(\n")
    start = cap.find("        data = self._load()", record_pos)
    if record_pos < 0 or start < 0:
        raise SystemExit("P8 persistence patch abort: record body start missing")
    # record() is deliberately the final method in this compact registry.  Use EOF
    # rather than depending on a trailing newline after `return row`.
    body = cap[start:]
    if "        return row" not in body:
        raise SystemExit("P8 persistence patch abort: record return missing")
    indented = "        with self._write_lock:\n" + "".join(
        "    " + line if line.strip() else line
        for line in body.splitlines(keepends=True)
    )
    cap = cap[:start] + indented

CAP.write_text(cap, encoding="utf-8")

work = WORK.read_text(encoding="utf-8")
old = '''            if capability_registry is not None:\n                capability_registry.record(\n                    domain,\n                    platform=platform,\n                    discovery_method=f"direct_{method}" if method else "direct_source",\n                    extraction_method=extraction,\n                    price_capable=True if found else None,\n                    stock_capable=True if any(row.stock is not None or bool(row.availability) for row in found) else None,\n                    seller_capable=True if any(bool(row.seller_display_name or row.seller_legal_name or row.seller_tax_id) for row in found) else None,\n                    success=bool(found),\n                    category=category,\n                )\n'''
new = '''            if capability_registry is not None:\n                try:\n                    capability_registry.record(\n                        domain,\n                        platform=platform,\n                        discovery_method=f"direct_{method}" if method else "direct_source",\n                        extraction_method=extraction,\n                        price_capable=True if found else None,\n                        stock_capable=True if any(row.stock is not None or bool(row.availability) for row in found) else None,\n                        seller_capable=True if any(bool(row.seller_display_name or row.seller_legal_name or row.seller_tax_id) for row in found) else None,\n                        success=bool(found),\n                        category=category,\n                    )\n                except Exception:\n                    # Capability memory is advisory. A persistence failure must never\n                    # discard a fresh offer already returned by the source adapter.\n                    pass\n'''
if old in work:
    work = work.replace(old, new, 1)
elif "Capability memory is advisory." not in work:
    raise SystemExit("P8 persistence patch abort: direct success record anchor missing")

WORK.write_text(work, encoding="utf-8")
print("P8_CAPABILITY_PERSISTENCE_PATCH=APPLIED")
