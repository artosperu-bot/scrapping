from product_intelligence.discovery import SearchCandidate
from product_intelligence.identity_bootstrap import resolve_identity_from_candidates
from product_intelligence.models import ProductIdentity


def test_seller_site_name_cannot_become_brand_from_title_prefix():
    identity = ProductIdentity(mpn="ZX-7001")
    candidates = [
        SearchCandidate("https://store-one.example/zx-7001", "Store One ZX-7001 available now", "Brand: Acme; ZX-7001 industrial sensor"),
        SearchCandidate("https://store-two.example/zx-7001", "Store Two ZX-7001", "Acme ZX-7001 sensor; in stock"),
        SearchCandidate("https://catalog.example/acme-zx-7001", "Acme ZX-7001 specifications", "Manufacturer: Acme"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert "Store One" not in result.brand_scores
    assert "Store Two" not in result.brand_scores


def test_social_site_identity_cannot_vote_as_product_brand():
    identity = ProductIdentity(mpn="ZX-7002")
    candidates = [
        SearchCandidate("https://www.youtube.com/watch?v=1", "YouTube ZX-7002 review", "Acme ZX-7002 product review"),
        SearchCandidate("https://www.facebook.com/acme/posts/1", "Facebook ZX-7002", "Acme ZX-7002"),
        SearchCandidate("https://catalog.example/acme-zx-7002", "Acme ZX-7002 specifications", "Manufacturer: Acme"),
        SearchCandidate("https://dealer.example/zx-7002", "Acme ZX-7002", "ZX-7002 product details"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert "YouTube" not in result.brand_scores
    assert "Facebook" not in result.brand_scores


def test_refined_query_context_outweighs_homonymous_product_cluster():
    identity = ProductIdentity(mpn="ZX-7003")
    candidates = [
        SearchCandidate("https://auto-one.example/zx-7003", "Marmon Ride ZX-7003 control arm", "Suspension control arm", query='"ZX-7003"'),
        SearchCandidate("https://auto-two.example/zx-7003", "Marmon Ride ZX-7003 control arm", "Automotive suspension part", query='"ZX-7003"'),
        SearchCandidate("https://auto-three.example/zx-7003", "Marmon Ride ZX-7003", "Control arm replacement", query='"ZX-7003"'),
        SearchCandidate("https://tech-one.example/zx-7003", "Acme USB-C Charge Cable ZX-7003", "Acme USB-C charge cable", query='"ZX-7003" "USB-C"'),
        SearchCandidate("https://tech-two.example/zx-7003", "Acme ZX-7003 USB-C cable", "Brand: Acme; charge cable", query='"ZX-7003" "USB-C"'),
        SearchCandidate("https://tech-three.example/zx-7003", "Acme Charge Cable ZX-7003", "USB-C cable by Acme", query='"ZX-7003" "Charge"'),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"


def test_subdomains_count_as_one_independent_source_for_brand_consensus():
    identity = ProductIdentity(mpn="ZX-7004")
    candidates = [
        SearchCandidate("https://ca.publisher.example/zx-7004", "Publisher ZX-7004", "ZX-7004 product"),
        SearchCandidate("https://www.publisher.example/zx-7004", "Publisher ZX-7004", "ZX-7004 product"),
        SearchCandidate("https://one.example/acme-zx-7004", "Acme ZX-7004", "Brand: Acme"),
        SearchCandidate("https://two.example/acme-zx-7004", "Acme ZX-7004 specifications", "Acme ZX-7004 product"),
    ]
    result = resolve_identity_from_candidates(identity, candidates)
    assert result.status == "RESOLVED"
    assert result.identity.brand == "Acme"
    assert result.brand_hosts.get("Publisher", 0) <= 1
