from pathlib import Path
p=Path('src/product_intelligence/discovery.py')
s=p.read_text(encoding='utf-8')
old='''    ranked=_rank_candidates(urls,identity,limit)
    if ranked:return ranked

    # Search engines occasionally return an empty/blocked HTML page to cloud runners.
'''
new='''    ranked=_rank_candidates(urls,identity,limit)

    # When brand is known, do not stop at the first retailer results. Product discovery is
    # evidence gathering, and manufacturer pages deserve an explicit second chance because
    # search engines often rank stores above regional official sites for exact MPN queries.
    brand=str(identity.brand or '').strip()
    if strong_raw and brand and not any(c.likely_official for c in ranked):
        strong=str(strong_raw).strip()
        official_queries=[
            f'"{strong}" "{brand}" official',
            f'"{strong}" "{brand}" product',
            f'"{strong}" "{brand}" specifications',
        ]
        for oq in official_queries:
            urls.extend(_provider_search(oq,max(8,min(timeout,15))))
            reranked=_rank_candidates(urls,identity,limit)
            if any(c.likely_official for c in reranked):
                ranked=reranked
                break
        else:
            ranked=_rank_candidates(urls,identity,limit)
    if ranked:return ranked

    # Search engines occasionally return an empty/blocked HTML page to cloud runners.
'''
if old not in s: raise SystemExit('anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('patched official query stage')
