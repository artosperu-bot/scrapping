from pathlib import Path
from product_intelligence.batch import manual_items
from product_intelligence.excel_mapper_v8 import fill_excel_v8
from product_intelligence.models import ProductIdentity, ProductRecord


def _record():
    return ProductRecord(identity=ProductIdentity(brand="JBL",product_name="JBL Quantum 350 Wireless",model="Quantum 350 Wireless",mpn="JBLQ350WLBLKAM",confidence=.99,match_level="EXACT",identifiers_confirmed=["mpn"]))

def test_manual_part_numbers_are_assigned_to_consecutive_rows():
    root=Path(__file__).resolve().parents[1]
    template=root/'examples'/'ProductCreationTemplate_reference.xlsx'
    items=manual_items(str(template),['JBLQ350WLBLKAM','JBLENDURRUN3BTBAM','JBLT530CBLKAM'])
    assert [(x.sheet,x.row,x.identity.mpn) for x in items] == [('Subir plantilla',5,'JBLQ350WLBLKAM'),('Subir plantilla',6,'JBLENDURRUN3BTBAM'),('Subir plantilla',7,'JBLT530CBLKAM')]

def test_manual_row_assignment_can_fill_empty_template(tmp_path):
    root=Path(__file__).resolve().parents[1]
    template=root/'examples'/'ProductCreationTemplate_reference.xlsx'
    rec=_record();out=tmp_path/'manual.xlsx'
    report=fill_excel_v8(str(template),str(out),[rec],overwrite=True,row_assignments={('Subir plantilla',5):rec})
    assert out.exists();assert report['summary']['written_count'] > 0
