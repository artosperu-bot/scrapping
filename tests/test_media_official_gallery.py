from product_intelligence.media_discovery import discover_media
from product_intelligence.media_url_quality import promote_image_url
from product_intelligence.models import ProductIdentity


def test_official_gallery_prefers_largest_srcset_and_extracts_video_urls():
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    html = '''
    <html><head><title>JBL Quantum 350 Wireless JBLQ350WLBLKAM</title>
    <script type="application/ld+json">{
      "@context":"https://schema.org","@type":"Product","name":"JBL Quantum 350 Wireless",
      "mpn":"JBLQ350WLBLKAM",
      "video":{"@type":"VideoObject","embedUrl":"https://www.youtube.com/embed/abc123","thumbnailUrl":"/media/video-thumb.jpg"}
    }</script></head><body>
      <div class="product-gallery">
        <img alt="JBL Quantum 350 Wireless front" src="/media/q350-320.jpg"
             srcset="/media/q350-640.jpg 640w, /media/q350-1600.jpg 1600w" data-zoom-image="/media/q350-2400.jpg">
        <video poster="/media/q350-video-poster.jpg"><source src="/media/q350-demo.mp4" type="video/mp4"></video>
        <iframe title="JBL Quantum video" src="https://www.youtube.com/embed/abc123"></iframe>
      </div>
      <section class="related-products"><img alt="JBL Tune earbuds" src="/media/related-tune.jpg"></section>
    </body></html>
    '''
    rows = discover_media(html, "https://www.jbl.com.pe/QUANTUM350WIRELESS-.html", identity, page_is_validated=True)
    by_url = {row["url"]: row for row in rows}

    assert "https://www.jbl.com.pe/media/q350-2400.jpg" in by_url
    assert by_url["https://www.jbl.com.pe/media/q350-2400.jpg"]["role"] == "product_gallery"
    assert "https://www.jbl.com.pe/media/q350-demo.mp4" in by_url
    assert by_url["https://www.jbl.com.pe/media/q350-demo.mp4"]["role"] == "product_video"
    assert "https://www.youtube.com/embed/abc123" in by_url
    assert by_url["https://www.youtube.com/embed/abc123"]["provider"] == "youtube"
    assert by_url["https://www.jbl.com.pe/media/related-tune.jpg"]["role"] != "product_gallery"


def test_gallery_rows_expose_stable_gallery_index():
    identity = ProductIdentity(brand="JBL", model="Quantum 350 Wireless", mpn="JBLQ350WLBLKAM")
    html = '''<div class="product-gallery">
      <img alt="JBL Quantum 350 Wireless" data-zoom="/media/a.jpg">
      <img alt="JBL Quantum 350 Wireless" data-zoom="/media/b.jpg">
    </div> JBLQ350WLBLKAM'''
    rows = discover_media(html, "https://jbl.com.pe/product", identity, page_is_validated=True)
    gallery = [r for r in rows if r.get("role") == "product_gallery"]
    indexes = [r.get("gallery_index") for r in gallery if r["url"].endswith(("a.jpg", "b.jpg"))]
    assert indexes == sorted(indexes)
    assert all(isinstance(i, int) and i >= 1 for i in indexes)


def test_resized_cdn_gallery_url_is_promoted_to_unconstrained_asset():
    resized = "https://www.jbl.com.pe/dw/image/v2/ABC/on/demandware.static/-/Sites-master/default/image.png?sfrm=jpg&sh=140&sm=cut&sw=140"
    promoted = promote_image_url(resized)
    assert promoted == "https://www.jbl.com.pe/dw/image/v2/ABC/on/demandware.static/-/Sites-master/default/image.png?sfrm=jpg"
    assert "sh=140" not in promoted and "sw=140" not in promoted
