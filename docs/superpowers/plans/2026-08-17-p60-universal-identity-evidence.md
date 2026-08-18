# P60 Universal Product Identity & Evidence Hardening — Implementation Plan

## Goal

Convert the existing evidence pipeline into a precision-first universal resolution layer without rewriting working WEB/PDF/OCR/Mistral/Excel components and without touching PR #63. The new layer must resolve identity first, route to high-authority sources sequentially, reject sibling variants, preserve field-level provenance, and fail closed before extraction/write.

## Non-negotiable invariants

- No brand/MPN/URL hardcoding for JBL or regression products.
- Contradiction vetoes similarity.
- Only EXACT_SKU or EXACT_MODEL document relationships may feed extraction.
- UNKNOWN, RELATED_FAMILY, SIBLING_VARIANT, UNRELATED are rejected from extraction.
- Provenance must never override a hard identity conflict.
- Search budgets are ceilings, not targets; early stop when sufficient evidence exists.
- WEB remains existing fallback, not a new parallel crawler.
- PR #63 remains isolated and untouched.

## Task 1 — Deterministic Product ↔ Document matcher

Create `product_document_matcher.py` with ProductFingerprint, DocumentFingerprint, ProductDocumentMatch and relationship classes: EXACT_SKU, EXACT_MODEL, SIBLING_VARIANT, RELATED_FAMILY, UNRELATED, UNKNOWN.

RED tests first for:
- exact MPN → EXACT_SKU
- exact functional model → EXACT_MODEL
- Wireless target vs Wired document → SIBLING_VARIANT
- Wireless target vs USB-C wired sibling → SIBLING_VARIANT
- same family only → UNKNOWN/RELATED_FAMILY, never accepted
- numeric/model sibling collision → SIBLING_VARIANT/RELATED_FAMILY
- generic non-JBL regression

## Task 2 — Integrate matcher into PDF evidence gate

Delegate `validate_pdf_identity()` to the matcher while preserving backward-compatible fields. Enforce accepted=true only for EXACT_SKU / EXACT_MODEL. Add relationship, hard_conflicts, positive_evidence and negative_evidence to diagnostics.

In `pdf_review.py`, block provenance binding when the matcher reports any hard conflict or a terminal non-exact relationship.

## Task 3 — Identity monotonicity and field-level evidence

Preserve stronger existing identity facts when low-confidence refinements arrive. Record source/confidence/evidence for identity fields and prohibit lower-quality observations from replacing higher-quality resolved values.

## Task 4 — Sequential authority router + budgets + early stop

Integrate with existing source/provider architecture instead of replacing it. Add source tiers, configurable budgets, missing-field routing, SOURCE_BLOCKED transitions, and early-stop evaluation. WEB remains the final limited fallback.

## Task 5 — Final evidence/write barrier

Before Excel write require: valid product identity, field evidence, allowed authority, no unresolved hard conflict, and field scope compatible with SKU/model evidence. Model-scope documents cannot prove SKU-sensitive fields without SKU evidence.

## Task 6 — Deterministic generalization matrix

Build stable fixtures across >=5 brands, >=5 categories and >=12 real products where existing legal/reproducible fixtures permit. Include exact, sibling trap, cosmetic/regional SKU, numeric collision and no-evidence cases.

## Task 7 — Live discovery + packaged desktop certification

After deterministic QA is green, run live discovery separately and report external drift distinctly from internal regressions. Then certify the packaged `.exe` route. Do not merge/release until deterministic QA, generalized QA, JBL regression and packaged E2E gates are all demonstrated.
