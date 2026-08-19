from pathlib import Path

path = Path("src/product_intelligence/price_identity.py")
text = path.read_text(encoding="utf-8")

old = '''    if host.endswith(".pe") or host.endswith(".com.pe"):
        return True
    if host in _PERU_RETAIL_HOSTS and str(row.currency or "").upper() == "PEN":
        return True
'''
new = '''    if host.endswith(".pe") or host.endswith(".com.pe"):
        return True
    # Geography is independent from settlement currency. Some Peru retailers use
    # a generic .com and expose Peru explicitly in the registrable host label;
    # final trust still requires the existing identity/confidence/positive-price gates.
    if any(label.endswith("peru") for label in host.split(".")):
        return True
    if host in _PERU_RETAIL_HOSTS and str(row.currency or "").upper() == "PEN":
        return True
'''

if new in text:
    print("P7 Peru-named dotcom offer semantics patch already present")
elif old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("P7 Peru-named dotcom offer semantics patch applied")
else:
    raise SystemExit("expected Peru offer block not found; refusing broad rewrite")
