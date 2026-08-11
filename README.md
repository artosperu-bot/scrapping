# Product Intelligence V8

Aplicación de escritorio para **identificar productos, descubrir fuentes públicas, extraer datos técnicos y completar plantillas Excel sin mezclar modelos/variantes**.

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
5. Extrae, si son válidos:
   - HTML renderizado;
   - JSON-LD / Microdata;
   - tablas y pares atributo/valor;
   - respuestas XHR/fetch observadas por Chromium;
   - PDFs enlazados desde la página validada;
   - imágenes y videos asociados.
6. Valida **cada PDF/XHR/imagen** contra la identidad antes de usarlo.
7. Limpia ruido de navegación, banners, newsletters, logos, iconos y heurísticas dudosas.
8. Normaliza la evidencia y la conserva en JSON.
9. Para cada columna del Excel crea un contrato semántico:
   - significado esperado;
   - contexto producto vs paquete;
   - unidad/dimensión física;
   - texto/número/lista controlada;
   - opciones válidas de la propia plantilla.
10. Solo escribe una celda cuando la evidencia pasa todos los controles. Si no, queda vacía y se registra el motivo en `trazabilidad.json`.

## Regla principal

> **No encontrado / no demostrado = vacío. Nunca se completa con otro producto o variante parecida.**

## Imágenes

La galería no se forma con todos los `<img>` de la página. V8 separa:

- `product_gallery` → elegible;
- `product_video` → elegible cuando corresponde;
- `page_asset` → logo/icono/badge/footer, nunca se sube;
- `unknown_image` → no se autocompleta.

Además valida modelo, MPN/EAN cuando aparecen, capacidad/color/variante y procedencia desde la página validada. Imágenes del mismo archivo con distintos tamaños (`sw`, `sh`, etc.) se deduplican.

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
4. Pulsar **EJECUTAR SCRAPING Y COMPLETAR EXCEL**.

Salida:

- `<plantilla>_completado.xlsx`
- `json/<identificador>.json`
- `trazabilidad.json`
- `resumen.json`

## Reprocesar JSON antiguos

La interfaz incluye **Reprocesar JSON antiguos...**. Sirve para pasar resultados de V3–V6 por los controles de V8 sin volver a scrapear, útil para auditoría y migración.

## 403 / páginas dinámicas

Se intenta HTTP normal primero. Si una página pública necesita JavaScript/cookies, se abre Chromium real con Playwright. No se implementan CAPTCHA solvers, plugins stealth ni evasión de controles de acceso. Si la fuente sigue bloqueada, se descarta y se prueba otra fuente candidata exacta.

## Pruebas

Ejecutar:

```bat
.venv\Scripts\activate
pytest -q
```

V8 incluye regresiones para ruido HTML/PDF, TBW falso, unidades incorrectas, contexto producto/paquete, conectividad wireless/wired, imágenes de otro color, iconos vs galería, autonomía y contenido de paquete.


## IA asistida opcional (V8)

V8 incorpora una capa de IA **opcional**, no una autoridad. El flujo es:

```text
web/PDF/API/imagenes
  -> identidad exacta
  -> evidencia limpia
  -> mapper deterministico
  -> IA opcional para descripcion/casos ambiguos
  -> validacion deterministica final
  -> Excel
```

La IA recibe únicamente evidencias ya scrapeadas y validadas para el producto. Debe devolver los IDs de evidencia usados. No puede completar datos del vendedor, no puede decidir que otra variante es equivalente y no puede inventar números.

### Proveedores

- `ollama`: para usar un modelo local en tu PC. Base URL habitual: `http://127.0.0.1:11434`.
- `openai_compatible`: para cualquier endpoint que implemente `/chat/completions`. La URL, modelo y API key se configuran en la app.

La IA viene **apagada por defecto**. El sistema funciona sin ella.

### Por qué usarla

Es útil para redactar una descripción comercial/técnica natural a partir de varias evidencias y para interpretar campos cuyo nombre difiere mucho entre fabricante y marketplace. No se usa para sustituir el scraper ni para inventar información faltante.


# V9 — Modo directo por Part Number

La app de escritorio ahora permite pegar uno o varios **part numbers** directamente.

1. Selecciona el Excel.
2. Pega los part numbers, uno por línea o separados por coma/punto y coma.
3. Opcionalmente activa IA.
4. Pulsa **EJECUTAR SCRAPING Y COMPLETAR EXCEL**.

Si el cuadro de part numbers está vacío, el programa mantiene el modo anterior y detecta identidades desde el Excel. Si se ingresan part numbers manualmente, se asignan en orden a las primeras filas de producto de la hoja de carga detectada. El part number se usa como identidad de búsqueda; **no se copia silenciosamente al SKU del vendedor**.

La búsqueda usa DuckDuckGo HTML y Bing HTML como backends de descubrimiento normales; toda URL encontrada pasa después por validación estricta de identidad antes de extraer o escribir datos.

El archivo `.gitignore` excluye entornos, builds, Chromium de Playwright, claves/API, Excel locales y salidas generadas.
