# Diseño — Galería oficial, video, filtros y progreso multimedia

Fecha: 2026-08-12
Repo: artosperu-bot/scrapping
Rama: feat/media-official-gallery-video

## Objetivo

Mejorar el módulo **7. Fotos y videos** para que, cuando llegue a una ficha oficial de producto, extraiga de forma exhaustiva la galería real y los videos del producto; mantenga una política más estricta para medios externos; descarte imágenes pequeñas o de interfaz; y muestre un progreso visible con animación GIF ligera sin afectar el motor de Excel ni la pestaña 8 de precios.

## Reglas funcionales

1. **Página oficial validada = modo galería oficial.** Si la página pertenece al fabricante y la identidad del producto está suficientemente validada, la extracción no depende del score genérico de cada imagen. Se aceptan los medios pertenecientes al carrusel/galería principal siempre que pasen los filtros de calidad y ruido.
2. **Extracción exhaustiva de galería.** Revisar DOM, `src/srcset`, lazy/zoom attrs, JSON-LD, estado embebido, recursos de red y selectores de carrusel. Conservar el orden de la galería cuando pueda inferirse.
3. **Videos.** Detectar `VideoObject`, `<video>/<source>`, iframe YouTube/Vimeo, MP4/WebM/MOV, HLS/m3u8, botones o elementos del carrusel que revelen video y URLs descubiertas por red/estado embebido. Videos directos se descargan; YouTube/Vimeo/HLS se registran como URL + metadata.
4. **Imágenes pequeñas.** Rechazar por defecto imágenes con ancho < 300 px, alto < 300 px o área < 120000 px² cuando las dimensiones puedan verificarse. También rechazar iconos, logos, badges, sprites, trackers, UI, banners y thumbnails que tengan una alternativa de mayor resolución.
5. **Medios externos.** Para resultados descubiertos fuera de una página oficial validada, aceptar automáticamente solo `confidence >= 0.95`. Los resultados `0.84–0.94` no se descargan como resultado principal; pueden quedar registrados como rechazados/revisión en metadata/logs. `<0.84` se descarta.
6. **Color.** Sigue sin ser bloqueo duro para multimedia; modelo/MPN/generación/capacidad sí protegen identidad.
7. **No mezclar productos relacionados.** Imágenes de recomendaciones, accesorios o productos distintos se rechazan aunque estén dentro de la misma página.
8. **Metadata.** Registrar URL original, URL final, rol, origen (official_gallery / official_video / external_search), dimensiones si se conocen, confidence, match de identidad, fuente y motivo de aceptación/rechazo cuando aplique.

## Detección de página oficial

Una página se considera oficial cuando:
- el dominio coincide de forma razonable con la marca/fabricante o ya fue clasificado como oficial por discovery; y
- la identidad de página coincide por MPN/GTIN exacto o marca + modelo descriptivo sin conflicto.

No basta con que el dominio sea oficial: una página de otro producto debe ser rechazada.

## Pipeline

```text
ProductIdentity
  -> URLs manuales primero + discovery
  -> validar identidad de página
  -> clasificar oficial vs externa
  -> fetch estático + Playwright/red cuando haga falta
  -> extraer candidatos multimedia
  -> si oficial: priorizar galería/carrusel y video del PDP
  -> si externa: exigir confidence >= 0.95
  -> verificar dimensiones/tipo de archivo
  -> rechazar ruido/pequeños/relacionados
  -> deduplicar URL + hash
  -> descargar directos / registrar hosted video
  -> metadata + eventos UI
```

## UI y progreso

La zona inferior de la pestaña 7 mantiene las barras existentes y añade una animación GIF original y ligera que se reproduce mientras el worker está activo. Estados visuales: esperando, buscando, extrayendo, descargando, completado y error. El GIF no determina el porcentaje: el porcentaje sigue viniendo de eventos reales del workflow.

La animación debe ejecutarse solo en el hilo principal de Tkinter mediante `after(...)`; ninguna actualización de Tk se hace desde el worker.

## Pruebas requeridas

- página oficial con múltiples imágenes de galería: conserva todas las válidas;
- página oficial con media de producto + productos relacionados: rechaza relacionados;
- imagen 120×120: rechazada;
- imagen 1000×1000: aceptada si identidad/rol válidos;
- externo 0.94: no descarga principal;
- externo 0.95: aceptado;
- JSON-LD `VideoObject` y `<video>` directo;
- YouTube/Vimeo/HLS quedan como metadata-only;
- URL oficial con producto incorrecto: rechazada;
- regresión completa del repo;
- smoke real con JBL cuando el entorno de GitHub Actions tenga Internet;
- build Windows después del merge.

## Aislamiento

No modificar `run_batch` ni el flujo de precios. Los cambios se concentran en `media_discovery.py`, `media_workflow.py`, `media_downloader.py` y la extensión de UI multimedia/progreso, con helpers nuevos si hacen falta.

## Criterio de éxito

Para una ficha oficial como JBL Quantum 350, el módulo debe intentar recuperar toda la galería real de producto y sus videos disponibles, sin contaminarse con imágenes pequeñas o productos relacionados; para fuentes externas debe ser conservador (`>=0.95`); y el usuario debe ver una animación GIF + progreso real durante el proceso.