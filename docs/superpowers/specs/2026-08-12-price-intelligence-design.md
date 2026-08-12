# Diseño — Inteligencia de precios y competencia

Fecha: 2026-08-12
Repo: artosperu-bot/scrapping
Rama: feat/price-intelligence

## Objetivo

Agregar una pestaña independiente **8. Precios y competencia** al escritorio actual. El usuario no tendrá que proporcionar URLs manuales: el proceso parte de la identidad ya cargada desde el Excel (Part Number/MPN como llave principal, con modelo/marca como respaldo) y descubre automáticamente ofertas públicas en marketplaces y tiendas.

El módulo debe mantener aislados el llenado del Excel y el flujo de multimedia. No se modifica la lógica existente de `run_batch` ni se usa la ejecución de multimedia como dependencia del motor de precios.

## Principios

1. **Part Number primero.** Una oferta no se acepta solo porque apareció en una búsqueda.
2. **Canal y seller son entidades distintas.** Falabella, Ripley o MercadoLibre pueden ser el canal; el seller real debe guardarse por separado cuando esté expuesto.
3. **Fuentes estructuradas primero.** API pública/JSON, JSON-LD, estado embebido, XHR/GraphQL antes que scraping visual.
4. **Fallback progresivo.** HTML y Playwright solo cuando una ruta estructurada no basta.
5. **No inventar.** Precio, seller, stock, razón social y RUC se guardan solo si hay evidencia explícita.
6. **General y extensible.** Los adaptadores por plataforma/canal se conectan a un motor común; no se hardcodea lógica de JBL.
7. **Histórico desde el inicio.** Cada observación válida se registra con timestamp para poder comparar cambios futuros.

## Flujo general

```text
ProductIdentity
   ↓
normalización y consultas exactas por MPN/modelo
   ↓
adaptadores conocidos
   ├─ MercadoLibre
   ├─ VTEX cuando se detecte realmente
   └─ adapters específicos de canal si existen
   ↓
discovery web genérico
   ↓
detección de plataforma / página
   ↓
API / JSON / JSON-LD / estado embebido
   ↓
XHR / GraphQL observados con navegador
   ↓
HTML
   ↓
Playwright
   ↓
validación de identidad
   ↓
normalización de ofertas
   ↓
deduplicación + score
   ↓
UI + histórico
```

## Modelo de oferta normalizado

Cada oferta tendrá, como mínimo:

- `part_number`
- `brand`
- `model`
- `channel`
- `seller_display_name`
- `seller_legal_name` (opcional)
- `seller_tax_id` / RUC (opcional)
- `selling_price`
- `list_price` (opcional)
- `currency`
- `stock` / disponibilidad si está expuesta
- `condition`
- `payment_method` o condición promocional si aplica
- `url`
- `source_type`
- `source_method`
- `identity_match`
- `confidence`
- `observed_at`

## Validación de identidad

Prioridad de evidencia:

1. MPN/Part Number exacto en API/JSON/atributos.
2. MPN exacto en la página.
3. GTIN/EAN/UPC exacto cuando esté disponible.
4. Marca + modelo completo compatibles.
5. Modelo familiar con confianza menor: se muestra como observación dudosa, pero no entra automáticamente en el precio competitivo principal.

El color no será un bloqueo fuerte cuando el modelo sea inequívoco, pero capacidad, generación, conectividad o variantes que cambien el producto sí deben impedir una coincidencia automática.

## Adaptadores

### MercadoLibre

- Usar el site de Perú (`MPE`) para la búsqueda pública cuando el endpoint esté disponible.
- Buscar por MPN exacto primero y modelo como fallback.
- Normalizar cada publicación válida como una oferta.
- Si el primer resultado no incluye todos los datos de seller, se permite una consulta adicional a recursos públicos relacionados con la publicación/seller.

### VTEX

- No asumir que un comercio usa VTEX solo por su marca.
- Activar el adapter únicamente cuando se detecten firmas/endpoints VTEX.
- Recorrer `items[]` y `sellers[]`; cada seller constituye una oferta independiente.
- Extraer `Price`, `ListPrice`, `AvailableQuantity` y nombre del seller cuando existan.

### Falabella / Ripley / otras tiendas

