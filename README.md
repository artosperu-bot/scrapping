# Product Intelligence V9

Aplicación de escritorio para **identificar productos, descubrir fuentes públicas, extraer datos técnicos y completar plantillas Excel sin mezclar modelos/variantes**.

> **Documento obligatorio de arquitectura:** [`ARCHITECTURE_PRODUCT_INTELLIGENCE.md`](ARCHITECTURE_PRODUCT_INTELLIGENCE.md)
>
> Toda mejora futura debe seguir esa pipeline: identidad exacta → evidencias crudas → normalización semántica → unidades → traducción controlada → conflictos → confianza → JSON maestro → contrato Excel → salida y trazabilidad.
>
> En especial, la extracción de imágenes debe tratar la **galería oficial completa** como una entidad estructurada. Encontrar una imagen válida no autoriza a detener la búsqueda si la misma ficha contiene más imágenes del SKU exacto.

## Qué hace

1. Lee la plantilla Excel y detecta automáticamente:
   - fila de atributos;
   - fila de instrucciones;
   - listas de opciones;
   - columnas de identidad, especificaciones, imágenes y datos del vendedor.
2. Detecta productos a partir de MPN/Part Number, EAN/UPC/GTIN, modelo, marca y nombre disponibles en cada fila.
3. Busca candidatos en web cuando no se proporcionó URL.
4. Valida **identidad antes de extraer**.
   - Si existe MPN/EAN/UPC/GTIN de entrada, se exige coincidencia fuerte incluso en la web del fabricante.
   - Una fuente secundaria/marketplace solo entra con identidad `EXACT`.
   - Un conflicto de MPN/EAN/GTIN/variante descarta la fuente.
   - Una página de familia/categoría que contiene el MPN no puede aportar indiscriminadamente especificaciones de otros productos de la página.
5. Extrae candidatos desde varias capas:
   - HTML/source HTML;
   - JSON-LD / Microdata / RDFa;
   - variables JavaScript embebidas;
   - XHR/fetch/API/GraphQL observados por Chromium;
   - DOM renderizado;
   - PDFs oficiales enlazados;
   - galerías e imágenes asociadas a la variante;
   - OCR solo como último recurso cuando no hay texto estructurado utilizable.
6. Conserva primero **evidencia cruda** antes de traducir o normalizar.
7. Valida cada PDF/XHR/imagen contra la identidad antes de usarlo.
8. Normaliza atributos, valores y unidades sin perder el valor original.
9. Detecta conflictos entre fuentes en vez de escoger simplemente la primera respuesta.
10. Para cada columna del Excel crea un contrato semántico usando conjuntamente:
   - encabezado;
   - ID externo;
   - descripción/instrucción;
   - sintaxis;
   - opciones válidas;
   - contexto producto/paquete.
11. Formatea el valor según lo que **el Excel espera**, no según cómo lo expresa la página.
12. Solo escribe una celda cuando la evidencia pasa los controles. Si no, queda vacía y se registra el motivo en `trazabilidad.json`.

## Regla principal

> **No encontrado / no demostrado = vacío. Nunca se completa con otro producto o variante parecida.**

Esta regla no significa abandonar información disponible. Si una fuente oficial exacta contiene varias especificaciones o varias imágenes válidas del mismo SKU, el motor debe intentar recuperarlas todas.

## Imágenes

La galería no se forma con todos los `<img>` de la página y tampoco se limita a la primera imagen válida.

El motor debe inspeccionar, cuando existan:

- JSON-LD `Product.image`;
- arrays de media en JSON/JavaScript;
- `src`, `srcset`, `data-src`, `data-srcset`, `data-zoom-image`, `data-large`;
- `<picture>` / `<source>`;
- sliders/carruseles del producto;
- endpoints XHR/API de media;
- OpenGraph como respaldo.

Clasificación:

- `product_gallery` → elegible;
- `product_video` → elegible cuando corresponde;
- `page_asset` → logo/icono/badge/footer, nunca se sube;
- `unknown_image` → no se autocompleta.

Además valida modelo, MPN/EAN cuando aparecen, capacidad/color/variante y procedencia desde la página validada. Imágenes del mismo archivo con distintos tamaños (`sw`, `sh`, `w`, `h`, etc.) se deduplican conservando preferentemente la versión de mayor calidad.

