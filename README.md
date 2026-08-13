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

Los campos comerciales/operativos del vendedor se preservan pero no se buscan en Internet para sustituirlos dentro del flujo que completa el Excel:

- SKU del vendedor;
- cantidad/stock de Falabella;
- precio y precio oferta;
- fechas de oferta;
- SKU padre cuando es una relación administrada por el vendedor;
- garantía del vendedor;
- otros campos comerciales equivalentes.

La categoría/condición del marketplace también se mantiene separada de las especificaciones técnicas cuando corresponde.

> La pestaña independiente **8. Precios y competencia** sí recopila precios, stock y sellers como inteligencia comercial; esos datos no contaminan automáticamente la plantilla técnica.

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

## Imágenes para Excel

Las columnas `Imagen principal`, `Imagen2`…`ImagenN` determinan cuántos slots de media necesita la plantilla. Si existen 8 columnas, la capa de Media Intelligence debe intentar recuperar hasta 8 imágenes válidas de la variante exacta.

La galería se busca en JSON-LD, JSON/JavaScript, `src/srcset`, atributos lazy/zoom, `<picture>`, sliders y endpoints XHR/API. Se eliminan logos, banners, relacionados, otras variantes y duplicados, conservando preferentemente la mayor resolución.

## 7. Fotos y videos — proceso independiente

La pestaña **7. Fotos y videos** trabaja separada del proceso que genera el Excel.

Para cada producto usa esta prioridad:

```text
Part Number / identidad exacta
  ↓
URL oficial o búsqueda web automática
  ↓
fabricante y fuentes oficiales primero
  ↓
JSON-LD / JSON embebido / Open Graph / HTML
  ↓
Playwright + scroll + recursos de red + media lazy
  ↓
validación del producto
  ↓
galería oficial completa / video
  ↓
filtro físico + confianza + deduplicación
  ↓
descarga + miniatura en vivo + metadata
```

### Reglas de multimedia

- En una **página oficial validada** se intenta recuperar la galería completa y sus versiones de alta resolución.
- URLs de miniaturas/CDN con transformaciones de tamaño pueden promoverse a la versión grande del **mismo asset** antes de descargar.
- Se rechazan imágenes pequeñas: ancho `< 300 px`, alto `< 300 px` o área `< 120000 px²`.
- Logos, íconos, badges, banners, productos relacionados y assets de navegación no se aceptan como fotos del producto.
- En resultados externos se exige normalmente **confianza >= 0.95**.
- En páginas oficiales validadas se permite una política más flexible solo para media perteneciente a la galería/video del producto.
- El color no bloquea una imagen si corresponde al mismo modelo validado; capacidad o variante materialmente distinta siguen protegidas.
- Videos directos (`mp4`, `webm`, etc.) se descargan físicamente.
- YouTube/Vimeo/HLS se guardan como enlace + metadata cuando no existe un archivo directo descargable.
- El flujo es **official-first con fallback confiable**: si la página oficial valida el producto pero no expone un asset descargable, puede usar otra fuente con evidencia suficiente.

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

`metadata.json` conserva, cuando aplica, URL original, URL final, fuente, página origen, rol de media, confianza, dimensiones, hash, índice de galería y método de extracción.

### Progreso visual

La pestaña mantiene progreso real por etapas y global por productos. Incluye una animación GIF ligera mientras trabaja, sin sustituir las barras de progreso.

Estados representativos:

```text
pendiente → buscando → validando → extrayendo → descargando → guardando → completado
```

El 100% significa que todos los productos seleccionados terminaron su procesamiento; los errores se reportan por separado y no se ocultan.

## 8. Precios y competencia — proceso independiente

La pestaña **8. Precios y competencia** parte del Part Number/modelo y descubre ofertas automáticamente, sin exigir URLs manuales.

```text
Part Number / modelo
  ↓
identidad canónica
  ↓
MercadoLibre / VTEX cuando corresponda
  ↓
discovery web y detección de plataforma
  ↓
JSON / API / XHR / JSON-LD / HTML / Playwright
  ↓
validación del producto exacto
  ↓
extraer ofertas
  ↓
canal ≠ vendedor
  ↓
normalizar precio / moneda / stock / URL
  ↓
deduplicar + score de confianza
  ↓
histórico
```

Características:

- prioridad comercial inicial para Perú: Falabella, Ripley, MercadoLibre Perú, PlazaVea y Oechsle;
- fallback a otras fuentes cuando no existe evidencia local suficiente;
- distingue **canal/marketplace** de **seller/vendedor**;
- conserva razón social/RUC solo cuando una fuente verificable lo expone;
- maneja PEN, USD, CLP y otras monedas sin comparar importes de monedas distintas como si fueran equivalentes;
- guarda precio actual, precio lista, stock, moneda, seller, URL, timestamp y confianza cuando están disponibles;
- no acepta un producto parecido solo porque tenga precio: primero valida identidad.

Histórico:

```text
<salida>/price_intelligence/
  latest.json
  history.jsonl
  sellers.json
```

## Salidas

Cada ejecución batch del Excel genera:

- `template_contract.json` — qué pide realmente la plantilla;
- `json/<identificador>.json` — producto y evidencia;
- `trazabilidad.json` — por qué se escribió/rechazó cada celda;
- `resumen.json` — estado global;
- `<plantilla>_completado.xlsx`.

Los procesos independientes generan además:

- `multimedia/fotos/` y `multimedia/videos/`;
- `price_intelligence/` para precios, sellers e histórico.

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

GitHub Actions también construye el paquete de Windows y publica el artifact **`ProductIntelligence-Windows`**. El build ejecuta las regresiones, instala Chromium empaquetado, construye con PyInstaller y verifica que `ProductIntelligence.exe` exista antes de publicar el artifact.

### Build verificado 2026-08-12

Código de aplicación verificado: `e9a375fea74c300de559fdac0a0df9cd368bf2e4`.

Workflow **Build Windows EXE #130**:

```text
regresión Windows       PASS
Chromium empaquetado    PASS
PyInstaller             PASS
ProductIntelligence.exe PASS
artifact Windows        PASS
```

Artifact publicado: `ProductIntelligence-Windows` (~423 MB).

## Desarrollo

```bash
pip install -e ".[dev]"
python -m pytest -q
```

Los tests unitarios no bastan para declarar terminado el scraper. Las mejoras de extracción deben validarse también con Part Numbers reales, páginas reales, trazabilidad y control de variante. El módulo multimedia tiene además un smoke test real que verifica productos concretos, filtrado de imágenes pequeñas y funcionamiento del fallback de fuentes.
