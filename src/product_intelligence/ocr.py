from __future__ import annotations
import io, tempfile
from pathlib import Path
import requests
from PIL import Image
from .web_fetch import UA


def ocr_image_bytes(data: bytes) -> list[dict]:
    """OCR opcional con PaddleOCR. Devuelve texto y score. No inventa atributos."""
    try:
        import numpy as np
        from paddleocr import PaddleOCR
    except Exception as e:
        raise RuntimeError("OCR no instalado. Instala: pip install -e '.[ocr]'") from e
    image = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    result = ocr.ocr(image, cls=True)
    out=[]
    for block in result or []:
        for item in block or []:
            if len(item)>=2 and item[1]:
                text, score=item[1]
                out.append({"text":text,"confidence":float(score)})
    return out


def ocr_image_url(url: str, timeout: int=30) -> list[dict]:
    r=requests.get(url,timeout=timeout,headers={"User-Agent":UA}); r.raise_for_status()
    return ocr_image_bytes(r.content)
