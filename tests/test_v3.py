from product_intelligence.models import ProductIdentity
from product_intelligence.identity import compare_identity
from product_intelligence.image_extract import extract_image_candidates
from product_intelligence.template_intelligence import analyze_matrix, classify_field
from product_intelligence.normalize import canonical_key


def test_market_identity_conflict_is_detectable():
    expected=ProductIdentity(brand="Kingston",mpn="SNV3S/1000G",model="NV3")
    candidate=ProductIdentity(brand="Kingston",mpn="SNV3S/2000G",model="NV3")
    out=compare_identity(expected,candidate)
    assert out.match_level=="CONFLICT"
    assert "mpn" in out.identifiers_conflicting


def test_exact_identifier_wins():
    expected=ProductIdentity(brand="Kingston",mpn="SNV3S/1000G")
    candidate=ProductIdentity(brand="Kingston",mpn="SNV3S/1000G")
    assert compare_identity(expected,candidate).match_level=="EXACT"


def test_product_images_rank_over_logo():
    html='''<html><head><meta property="og:image" content="/images/NV3-1TB-product-1200.jpg"></head><body>
    <img src="/logo.png" width="80" height="40" alt="Kingston logo">
    <img srcset="/nv3-small.jpg 300w, /nv3-large.jpg 1400w" alt="Kingston NV3 1TB">
    </body></html>'''
    imgs=extract_image_candidates(html,"https://kingston.example/nv3",["Kingston","NV3","1TB"])
    assert imgs[0]["url"].endswith("NV3-1TB-product-1200.jpg")
    assert imgs[0]["score"] > imgs[-1]["score"]


def test_template_detects_non_first_header_row_and_images():
    matrix=[
        ["Principales","Principales","Imágenes","Precio"],
        ["Ingresa la marca","Ingresa capacidad","URL de imagen del producto","Precio del vendedor"],
        ["Opcional","Opcional","Opcional","Obligatorio"],
        ["Marca #26","CapacidadDeAlmacenamiento #1538","Imagen 1 #90","PriceFalabella #52"],
        ["Kingston",None,None,None],
    ]
    out=analyze_matrix(matrix)
    assert out["header_row"]==4
    classes={f["label"]:f["field_class"] for f in out["fields"]}
    assert classes["Imagen 1 #90"]=="IMAGE"
    assert classes["PriceFalabella #52"]=="SELLER_DATA"


def test_spanish_english_aliases():
    assert canonical_key("Velocidad de lectura secuencial")=="sequential_read_speed"
    assert canonical_key("Storage temperature")=="storage_temperature"
    assert canonical_key("Garantía del producto")=="warranty"

from product_intelligence.text_extract import extract_text_evidence


def test_datasheet_without_colons_and_capacity_table():
    text='''
Form factor M.2 2280
Interface PCIe 4.0 x4 NVMe
Sequential read/write
500GB – 5,000/3,000MB/s
1TB – 6,000/4,000MB/s
NAND 3D
Storage temperature -40°C~85°C
Operating temperature 0°C~70°C
Dimensions 22mm x 80mm x 2.3mm
Weight 7g
Vibration non-operating 20G (10-1000Hz)
MTBF 2,000,000 hours
Warranty/Support Limited 5-year warranty with free technical support
'''
    ev=extract_text_evidence(text,'https://example/datasheet.pdf','official_pdf','EXACT',.95,expected_capacity='1TB')
    vals={canonical_key(e.attribute) or e.attribute:str(e.normalized_value) for e in ev}
    assert vals['form_factor']=='M.2 2280'
    assert vals['interface']=='PCIe 4.0 x4 NVMe'
    assert vals['sequential_read_speed']=='6000 MB/s'
    assert vals['sequential_write_speed']=='4000 MB/s'
    assert vals['storage_temperature_min']=='-40 °C'
    assert vals['storage_temperature_max']=='85 °C'
    assert vals['width']=='22 mm'
    assert vals['length']=='80 mm'
    assert vals['thickness']=='2.3 mm'
    assert vals['vibration_frequency_range'].replace(' ','')=='10-1000Hz'
