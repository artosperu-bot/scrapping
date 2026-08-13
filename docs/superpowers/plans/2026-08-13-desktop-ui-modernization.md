# Desktop UI Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Modernize the Windows desktop UI without changing scraping, price, media, Excel, identity, validation, persistence, browser, or API engine behavior.

**Architecture:** Add UI-only process sessions, theme/widgets, and per-execution log routing. Existing workers keep queue/event contracts and independent guards.

**Tech Stack:** Python 3.11/3.12, Tkinter/ttk, Pillow, PyInstaller, pytest.

## Constraints
- No global process lock.
- Preserve `_media_running`, `_price_running`, `run_batch`, `run_media_product`, `run_price_product` semantics.
- Worker threads never touch Tk widgets directly.
- Missing GIFs fall back to text and never abort work.

## Tasks
1. Create `ui_process.py` + `test_ui_process_sessions.py`: RED/GREEN tests for independent session ids, progress/log isolation, complete/error transitions.
2. Create `ui_theme.py`, `ui_widgets.py`, `test_ui_asset_paths.py`; add `process_running.gif` and `process_complete.gif`; test source/frozen asset paths and fallback behavior.
3. Modify `desktop.py`: business theme, `Todos` + per-execution logs, backward-compatible `emit`, base Excel session wrapping the same `run_batch` call. Add integration guards preventing global locks.
4. Modify `media_progress_desktop.py`/`media_desktop.py`: remove wolf UI only, use universal process card, preserve `_media_running`, queues, gallery/manual URLs and `run_media_product`.
5. Modify `price_desktop.py`: business layout, metrics, universal process card, preserve `_price_running`, queue flow, table meanings and `run_price_product`.
6. Full `pytest -q`; verify PyInstaller asset packaging; update `ARCHITECTURE_PRODUCT_INTELLIGENCE.md` and `README.md` with important architecture/concurrency/logging/build state; build final Windows EXE with existing `.bat`; diff-review for zero new engine/business-logic edits.

## Acceptance
- Multimedia and Prices can run simultaneously with separate cards/log tabs.
- Same-module duplicate starts remain blocked as before.
- `Todos` combines logs; session tabs isolate them.
- Running state uses the running asset; 100% success uses completion asset; error never shows completion.
- Existing result semantics remain unchanged.
