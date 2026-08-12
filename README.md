# Product Intelligence 0.10

Aplicación de escritorio para completar plantillas de catálogo a partir de **productos identificados con precisión y evidencia pública trazable**, sin mezclar modelos, variantes ni datos comerciales del vendedor.

## Regla principal: Excel primero

El motor **no empieza scrapeando Internet**. Primero entiende la plantilla que debe llenar.

```text
EXCEL
  ↓
encabezados + IDs + descripciones + requerido/opcional + listas válidas
  ↓
template_contract.json
  ↓
qué datos son identidad / scrapeables / derivados / imágenes / vendedor / marketplace
  ↓
recién entonces identificar y buscar el producto exacto
  ↓
extraer evidencia útil
  ↓
resolver campo por campo
  ↓
validar el formato que exige el Excel
  ↓
llenar celdas + trazabilidad
```

La descripción situada sobre una columna forma parte del contrato. Si explica mejor la intención que el nombre corto del encabezado, esa descripción debe guiar la semántica y el formato final.

Ejemplo:

```text
CuentaConBluetooth #1568
"Selecciona si el producto cuenta con bluetooth."
Syntax: One value from the list
```

El motor entiende `bluetooth` como el concepto a demostrar y devuelve exactamente una opción permitida por la plantilla, por ejemplo `Sí` o `No`.

## Lo que nunca se inventa por scraping

Los campos comerciales/operativos del vendedor se preservan pero no se buscan en Internet para sustituirlos:

- SKU del vendedor;
- cantidad/stock de Falabella;
- precio y precio oferta;
- fechas de oferta;
- SKU padre cuando es una relación administrada por el vendedor;
- garantía del vendedor;
- otros campos comerciales equivalentes.

La categoría/condición del marketplace también se mantiene separada de las especificaciones técnicas cuando corresponde.

## Flujo de producto

Una vez conocido el contrato del Excel:

```text
identidad inicial / Part Number
  ↓
validar producto y variante exacta
  ↓
fuentes oficiales primero + fallbacks confiables
  ↓
HTML / source / JSON-LD / JS / XHR/API / DOM / PDF
  ↓
evidencia cruda
  ↓
normalización semántica y de unidades
  ↓
traducción técnica controlada
  ↓
conflictos + confianza + validación lógica
  ↓
JSON de producto
  ↓
resolver únicamente los objetivos del contrato Excel
```

**No encontrado / no demostrado = vacío.** Una fuente parecida o una variante cercana nunca autoriza a inventar el dato.

## Imágenes

Las columnas `Imagen principal`, `Imagen2`…`ImagenN` determinan cuántos slots de media necesita la plantilla. Si existen 8 columnas, la capa de Media Intelligence debe intentar recuperar hasta 8 imágenes válidas de la variante exacta.

La galería se busca en JSON-LD, JSON/JavaScript, `src/srcset`, atributos lazy/zoom, `<picture>`, sliders y endpoints XHR/API. Se eliminan logos, banners, relacionados, otras variantes y duplicados, conservando preferentemente la mayor resolución.

## Fotos y videos — proceso independiente

El escritorio incluye la pestaña **7. Fotos y videos**. Este flujo no modifica la plantilla ni llama al proceso que genera el Excel.

Para cada producto usa esta prioridad:

```text
URLs manuales del producto
  ↓
búsqueda web por Part Number / identificador / modelo
  ↓
fabricante y fuentes oficiales primero
  ↓
JSON-LD / JSON embebido / Open Graph / HTML / recursos de red
  ↓
Playwright y activación de media lazy cuando hace falta
  ↓
validación del modelo
  ↓
descarga + miniatura en vivo + metadata
```

En este proceso multimedia el **color no bloquea** una imagen si corresponde al mismo modelo validado. Las diferencias que pueden indicar otro producto, como capacidad o variante materialmente distinta, siguen protegidas.

Las imágenes y los videos directos se guardan físicamente. Videos externos de YouTube/Vimeo y streams HLS se conservan como enlace/metadata cuando no existe un archivo directo descargable.

La salida queda separada por identificador:

```text
<salida>/multimedia/
  fotos/<PART_NUMBER_O_ID>/
    01.jpg
    02.webp
    metadata.json
  videos/<PART_NUMBER_O_ID>/
    01.mp4
    metadata.json
```

Las miniaturas aparecen en la pestaña a medida que se descargan. Un doble clic abre el archivo local; si el video es externo, abre su URL.

## Salidas

Cada ejecución batch genera:

- `template_contract.json` — qué pide realmente la plantilla;
- `json/<identificador>.json` — producto y evidencia;
- `trazabilidad.json` — por qué se escribió/rechazó cada celda;
- `resumen.json` — estado global;
- `<plantilla>_completado.xlsx`.

El proceso independiente de multimedia genera además las carpetas `multimedia/fotos/` y `multimedia/videos/` descritas arriba.

## Arquitectura y reglas

- [`EXCEL_CONTRACT.md`](EXCEL_CONTRACT.md) — contrato de entrada y clasificación de columnas.
- [`ARCHITECTURE_PRODUCT_INTELLIGENCE.md`](ARCHITECTURE_PRODUCT_INTELLIGENCE.md) — evidencia, identidad, normalización, conflictos y media.
- [`ARCHITECTURE_RUNTIME_AND_CAPABILITIES.md`](ARCHITECTURE_RUNTIME_AND_CAPABILITIES.md) — núcleo ligero, navegador y capacidades opcionales.

## Capacidades

El ejecutable estándar mantiene un núcleo ligero. Las capacidades pesadas se cargan solo cuando se instalan explícitamente:

- `browser` — Playwright para páginas dinámicas;
- `vision` — OpenCV para calidad/deduplicación de imágenes;
- `ocr` — PaddleOCR como último recurso;
- `documents` — parsing avanzado con Docling;
- `api` / `cli` — interfaces opcionales.

OCR no debe ejecutarse cuando HTML, JSON o PDF de texto ya ofrecen evidencia suficiente.

## Ejecutar en Windows

Sin compilar:

```bat
INSTALAR_Y_ABRIR_WINDOWS.bat
```

Crear el EXE:

```bat
CONSTRUIR_EXE_WINDOWS.bat
```

Salida esperada:

```text
dist\ProductIntelligence\ProductIntelligence.exe
```

El build ejecuta regresiones antes de publicar el ejecutable.

## Desarrollo

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Los tests unitarios no bastan para declarar terminado el scraper. Las mejoras de extracción deben validarse también con part numbers reales, plantilla real, trazabilidad y control de variante.
