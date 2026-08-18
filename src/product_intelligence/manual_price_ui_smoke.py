from __future__ import annotations

import traceback
from unittest.mock import patch

from .final_live_ui_desktop import App


TEST_MPN = "sa400s37/960g"


def run_smoke() -> None:
    app = App()
    patcher = None
    try:
        app.update_idletasks()

        # Reproduce the user's real entry path: no Excel, only an MPN typed in Price Intelligence.
        assert not list(getattr(app, "product_rows", []) or []), "Smoke must start without Excel products"
        assert app.price_product_list.size() == 0, "Price list must start empty"
        app.price_manual_part_number.set(TEST_MPN)
        app._add_manual_price_product()

        assert app.price_product_list.size() == 1
        assert app.price_product_list.get(0) == TEST_MPN
        identity = app._price_identity_for_list_index(0)
        assert identity is not None
        assert identity.mpn == TEST_MPN

        # First reproduce the 'Procesar todos' button without launching the worker.
        captured_indices: list[list[int]] = []
        original_start = app._start_price_indices
        app._start_price_indices = lambda indices: captured_indices.append(list(indices))
        try:
            app._run_price_all()
        finally:
            app._start_price_indices = original_start
        assert captured_indices == [[0]], captured_indices

        # Then exercise the real final MRO for BUSCAR PRECIOS. The worker thread is
        # prevented from starting so this smoke validates routing/identity, not the network.
        patcher = patch("product_intelligence.isolated_desktop.threading.Thread")
        thread_cls = patcher.start()
        app._run_price_selected()

        assert app._price_running is True
        price_snapshots = [
            snapshot
            for snapshot in app._active_snapshots.values()
            if str(getattr(snapshot, "process_type", "")) == "PRICE"
        ]
        assert len(price_snapshots) == 1, price_snapshots
        snapshot = price_snapshots[0]
        assert len(snapshot.products) == 1
        assert snapshot.products[0].identity.mpn == TEST_MPN
        thread_cls.return_value.start.assert_called_once()
    finally:
        if patcher is not None:
            patcher.stop()
        try:
            app.destroy()
        except Exception:
            pass


def main() -> int:
    try:
        run_smoke()
    except Exception:
        traceback.print_exc()
        return 1
    print(f"PACKAGED_MANUAL_PRICE_NO_EXCEL=PASS mpn={TEST_MPN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