Si la ficha oficial exacta muestra 5 imágenes válidas y el Excel admite 8, el resultado esperado es llenar `Imagen principal` + `Imagen2`…`Imagen5`, no detenerse después de `Imagen principal`.

Las reglas completas están en [`ARCHITECTURE_PRODUCT_INTELLIGENCE.md`](ARCHITECTURE_PRODUCT_INTELLIGENCE.md).

## Campos del vendedor

Precio, stock, promociones, SKU propio, garantía del vendedor y otros datos comerciales no se inventan por scraping. Se protegen. Los valores que la propia plantilla declara explícitamente como ejemplos pueden eliminarse para evitar subir datos ficticios.

## Ejecutar en Windows sin compilar

Doble clic en:

`INSTALAR_Y_ABRIR_WINDOWS.bat`

La primera ejecución instala dependencias y Chromium de Playwright.

## Crear el EXE de Windows

Doble clic en:

`CONSTRUIR_EXE_WINDOWS.bat`

Al terminar tendrás:

`dist\ProductIntelligence\ProductIntelligence.exe`

Se genera como aplicación `onedir` para que Chromium y sus recursos viajen junto al EXE de manera estable.

## Uso de la interfaz

1. Elegir el Excel.
2. Elegir carpeta de salida.
3. Mantener activado **Sobrescribir valores existentes** cuando quieres recalcular campos del producto; los datos comerciales del vendedor siguen protegidos.
4. Pegar part numbers manualmente si se desea usar el modo directo.
5. Pulsar **EJECUTAR SCRAPING Y COMPLETAR EXCEL**.

Salida:

- `<plantilla>_completado.xlsx`
- `json/<identificador>.json`
- `trazabilidad.json`
- `resumen.json`

## Reprocesar JSON antiguos

La interfaz incluye **Reprocesar JSON antiguos...**. Sirve para pasar resultados anteriores por los controles actuales sin volver a scrapear, útil para auditoría y migración.

## 403 / páginas dinámicas

Se intenta HTTP normal primero. Si una página pública necesita JavaScript/cookies, se abre Chromium real con Playwright. No se implementan CAPTCHA solvers, plugins stealth ni evasión de controles de acceso. Si la fuente sigue bloqueada, se descarta y se prueba otra fuente candidata exacta.

## Pruebas

Ejecutar:

```bat
.venv\Scripts\activate
pytest -q
```

Las pruebas unitarias no son suficientes para declarar una mejora terminada. También se requiere prueba real con varios part numbers, plantilla Excel real, revisión de trazabilidad y comparación entre la **cantidad visible de imágenes válidas en la galería oficial y la cantidad realmente extraída**.

## IA asistida opcional

La IA es una capa opcional, no una autoridad:

```text
web/PDF/API/imagenes
  -> identidad exacta
  -> evidencia limpia
  -> normalizacion/resolucion
  -> IA opcional para descripcion/casos ambiguos
  -> validacion deterministica final
  -> Excel
```

La IA recibe únicamente evidencias ya scrapeadas y validadas para el producto. Debe devolver los IDs de evidencia usados. No puede completar datos del vendedor, no puede decidir que otra variante es equivalente y no puede inventar números.

### Proveedores

- `ollama`: para usar un modelo local en tu PC. Base URL habitual: `http://127.0.0.1:11434`.
- `openai_compatible`: para cualquier endpoint que implemente `/chat/completions`. La URL, modelo y API key se configuran en la app.

La IA viene **apagada por defecto**. El sistema funciona sin ella.

## Modo directo por Part Number

La app permite pegar uno o varios **part numbers** directamente.

1. Selecciona el Excel.
2. Pega los part numbers, uno por línea o separados por coma/punto y coma.
3. Opcionalmente activa IA.
4. Ejecuta el proceso.

Si el cuadro de part numbers está vacío, el programa detecta identidades desde el Excel. Si se ingresan part numbers manualmente, se asignan en orden a las primeras filas de producto de la hoja de carga detectada. El part number se usa como identidad de búsqueda; **no se copia silenciosamente al SKU del vendedor**.

La búsqueda usa varios backends públicos de descubrimiento y toda URL encontrada pasa después por validación estricta de identidad antes de extraer o escribir datos.

El archivo `.gitignore` excluye entornos, builds, Chromium de Playwright, claves/API, Excel locales y salidas generadas.
