from __future__ import annotations

from urllib.parse import urlparse

from .media_discovery import classify_media_role
from .models import ProductRecord
from .record_builder import build_record_strict
from .normalize import key_norm


def repair_existing_record(rec: ProductRecord) -> ProductRecord:
    """Re-run V7 quality gates against a record produced by an older version.
    Useful for migration/testing; normal runs build strict records directly.
    """
    new=build_record_strict(rec.identity,rec.evidence,rec.sources)
    # Manufacturer-page MPN vs structured SKU mismatch is a strong warning/conflict.
    hosts=[(urlparse(u).hostname or '').lower() for u in rec.sources]
    brand=key_norm(rec.identity.brand or '').replace(' ','')
    manufacturer_like=any(brand and brand in key_norm(h).replace(' ','') for h in hosts)
    if manufacturer_like and rec.identity.mpn and rec.identity.sku and key_norm(rec.identity.mpn)!=key_norm(rec.identity.sku):
        new.identity.match_level='CONFLICT'
        new.identity.identifiers_conflicting=sorted(set(new.identity.identifiers_conflicting+['mpn_vs_manufacturer_sku']))
        new.warnings.append('manufacturer_sku_conflicts_with_target_mpn')
    new.media=[]
    for m in rec.media:
        x=dict(m)
        role,ok=classify_media_role(x.get('url',''),x.get('alt'),x.get('source',''),x.get('media_type','image'))
        x['role']=role;x['autofill_eligible']=bool(ok and x.get('scope') in {'EXACT_VARIANT','EXACT_PRODUCT'} and float(x.get('confidence') or 0)>=.80)
        new.media.append(x)
    new.images=[m for m in new.media if m.get('media_type')=='image' and m.get('autofill_eligible') and new.identity.match_level!='CONFLICT']
    new.videos=[m for m in new.media if m.get('media_type')=='video' and m.get('autofill_eligible') and new.identity.match_level!='CONFLICT']
    new.site_profile=rec.site_profile
    new.technical_notes=rec.technical_notes
    new.fetch=rec.fetch
    new.warnings.extend(rec.warnings)
    return new