- Primero detectar la arquitectura real.
- Si hay API/estado/GraphQL/XHR consumible, usar esa ruta.
- Si no, usar HTML y Playwright como fallback.
- Guardar el marketplace como `channel` y el seller real por separado cuando aparezca.

### Retailer genérico

- Para tiendas que no tengan adapter específico, reutilizar discovery + extracción estructurada/HTML/Playwright.
- Solo aceptar precios de páginas cuya identidad haya sido validada.

## Enriquecimiento del seller

El seller se resuelve en dos fases:

1. Capturar el nombre visible/ID desde la oferta.
2. Enriquecer, si está públicamente expuesto, con razón social y RUC desde perfiles/páginas legales del mismo marketplace o seller.

Los datos legales no serán requisito para conservar una oferta de precio válida.

## Score

Referencia inicial:

- `1.00`: MPN exacto en datos estructurados/API.
- `0.95`: MPN exacto en contenido validado de página.
- `0.90`: marca + modelo completo inequívocos.
- `0.75`: coincidencia probable sin MPN.
- `< 0.70`: no se usa en la comparación principal automática.

El score final puede ajustar por calidad de fuente, conflictos de variante y seller/URL duplicados.

## Deduplicación

Clave lógica aproximada:

`channel + seller + product identity + publication/SKU/canonical URL`

También se normalizan URLs y IDs de publicación para evitar que la misma oferta encontrada por API, buscador y HTML aparezca varias veces.

## Histórico

Persistencia local simple dentro de la carpeta de salida, sin introducir base de datos obligatoria en esta fase:

```text
salida/
└── price_intelligence/
    ├── latest.json
    ├── history.jsonl
    └── sellers.json
```

`history.jsonl` agrega una observación por línea y no sobrescribe el histórico anterior. `latest.json` contiene la vista consolidada de la ejecución más reciente.

## UI — pestaña 8

Nombre: **8. Precios y competencia**.

La pantalla tendrá:

- lista de productos ya detectados del Excel;
- botón `BUSCAR PRECIOS` para el producto seleccionado;
- botón `Procesar todos los productos`;
- tabla de resultados con:
  - canal,
  - vendedor,
  - precio actual,
  - precio lista,
  - stock/disponibilidad,
  - confianza,
  - enlace;
- resumen por producto: menor precio válido, número de ofertas válidas y canales encontrados;
- progreso por producto y progreso global reutilizando el patrón de eventos del módulo multimedia, sin reutilizar su motor;
- doble clic en una oferta abre la publicación.

No habrá campo obligatorio de URLs manuales en esta primera versión, porque el objetivo es discovery automático inteligente.

## Concurrencia y estabilidad de UI

- Red y scraping corren en worker thread.
- Tkinter solo se actualiza desde el hilo principal mediante `queue.Queue` + `after(...)`.
- Un canal que falle no aborta el resto del producto.
- Timeouts y errores se registran por fuente.

## Archivos previstos

Nuevos módulos enfocados:

- `price_models.py`
- `price_identity.py`
- `price_adapters.py` o paquete `price_adapters/`
- `price_discovery.py`
- `price_normalizer.py`
- `price_history.py`
- `price_workflow.py`
- `price_desktop.py`

Se reutilizan:

- `ProductIdentity`
- `discovery.py`
- `web_fetch.py`
- Playwright ya empaquetado
- helpers de validación de identidad cuando sean compatibles

El entrypoint del escritorio apuntará a la extensión final que incluya las pestañas 7 y 8, manteniendo las clases anteriores reutilizables y evitando copiar toda la UI.

## Pruebas

Mínimo:

1. normalización de ofertas;
2. validación exacta por MPN/modelo;
3. deduplicación;
4. parsing de payload MercadoLibre con fixtures;
5. parsing de payload VTEX con múltiples sellers;
6. histórico append + latest;
7. aislamiento: módulo de precios no llama `run_batch` ni `run_media_product`;
8. estructura de pestaña 8;
9. regresión completa del repo;
10. build Windows después del merge a `main` mediante el workflow existente.

## Criterio de éxito

Para un conjunto de productos con MPN, la app debe poder descubrir automáticamente ofertas públicas, aceptar únicamente coincidencias suficientemente validadas, mostrar precio + canal + seller real cuando esté disponible, abrir la publicación, guardar el histórico y terminar el procesamiento sin afectar las pestañas 1–7 ni el llenado del Excel.
