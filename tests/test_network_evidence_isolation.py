from product_intelligence.web_fetch import _same_site_family, _site_key
from product_intelligence.html_extract import identity_from_page
from product_intelligence.identity import compare_identity
from product_intelligence.models import ProductIdentity


def test_same_site_family_blocks_disqus_recommendations():
    page='https://www.solotodo.cl/products/367057-jbl-endurance-run-3-bt-blue-jblendurrun3btbam'
    disqus='https://disqus.com/api/3.0/discovery/listRecommendations.json?forum=solotodo3'
    assert _same_site_family(page,disqus) is False


def test_same_site_family_accepts_regional_same_site_api():
    assert _site_key('https://www.example.com.pe/product') == 'example.com.pe'
    assert _same_site_family('https://www.example.com.pe/product','https://api.example.com.pe/catalog/123') is True


def test_mpn_in_url_path_alone_does_not_prove_exact_identity():
    expected=ProductIdentity(mpn='JBLENDURRUN3BTBAM')
    page={
        'title':'Different USB-C Headphones',
        'text':'Different USB-C Headphones model ABC. No requested manufacturer part number is present.',
        'jsonld':[],
        'embedded':{},
    }
    candidate=identity_from_page(page,expected=expected,source_url='https://retailer.example/products/wrong-product-jblendurrun3btbam')
    checked=compare_identity(expected,candidate)
    assert checked.match_level != 'EXACT'
    assert 'mpn' not in checked.identifiers_confirmed
