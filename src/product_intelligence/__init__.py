__version__ = "0.10.31"

from .seller_defaults import install as _install_seller_defaults

_install_seller_defaults()

from .audit_bridge import install as _install_audit_bridge

_install_audit_bridge()


def _install_identity_sanity_guard() -> None:
    """Keep bootstrap brand acceptance aligned with the canonical identity sanity contract.

    The bootstrap has richer evidence-ranking rules, while identity_refinement owns
    semantic sanity (URL fragments, generic merchandising/category/color phrases,
    identifier contamination). Every package import crosses this boundary, so a
    bootstrap candidate can never be considered brand-quality if canonical sanity
    rejects it.
    """
    from . import identity_bootstrap as _bootstrap
    from .identity_refinement import brand_sanity_pass as _brand_sanity_pass

    original = _bootstrap._brand_candidate_quality
    if getattr(original, "_canonical_sanity_guard", False):
        return

    def guarded(brand, raw):
        return bool(_brand_sanity_pass(brand, raw=raw) and original(brand, raw))

    guarded._canonical_sanity_guard = True
    _bootstrap._brand_candidate_quality = guarded


_install_identity_sanity_guard()
