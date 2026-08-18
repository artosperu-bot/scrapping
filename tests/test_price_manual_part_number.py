from pathlib import Path

from product_intelligence.models import ProductIdentity
from product_intelligence.price_desktop import App as PriceApp
from product_intelligence import isolated_desktop
from product_intelligence.isolated_desktop import App as IsolatedPriceApp


ROOT = Path(__file__).parents[1]


class _FakeGetVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _FakeButton:
    def configure(self, **_kwargs):
        return None


class _FakeTree:
    def get_children(self):
        return ()

    def delete(self, _item):
        return None


class _FakeList:
    def __init__(self, size):
        self._size = size

    def size(self):
        return self._size


class _NoStartThread:
    def __init__(self, *, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        return None


def test_price_ui_can_add_manual_part_number_to_existing_search_flow():
    source = (ROOT / "src" / "product_intelligence" / "price_desktop.py").read_text(encoding="utf-8")

    # The manual input belongs only to the Price UI. It must create the same
    # ProductIdentity shape that the already-working price workflow consumes.
    assert 'text="Part Number / MPN"' in source
    assert "_add_manual_price_product" in source
    assert "ProductIdentity(mpn=part_number)" in source
    assert "_price_identity_for_list_index" in source

    # The existing price engine remains the terminal execution path.
    assert "run_price_product(identity, output_root, on_event=on_event, max_sources=48)" in source


def test_final_organized_price_ui_keeps_manual_part_number_controls():
    source = (ROOT / "src" / "product_intelligence" / "organized_desktop.py").read_text(encoding="utf-8")

    # organized_desktop rebuilds the visible Price workspace after the base UI.
    # The final packaged screen must therefore recreate the manual MPN controls.
    assert 'text="Part Number / MPN"' in source
    assert "textvariable=self.price_manual_part_number" in source
    assert 'text="Agregar"' in source
    assert "command=self._add_manual_price_product" in source
    assert "Analiza un Excel o agrega un Part Number para buscar precios." in source


def test_process_all_accepts_manual_product_without_excel(monkeypatch):
    app = object.__new__(PriceApp)
    app.product_rows = []
    app._manual_price_identities = [ProductIdentity(mpn="sa400s37/960g")]
    app.price_product_list = _FakeList(1)
    started = []
    warnings = []
    app._start_price_indices = lambda indices: started.append(list(indices))
    monkeypatch.setattr("product_intelligence.price_desktop.messagebox.showwarning", lambda *args: warnings.append(args))

    PriceApp._run_price_all(app)

    assert warnings == []
    assert started == [[0]]


def test_isolated_price_run_accepts_manual_identity_without_excel(monkeypatch, tmp_path):
    app = object.__new__(IsolatedPriceApp)
    app._price_running = False
    app.product_rows = []
    app._manual_price_identities = [ProductIdentity(mpn="sa400s37/960g")]
    app._active_snapshots = {}
    app.out = _FakeGetVar(str(tmp_path))
    app.price_selected_btn = _FakeButton()
    app.price_all_btn = _FakeButton()
    app.price_tree = _FakeTree()
    app._set_price_progress = lambda *_args: None
    app._audit = lambda *_args, **_kwargs: None
    # If the isolated PRICE layer incorrectly falls back to the Excel-only
    # identity resolver, the manual product disappears here.
    app._identity_for_index = lambda _index: None

    errors = []
    monkeypatch.setattr(isolated_desktop.messagebox, "showerror", lambda *args: errors.append(args))
    monkeypatch.setattr(isolated_desktop.threading, "Thread", _NoStartThread)

    IsolatedPriceApp._start_price_indices(app, [0])

    assert errors == []
    assert app._price_running is True
    assert len(app._active_snapshots) == 1
    snapshot = next(iter(app._active_snapshots.values()))
    assert len(snapshot.products) == 1
    assert snapshot.products[0].identity.mpn == "sa400s37/960g"


def test_packaged_entrypoint_has_manual_price_no_excel_smoke_contract():
    run_desktop = (ROOT / "run_desktop.py").read_text(encoding="utf-8")
    smoke_path = ROOT / "src" / "product_intelligence" / "manual_price_ui_smoke.py"

    assert '--manual-price-ui-smoke' in run_desktop
    assert smoke_path.is_file()
    smoke = smoke_path.read_text(encoding="utf-8")
    assert 'sa400s37/960g' in smoke
    assert '_run_price_all()' in smoke
    assert '_run_price_selected()' in smoke
    assert 'snapshot.products[0].identity.mpn' in smoke
