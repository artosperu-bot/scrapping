from importlib import import_module
from product_intelligence.workspace_desktop import main as workspace_main

# Preserve the validated modern/PDF/provider extension chain, then add the
# persistent workspace shell as the final additive desktop layer.
import_module("product_intelligence.pdf_desktop")
import_module("product_intelligence.provider_desktop")
workspace_main()
