from __future__ import annotations

from product_intelligence.real_pdf_review_shell import App


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Box:
    def __init__(self):
        self.index = -1

    def current(self, value=None):
        if value is not None:
            self.index = int(value)
        return self.index


def _bare_app(total_products: int, enforced: set[int]):
    app = object.__new__(App)
    app.product_rows = [{} for _ in range(total_products)]
    app.pdf_review_mode = _Value("reviewed")
    app.use_pdf_evidence = _Value(True)
    app._pdf_review_enforced = set(enforced)
    app.pdf_review_product_box = _Box()
    app.pdf_review_status = _Value("")
    app._pdf_review_refresh_tree = lambda: None
    return app


def test_execute_in_reviewed_pdf_mode_starts_search_for_first_pending_product(monkeypatch):
    app = _bare_app(3, set())
    actions = []
    warnings = []

    app._show_workspace = lambda key: actions.append(("workspace", key))

    original_current = app.pdf_review_product_box.current
    def current(value=None):
        result = original_current(value)
        if value is not None:
            actions.append(("current", result))
        return result
    app.pdf_review_product_box.current = current

    app._pdf_review_search = lambda: actions.append(("search", app.pdf_review_product_box.current()))
    monkeypatch.setattr("product_intelligence.real_pdf_review_shell.messagebox.showwarning", lambda *args: warnings.append(args))

    result = App.run(app)

    assert result is None
    assert actions == [("workspace", "pdf_review"), ("current", 0), ("search", 0)]
    assert warnings == []
    assert "Buscando PDFs" in app.pdf_review_status.get()


def test_execute_starts_next_unconfirmed_product_instead_of_repeating_confirmed_one(monkeypatch):
    app = _bare_app(3, {0})
    searched = []
    app._show_workspace = lambda _key: None
    app._pdf_review_search = lambda: searched.append(app.pdf_review_product_box.current())
    monkeypatch.setattr("product_intelligence.real_pdf_review_shell.messagebox.showwarning", lambda *_args: None)

    result = App.run(app)

    assert result is None
    assert searched == [1]
