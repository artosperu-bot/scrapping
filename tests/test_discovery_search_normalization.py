from product_intelligence.discovery import _unwrap_bing


def test_bing_tracking_url_is_unwrapped_to_destination():
    tracked = (
        "https://www.bing.com/ck/a?!&&p=abc&u="
        "a1aHR0cHM6Ly9lbi5tLndpa2lwZWRpYS5vcmcvd2lraS9Bcm1vdXI&ntb=1"
    )

    assert _unwrap_bing(tracked) == "https://en.m.wikipedia.org/wiki/Armour"


def test_normal_result_url_is_unchanged():
    url = "https://manufacturer.example/products/model-22"

    assert _unwrap_bing(url) == url
