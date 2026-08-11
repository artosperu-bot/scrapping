# Changelog V4

- Añadido `media_discovery.py`.
- Validación individual de imágenes/videos/PDF/assets contra identidad objetivo.
- Alcances `EXACT_VARIANT`, `EXACT_PRODUCT`, `PRODUCT_FAMILY`, `UNVERIFIED`.
- Conflicto explícito de capacidad/variante => recurso no elegible.
- Descubrimiento de Vimeo, YouTube, HTML5 video, imágenes DOM/JSON-LD/OpenGraph y Network.
- Captura de recursos de red desde Playwright.
- `site_profile` aprendido por dominio durante la visita, sin hardcodear marcas.
- `evidence_graph` para trazabilidad producto ↔ fuente ↔ atributo/media.
- Excel solo usa multimedia exacta/validada.
- Regla: vacío > recurso de otra variante.
