# Arquitectura de runtime y capacidades

Este documento complementa `ARCHITECTURE_PRODUCT_INTELLIGENCE.md` y define cómo debe organizarse el ejecutable, las dependencias y las capacidades opcionales.

## Objetivo

Mantener un núcleo pequeño, estable y testeable. Las herramientas pesadas deben cargarse solo cuando aportan valor real.

```text
DESKTOP / CLI / API
        ↓
APPLICATION CORE
        ↓
IDENTITY + DISCOVERY + EVIDENCE + NORMALIZATION + EXCEL
        ↓
CAPABILITY PORTS
   ├─ browser
   ├─ vision
   ├─ ocr
   ├─ documents
   └─ ai
```

La lógica de negocio nunca debe depender directamente de una librería pesada si puede depender de una interfaz/capacidad.

## 1. Núcleo obligatorio

El núcleo puede depender de librerías razonablemente pequeñas y necesarias en casi todas las ejecuciones:

- requests
- beautifulsoup4
- lxml
- pydantic
- rapidfuzz
- PyMuPDF
- openpyxl
- Pillow
- extruct

No pertenecen al núcleo:

- FastAPI / Uvicorn
- Typer
- Playwright
- OpenCV
- PaddleOCR / PaddlePaddle
- Docling
- PyInstaller
- pytest

## 2. Capacidades opcionales

### browser

Playwright. Se usa para páginas dinámicas, DOM renderizado, respuestas XHR/fetch y galerías que no existen en el HTML inicial.

### vision

OpenCV headless + NumPy. Se usa para análisis de imágenes cuando URL/metadata no bastan:

- dimensiones reales;
- detección de imágenes casi duplicadas;
- blur/calidad básica;
- comparación perceptual;
- apoyo para separar thumbnails de imágenes de producto.

No se usa para decidir identidad por sí solo.

### ocr

PaddleOCR/PaddlePaddle como capacidad avanzada y opcional. Solo se activa como último recurso sobre documentos/imágenes ya validados por identidad.

Regla:

```text
texto estructurado disponible → NO OCR
PDF con text layer → NO OCR
imagen/PDF escaneado relevante → OCR opcional
```

El texto OCR siempre tiene penalización de confianza y conserva la imagen/página origen.

### documents

Docling u otros parsers avanzados. Complementan PyMuPDF para tablas/documentos difíciles. No son requisito del EXE estándar.

### api

FastAPI + Uvicorn + python-multipart. Solo para despliegues como servicio; nunca deben inflar el EXE de escritorio.

### cli

Typer. Solo para interfaz de línea de comandos.

### ai

La IA permanece como enriquecedor opcional sobre evidencia previamente validada. Nunca reemplaza identidad ni evidencia.

## 3. Dos pipelines coordinadas

### A. Product Intelligence

```text
identidad exacta
→ descubrimiento
→ extracción multicapas
→ evidencia cruda
→ normalización semántica
→ unidades
→ traducción controlada
→ conflictos
→ confianza
→ validación lógica
→ JSON maestro
→ contrato Excel
→ Excel
```

### B. Media Intelligence

```text
fuente exacta validada
→ localizar galería estructurada
→ JSON/JS/DOM/XHR/srcset/zoom
→ validar SKU/variante/color
→ canonicalizar URLs
→ obtener dimensiones/calidad
→ deduplicar
→ OpenCV opcional para casi-duplicados
→ ordenar hero/vistas/detalles/lifestyle
→ Imagen principal + Imagen2..ImagenN
```

Media Intelligence produce evidencias, no escribe directamente el Excel.

## 4. OCR y visión no deben contaminar el núcleo

Las importaciones de capacidades pesadas deben ser lazy/condicionales.

Correcto:

```python
if capabilities.ocr.available:
    adapter = load_ocr_adapter()
```

Incorrecto:

```python
import paddleocr
import cv2
```

en un módulo cargado siempre por `desktop.py`, `batch.py` o `pipeline.py`.

Si una capacidad no está instalada, el flujo continúa con las capas disponibles y registra `CAPABILITY_UNAVAILABLE`; no debe cerrarse la aplicación.

## 5. Perfiles de instalación

```text
base       → motor determinístico
browser    → base + Playwright
vision     → base + OpenCV headless
ocr        → base + visión + PaddleOCR
documents  → base + Docling
api        → base + servidor HTTP
cli        → base + Typer
desktop    → base + browser + PyInstaller
dev        → pytest y herramientas de prueba
full       → capacidades avanzadas, no recomendado para EXE estándar
```

## 6. Política del EXE

El EXE estándar debe incluir:

- núcleo;
- interfaz desktop;
- Playwright y Chromium cuando el build los empaquete;
- parsers necesarios para HTML/PDF/Excel.

Debe excluir explícitamente:

- OCR pesado;
- OpenCV/NumPy si no se usa en ese perfil;
- Docling;
- FastAPI/Uvicorn;
- Typer/CLI;
- pytest;
- herramientas de desarrollo.

Puede existir en el futuro un build `ProductIntelligence-Full`, separado del estándar, si se decide distribuir OCR local.

## 7. Principio de degradación elegante

Cada capability debe poder responder:

```text
AVAILABLE
UNAVAILABLE
FAILED
NOT_NEEDED
```

La ausencia de una capacidad opcional nunca puede convertir una ejecución normal en crash.

## 8. Limpieza de código

Antes de borrar un módulo antiguo:

1. buscar imports/referencias;
2. correr toda la suite;
3. correr integración real;
4. eliminarlo solo si no participa en producción ni en migración explícita.

Los módulos legacy que deban permanecer deben marcarse como compatibilidad/migración y no ser importados desde el camino principal.

## 9. Workflows de GitHub

El repositorio limpio debe tender a solo tres responsabilidades:

- `ci.yml`: tests/regresiones en cada push/PR;
- `build-windows.yml`: build del EXE solo si CI lógico pasa;
- `integration-smoke.yml`: prueba real/manual de scraping e imágenes.

Los workflows temporales `apply-*`, `fix-*` y pruebas puntuales de una corrección deben eliminarse después de que el cambio quede incorporado al código.

## 10. Criterio final

Agregar una librería no es una mejora si:

- no existe un adapter que la use;
- no mejora una etapa concreta;
- se carga siempre aunque rara vez se necesite;
- aumenta el EXE sin una ganancia medible.

La arquitectura prioriza:

```text
exactitud + trazabilidad + cobertura
con
mínimo acoplamiento + mínimo peso permanente
```
