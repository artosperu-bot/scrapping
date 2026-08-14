from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class SourceStrategy:
    """Per-execution routing controls for product evidence acquisition and providers."""

    web: bool = True
    pdf: bool = True
    ocr: bool = True
    mistral: bool = True

    def normalized(self) -> "SourceStrategy":
        if not self.web and not self.pdf:
            raise ValueError("SOURCE_STRATEGY_REQUIRES_WEB_OR_PDF")
        if not self.pdf and self.ocr:
            return replace(self, ocr=False)
        return self

    def as_options(self) -> dict[str, bool]:
        value = self.normalized()
        return {
            "source_web_enabled": value.web,
            "source_pdf_enabled": value.pdf,
            "ocr_space_enabled": value.ocr,
            "mistral_enabled": value.mistral,
        }
