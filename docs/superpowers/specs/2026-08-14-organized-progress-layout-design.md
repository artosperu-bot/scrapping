# Organized Progress Layout — Design

## Scope
Visual-only reorganization of ProductIntelligence desktop views. Preserve all scraping, pricing, multimedia, OCR.space, Mistral, PDF evidence, canonical, Excel writing, event flow, threading, and updater behavior.

## Goals
- Make the progress GIF clearly visible instead of visually compressed.
- Improve visual hierarchy and spacing in Price Intelligence.
- Align Multimedia and Scraping Excel progress areas to the same visual pattern where useful.
- Keep results/content as the largest area of each workspace.
- Do not invent percentages or process states.

## Price Intelligence layout
1. Header remains unchanged in meaning.
2. Top row: Products detected on the left; Actions + current status on the right.
3. Dedicated progress card below with fixed vertical space. Left side contains current status and truthful progress bars; right side contains ProgressAnimation at a larger visible size (about 220x140).
4. Compact summary strip below progress.
5. Offers table remains the main expanding content area.
6. Existing callbacks, event handling, run_price_product invocation, queue behavior, buttons, tree bindings, and data columns remain functionally unchanged.

## Multimedia layout
- Preserve media workflow and gallery behavior.
- Keep gallery as the primary expanding result area.
- Reorganize only the progress card to match the same status/bars/GIF hierarchy and ensure the animation has enough fixed space.

## Scraping Excel layout
- Preserve analysis, OCR, Mistral, PDF discovery/evidence and Excel writing logic.
- Reorganize only the existing progress area so status, progress counters/bars and GIF are readable and aligned.

## ProgressAnimation
- Reuse the existing shared component and existing processing.gif/completed.gif assets.
- No animation threads.
- Keep Tk after()-driven frames and RUNNING/COMPLETED/ERROR semantics.
- Layout containers must reserve enough width/height so the animation is not clipped or collapsed.

## Safety invariants
- No changes to price_workflow.py, media_workflow.py, scraping/canonical/resolution logic, OCR/Mistral provider logic, updater logic, or release logic.
- No fake stage percentages.
- Existing public callbacks and widget names used by event handlers remain stable unless a test proves a visual wrapper can safely change them.
- Error/completion semantics remain unchanged.

## Verification
- Add UI contract tests that assert the larger dedicated progress layout and preserved workflow calls/event methods.
- Run full regression suite and optional capability registry.
- Build/smoke gate before any merge to release/windows.
- Never touch main.
