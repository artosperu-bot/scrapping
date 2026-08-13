SELLER_SKU_LABELS = {"seller sku", "sku vendedor", "sku del vendedor"}


def install() -> None:
    from . import normalize
    from . import template_intelligence

    for label in SELLER_SKU_LABELS:
        if label not in normalize.ALIASES["mpn"]:
            normalize.ALIASES["mpn"].append(label)
        template_intelligence.SELLER_HINTS.discard(label)
