from __future__ import annotations

import re
from .models import ProductIdentity


def _clean(v: str | None) -> str | None:
    v=str(v or '').strip()
    return v or None


def parse_product_query(line: str) -> ProductIdentity | None:
    """Parse one user product query.

    One primary value is enough. Optional hints may follow with | separators, e.g.:
    JBLENDURRUN3BTBAM | brand=JBL | color=Azul
    name=JBL Tune 530C USB-C | brand=JBL
    """
    raw=str(line or '').strip()
    if not raw:return None
    parts=[x.strip() for x in raw.split('|') if x.strip()]
    data={}
    primary=None
    for part in parts:
        m=re.match(r'^(mpn|part(?:\s*number)?|ean|upc|gtin|name|nombre|brand|marca|model|modelo|color|variant|variante)\s*[:=]\s*(.+)$',part,re.I)
        if not m:
            if primary is None: primary=part
            continue
        key=m.group(1).lower().replace(' ','')
        value=_clean(m.group(2))
        mapping={"part":"mpn","partnumber":"mpn","nombre":"product_name","name":"product_name","marca":"brand","brand":"brand","modelo":"model","model":"model","variante":"variant","variant":"variant"}
        data[mapping.get(key,key)]=value
    if primary and not any(data.get(k) for k in ['mpn','ean','upc','gtin','product_name']):
        compact=re.sub(r'[\s-]+','',primary)
        if compact.isdigit() and len(compact)==12:
            data['upc']=compact
        elif compact.isdigit() and len(compact) in {8,13,14}:
            data['ean' if len(compact) in {8,13} else 'gtin']=compact
        elif re.fullmatch(r'[A-Za-z0-9._/-]{4,80}',primary) and re.search(r'[A-Za-z]',primary) and re.search(r'\d',primary):
            data['mpn']=primary
        else:
            data['product_name']=primary
    if not any(data.get(k) for k in ['mpn','ean','upc','gtin','product_name']):
        return None
    allowed={k:v for k,v in data.items() if k in ProductIdentity.model_fields and v not in (None,'')}
    return ProductIdentity(**allowed)


def parse_product_queries(text: str) -> list[ProductIdentity]:
    out=[];seen=set()
    for line in str(text or '').splitlines():
        identity=parse_product_query(line)
        if not identity:continue
        signature=tuple((k,str(getattr(identity,k,None) or '').lower()) for k in ['mpn','ean','upc','gtin','product_name','brand','model','color','variant'])
        if signature in seen:continue
        seen.add(signature);out.append(identity)
    return out
