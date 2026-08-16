from importlib import import_module
from product_intelligence.modern_desktop import main
from product_intelligence.provider_desktop import main as provider_main
from product_intelligence.workspace_desktop import main as workspace_main
from product_intelligence.organized_desktop import main as organized_main
from product_intelligence.managed_desktop import main as managed_main
from product_intelligence.pdf_review_shell import main as pdf_review_main

# Preserve the validated modern/PDF/provider/workspace extension-chain imports because
# regression contracts use them as evidence that those layers remain present.
# The PDF review shell is the final additive launcher and does not replace the engines.
import_module("product_intelligence.pdf_desktop")
import_module("product_intelligence.provider_desktop")
import_module("product_intelligence.workspace_desktop")
import_module("product_intelligence.organized_desktop")
import_module("product_intelligence.pdf_review_shell")
pdf_review_main()
