from importlib import import_module
from product_intelligence.modern_desktop import main
from product_intelligence.provider_desktop import main as provider_main
from product_intelligence.workspace_desktop import main as workspace_main

# Preserve the validated modern/PDF/provider extension-chain imports because
# regression contracts use them as evidence that those layers remain present.
# The persistent workspace shell is only the final additive launcher.
import_module("product_intelligence.pdf_desktop")
import_module("product_intelligence.provider_desktop")
workspace_main()
