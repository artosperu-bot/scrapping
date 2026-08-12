# Media Official Gallery + Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mejorar el módulo multimedia para extraer galerías y videos de fichas oficiales, rechazar imágenes pequeñas/ruido, exigir 0.95+ a fuentes externas y mostrar una animación GIF junto al progreso real.

**Architecture:** Se conserva `run_media_product` como orquestador independiente. La clasificación de páginas oficiales y la política de elegibilidad quedan en `media_workflow.py`; la validación física de dimensiones queda en `media_downloader.py`; la extracción de galería/video se amplía en `media_discovery.py`; la UI de progreso carga un GIF local con fallback al dibujo actual.

**Tech Stack:** Python 3.12, requests, BeautifulSoup/lxml, Pillow, Tkinter, Playwright existente, pytest.

## Global Constraints

- No modificar `run_batch` ni el flujo de precios.
- Part Number/modelo sigue siendo la identidad principal.
- Página oficial validada: aceptar galería principal aunque el score individual sea menor a 0.95.
- Fuente externa: aceptación automática solo con confianza >= 0.95.
- Rechazar imágenes con ancho < 300 px, alto < 300 px o área < 120000 px², salvo metadatos-only de video.
- No aceptar assets de UI, logos, badges, productos relacionados ni conflictos de identidad.
- Videos directos MP4/WebM/MOV se descargan; YouTube/Vimeo/HLS quedan como metadata/enlace.
- Progreso debe seguir basado en eventos reales; el GIF es decorativo y no controla el porcentaje.

---

### Task 1: Política de fuente oficial y confianza

**Files:**
- Modify: `src/product_intelligence/media_workflow.py`
- Test: `tests/test_media_workflow.py`

**Interfaces:**
- Produces: `_is_official_product_page(url, identity, discovery_source) -> bool`, `_eligible_media(row, *, official_page=False) -> bool`.

- [ ] Agregar tests: externo con 0.94 se rechaza; externo 0.95 se acepta; galería oficial validada puede aceptar 0.90; conflictos y `page_asset` siempre se rechazan.
- [ ] Ejecutar `python -m pytest tests/test_media_workflow.py -q` y confirmar RED.
- [ ] Implementar política mínima sin tocar el resto del pipeline.
- [ ] Ejecutar el archivo de tests y confirmar GREEN.

### Task 2: Galería y video de ficha oficial

**Files:**
- Modify: `src/product_intelligence/media_discovery.py`
- Test: `tests/test_media_discovery.py`

**Interfaces:**
- Produces filas `dict` con `role="product_gallery"` o `role="product_video"`, `gallery_index`, `provider`, `url` absoluta y evidencia de origen.

- [ ] Agregar fixtures HTML con carrusel (`srcset`, `data-zoom`, thumbnails), `VideoObject`, iframe YouTube y fuente MP4.
- [ ] Ejecutar tests específicos y confirmar RED.
- [ ] Extraer URL de mayor resolución por `srcset`, normalizar URLs relativas y deduplicar por URL canónica.
- [ ] Marcar medios de galería/video sin promover productos relacionados.
- [ ] Ejecutar tests específicos y confirmar GREEN.

### Task 3: Filtro físico de imágenes pequeñas

**Files:**
- Modify: `src/product_intelligence/media_downloader.py`
- Test: `tests/test_media_downloader.py`

**Interfaces:**
- `download_media_item(...)` agrega `width`, `height`, `pixel_area` y devuelve `reason="image_too_small"` sin conservar archivo rechazado.

- [ ] Crear tests con imágenes Pillow 120x120, 299x500, 400x250 y 800x800.
- [ ] Ejecutar tests y confirmar RED.
- [ ] Después de descargar imagen a `.part`, abrir con Pillow, validar dimensiones y borrar temporal si no cumple.
- [ ] Mantener checksum/deduplicación para imágenes aceptadas.
- [ ] Ejecutar tests y confirmar GREEN.

### Task 4: Metadata y eventos de trazabilidad

**Files:**
- Modify: `src/product_intelligence/media_workflow.py`
- Modify: `src/product_intelligence/media_downloader.py`
- Test: `tests/test_media_workflow.py`

**Interfaces:**
- Cada resultado guarda `page_url`, `page_discovery_source`, `official_page`, `role`, dimensiones cuando existan y razón de rechazo cuando corresponda.

- [ ] Testear que medios rechazados por tamaño no entren en resultados descargados y que videos metadata-only sí queden registrados.
- [ ] Emitir eventos `stage`/`media_rejected` para progreso/log sin bloquear el producto.
- [ ] Confirmar GREEN.

### Task 5: GIF animado con fallback seguro

**Files:**
- Create: `src/product_intelligence/assets/wolf_search.gif`
- Modify: `src/product_intelligence/media_progress_desktop.py`
- Test: `tests/test_desktop_media_progress.py`
- Modify: `ProductIntelligence.spec` solo si el asset no queda recogido por el empaquetado actual.

**Interfaces:**
- UI intenta cargar frames GIF con Pillow `ImageSequence`; si no puede, conserva `_draw_wolf` actual.

- [ ] Testear presencia de loader, frame retention y fallback.
- [ ] Crear GIF ligero (loop continuo) y cargarlo en Tkinter sin bloquear hilo principal.
- [ ] Cambiar caption según estado real (`searching`, `found`, `downloading`, `done`, `error`).
- [ ] Confirmar GREEN.

### Task 6: Verificación integral y smoke real

**Files:**
- Modify/Create: `.github/workflows/media-integration-smoke.yml` si el workflow existente no cubre este caso.

- [ ] Ejecutar `python -m pytest -q` y exigir 0 fallos.
- [ ] Ejecutar smoke con `JBLQ350WLBLKAM`, `JBLENDURRUN3BTBAM`, `JBLT530CBLKAM` y registrar conteo de imágenes/videos/rechazos.
- [ ] Verificar que no se descarguen imágenes pequeñas ni productos relacionados de confianza baja.
- [ ] Abrir PR, esperar CI y smoke, corregir cualquier regresión.
- [ ] Mergear a `main` únicamente con CI verde y luego verificar Build Windows EXE + artifact.
