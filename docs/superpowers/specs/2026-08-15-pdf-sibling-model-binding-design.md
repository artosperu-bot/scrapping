# PDF Sibling Model Binding Design

## Goal
Prevent final PDF evidence from being accepted when the PDF filename/URL is explicitly bound to a sibling model different from the user-provided model, while preserving valid PDFs whose URL is bound to the requested model.

## Scope
- Keep user-provided model as canonical input.
- Do not expand automatic model/brand discovery.
- Modify only PDF identity validation and its regression tests.
- Preserve fail-closed behavior.

## Design
Before accepting a PDF by brand+model text evidence, inspect model-like tokens in the PDF URL. Normalize the requested model to a compact alphanumeric code and compare it with URL tokens that contain digits. If a URL token has the same alphabetic skeleton as the requested model but a different compact value, treat it as an explicit sibling-model conflict and reject the PDF.

Examples:
- Requested `HL-L2460DW`, URL contains `hll2480dw` -> reject.
- Requested `P2422H`, URL contains `p2422h` -> allow normal validation.
- URLs without a model-like binding -> keep existing content-based behavior.

## Safety
The conflict rule is intentionally narrow: it requires a model-like URL token with digits and the same alphabetic skeleton as the requested model. It does not reject generic document IDs or unrelated numeric tokens.

## Verification
Add regression tests for the Brother sibling-model rejection and Dell exact-model URL acceptance, then run the focused PDF identity test file and the existing CI/source-validation workflows.