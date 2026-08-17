from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Iterable


@dataclass(frozen=True)
class Capability:
    name: str
    modules: tuple[str, ...]
    purpose: str

    @property
    def available(self) -> bool:
        return all(find_spec(module) is not None for module in self.modules)

    def status(self) -> str:
        return "AVAILABLE" if self.available else "UNAVAILABLE"


CAPABILITIES: dict[str, Capability] = {
    "browser": Capability(
        "browser",
        ("playwright",),
        "DOM dinámico, XHR/fetch y galerías renderizadas",
    ),
    "vision": Capability(
        "vision",
        ("cv2", "numpy"),
        "calidad, dimensiones y deduplicación perceptual de imágenes",
    ),
    "ocr": Capability(
        "ocr",
        ("rapidocr", "onnxruntime"),
        "OCR local CPU de último recurso para documentos o imágenes sin capa de texto",
    ),
    "documents": Capability(
        "documents",
        ("docling",),
        "parsing avanzado de documentos/tablas difíciles",
    ),
    "api": Capability(
        "api",
        ("fastapi", "uvicorn"),
        "ejecución como servicio HTTP",
    ),
    "cli": Capability(
        "cli",
        ("typer",),
        "interfaz de línea de comandos",
    ),
}


def get_capability(name: str) -> Capability:
    try:
        return CAPABILITIES[name]
    except KeyError as exc:
        raise ValueError(f"Capacidad desconocida: {name}") from exc


def capability_status(names: Iterable[str] | None = None) -> dict[str, str]:
    selected = list(names) if names is not None else list(CAPABILITIES)
    return {name: get_capability(name).status() for name in selected}


def is_available(name: str) -> bool:
    return get_capability(name).available
