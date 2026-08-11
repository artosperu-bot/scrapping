from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from .capabilities import is_available


@dataclass(frozen=True)
class ImageAnalysis:
    width: int
    height: int
    aspect_ratio: float
    megapixels: float
    brightness_stddev: float
    sharpness: float | None = None
    perceptual_hash: str | None = None
    backend: str = "pillow"


def _pillow_analysis(path: str | Path) -> ImageAnalysis:
    with Image.open(path) as image:
        image = image.convert("L")
        width, height = image.size
        stat = ImageStat.Stat(image)
        return ImageAnalysis(
            width=width,
            height=height,
            aspect_ratio=round(width / height, 4) if height else 0.0,
            megapixels=round((width * height) / 1_000_000, 4),
            brightness_stddev=round(float(stat.stddev[0]), 3),
        )


def analyze_image(path: str | Path, *, advanced: bool = True) -> ImageAnalysis:
    """Analyze an already downloaded/validated product image.

    Pillow is always available. OpenCV is imported only when the optional
    `vision` capability is installed. Image content never establishes product
    identity by itself; it only supports quality/ranking/deduplication.
    """
    base = _pillow_analysis(path)
    if not advanced or not is_available("vision"):
        return base

    import cv2  # lazy optional import

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return base

    variance = float(cv2.Laplacian(img, cv2.CV_64F).var())
    small = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
    mean = float(small.mean())
    bits = (small > mean).flatten().tolist()
    phash = "".join(f"{int(''.join('1' if b else '0' for b in bits[i:i+4]), 2):x}" for i in range(0, 64, 4))

    return ImageAnalysis(
        width=base.width,
        height=base.height,
        aspect_ratio=base.aspect_ratio,
        megapixels=base.megapixels,
        brightness_stddev=base.brightness_stddev,
        sharpness=round(variance, 3),
        perceptual_hash=phash,
        backend="opencv",
    )


def hamming_distance(hash_a: str | None, hash_b: str | None) -> int | None:
    if not hash_a or not hash_b or len(hash_a) != len(hash_b):
        return None
    try:
        a = int(hash_a, 16)
        b = int(hash_b, 16)
    except ValueError:
        return None
    return (a ^ b).bit_count()


def likely_duplicate(a: ImageAnalysis, b: ImageAnalysis, *, max_hamming: int = 6) -> bool:
    """Conservative near-duplicate helper for gallery ranking.

    URL canonicalization remains the first dedupe layer. This helper is only
    used when both images have advanced perceptual hashes.
    """
    distance = hamming_distance(a.perceptual_hash, b.perceptual_hash)
    if distance is None:
        return False
    return distance <= max_hamming
