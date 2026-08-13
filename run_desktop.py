from importlib import import_module
from product_intelligence.modern_desktop import main

# Preserve the validated modern desktop import chain and launch the PDF-aware isolated shell.
import_module("product_intelligence.pdf_desktop").main()
