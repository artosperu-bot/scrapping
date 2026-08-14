from importlib import import_module
from product_intelligence.modern_desktop import main
from product_intelligence.provider_desktop import main as provider_main

# Preserve the validated modern/PDF extension chain while launching the provider settings layer.
import_module("product_intelligence.pdf_desktop")
provider_main()
