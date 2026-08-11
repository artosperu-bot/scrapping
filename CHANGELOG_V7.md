# V7 — Corrección de causa raíz

## Cambios principales

- `Evidence Quality Gate`: elimina navegación, banners, newsletter, labels vacíos/control chars y evidencia de baja calidad.
- `Strict Semantic Gate`: una palabra parecida ya no basta para crear un atributo canónico.
- TBW exige TBW real; `Endurance Run 3` ya no puede convertirse en endurance/TBW.
- Peso exige unidad de masa.
- Dimensiones del producto requieren vector dimensional; dimensiones de almohadilla/cable se bloquean por contexto.
- Potencia exige W/mW; `m/s`, dBm, voltaje/corriente no entran como potencia de audio.
- Contenido de paquete exige evidencia explícita/listable, no frases de marketing.
- Garantía vaga como “de fábrica” ya no se considera detalle suficiente de garantía.
- Resolver de atributos busca en **toda la evidencia limpia**, no solo en `specifications`.
- Contratos del Excel usan la instrucción `One/Multiple values from the list` como autoridad para campos controlados.
- Conectividad deriva tecnologías solo desde contexto de conexión/producto; `inalámbrico` ya no dispara `alámbrico`.
- Variantes por color/capacidad más estrictas.
- Fuente oficial con MPN/EAN/UPC/GTIN objetivo exige `EXACT`; `HIGH` solo cuando no existe ID fuerte de entrada.
- En fabricante, `Product.sku` puede confrontarse contra MPN objetivo para detectar variante regional/color diferente.
- PDFs y XHR/fetch se validan individualmente antes de aportar evidencia.
- Media clasificada como galería/video/page asset; iconos/logos/footer no autocompletan imágenes.
- Deduplicación de la misma imagen servida en diferentes tamaños.
- Campos seller protegidos; ejemplos declarados por la plantilla se limpian.
- GUI Tkinter + ejecución por lotes + auto-discovery + trazabilidad.
- Build Windows PyInstaller + Chromium incluido en la carpeta de distribución.

## Regresión JBL

- Quantum 350: recupera 22 h, gaming, inalámbrico, batería recargable, micrófono y galería oficial.
- Endurance Run 3: recupera 25 h, Bluetooth, in-ear, batería recargable, características compatibles, contenido de paquete y galería oficial.
- Tune 530C: el JSON antiguo presenta MPN objetivo `JBLT530CBLKAM` frente a SKU estructurado `JBLT530CBEGAM`; V7 lo marca como conflicto en migración y no utiliza esa fuente como variante exacta.
