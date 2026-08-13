from product_intelligence.ui_process import ProcessRegistry

def test_ui_state_fields():
    r=ProcessRegistry(); s=r.start('price','x',total=4)
    r.apply(s.session_id, {'stage':'validating','overall_percent':25})
    x=r.get(s.session_id)
    assert x.total == 4
    assert x.stage == 'validating'
    assert x.overall_percent == 25
