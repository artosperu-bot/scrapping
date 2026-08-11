from product_intelligence.discovery import _is_search_provider_host
from product_intelligence.html_extract import identity_from_page
from product_intelligence.identity import compare_identity
from product_intelligence.models import ProductIdentity


def test_search_auth_redirect_query_does_not_confirm_mpn():
    expected = ProductIdentity(mpn="JBLQ350WLBLKAM")
    page = {
        "jsonld": [],
        "embedded": {},
        "title": "Login - Sign in to Yahoo",
        "text": "Sign in to Yahoo to continue",
    }
    url = (
        "https://login.yahoo.com/?done="
        "https://search.yahoo.com/search?p=JBLQ350WLBLKAM"
    )

    candidate = identity_from_page(page, expected=expected, source_url=url)
    assert candidate.mpn is None
    checked = compare_identity(expected, candidate)
    assert checked.match_level != "EXACT"


def test_product_url_path_can_still_reinforce_mpn():
    expected = ProductIdentity(mpn="JBLQ350WLBLKAM")
    page = {
        "jsonld": [],
        "embedded": {},
        "title": "JBL Quantum 350 Wireless",
        "text": "JBL Quantum 350 Wireless gaming headset",
    }
    url = "https://www.jbl.com/JBLQ350WLBLKAM.html?utm_source=test"

    candidate = identity_from_page(page, expected=expected, source_url=url)
    assert candidate.mpn == "JBLQ350WLBLKAM"
    checked = compare_identity(expected, candidate)
    assert checked.match_level == "EXACT"


def test_search_provider_subdomains_are_blocked():
    assert _is_search_provider_host("login.yahoo.com")
    assert _is_search_provider_host("search.yahoo.com")
    assert _is_search_provider_host("www.bing.com")
    assert not _is_search_provider_host("www.jbl.com")
    assert not _is_search_provider_host("www.bhphotovideo.com")
