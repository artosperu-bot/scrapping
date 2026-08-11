# Arquitectura obligatoria — Product Intelligence

Este documento define la arquitectura de referencia del proyecto. Toda mejora futura del scraper, del normalizador, del sistema de imágenes, del traductor o del mapper de Excel debe respetar estas reglas.

El objetivo no es construir un scraper que copie texto de una página. El objetivo es construir un **motor de inteligencia de producto** capaz de procesar cientos o miles de part numbers con trazabilidad, mínima contaminación entre variantes y salida adaptada a la plantilla Excel.

---

## 1. Principio general

La pipeline debe separar claramente estas responsabilidades:

```text
PART NUMBER / IDENTIDAD INICIAL
        ↓
IDENTIFICAR PRODUCTO EXACTO
        ↓
DESCUBRIR FUENTES
        ↓
EXTRAER CANDIDATOS CRUDOS
        ↓
VALIDAR IDENTIDAD DE CADA EVIDENCIA
        ↓
NORMALIZAR ATRIBUTO
        ↓
NORMALIZAR VALOR Y UNIDAD
        ↓
TRADUCCIÓN TÉCNICA CONTROLADA
        ↓
RESOLVER CONFLICTOS
        ↓
SCORE DE CONFIANZA
        ↓
VALIDACIÓN LÓGICA
        ↓
JSON MAESTRO + EVIDENCIA
        ↓
INTERPRETAR CONTRATO DEL EXCEL
        ↓
FORMATEAR SEGÚN LA PLANTILLA
        ↓
LLENAR EXCEL
        ↓
REPORTE Y TRAZABILIDAD
```

**No mezclar extracción, traducción y escritura de Excel en una sola etapa.**

---

## 2. Identificación del producto

Entrada mínima:

- `part_number` / MPN;
- marca cuando esté disponible;
- EAN/UPC/GTIN cuando exista;
- mercado/país cuando sea relevante.

Antes de aceptar una fuente se debe verificar que corresponde al producto correcto.

Guardar como identidad:

```json
{
  "brand": "JBL",
  "model": "Quantum 350 Wireless",
  "part_number": "JBLQ350WLBLKAM",
  "ean": "6925281986505",
  "official_url": "...",
  "country": "...",
  "source_type": "official_product_page"
}
```

### Regla anti-variante

La coincidencia de identidad debe seguir esta prioridad:

```text
MPN / EAN / UPC / GTIN exacto
>
modelo + variante exacta
>
modelo exacto
>
familia de producto
```

Una fuente de familia o categoría **no puede aportar especificaciones particulares** si no se demuestra que el dato pertenece a la variante exacta.

La presencia aislada del MPN dentro de una página de categoría no es suficiente para aceptar todos los atributos de esa página.

---

## 3. Jerarquía de fuentes

Prioridad general:

1. Página oficial exacta del fabricante.
2. Datasheet / manual / ficha técnica oficial exacta.
3. API, XHR, GraphQL o endpoint interno del fabricante.
4. Distribuidor autorizado.
5. Mayorista.
6. Retailer confiable.
7. Marketplace.
8. Otras fuentes públicas.

Dentro de una misma fuente:

```text
part number exacto
>
variante exacta
>
modelo exacto
>
familia
>
categoría
```

La fuente de mayor jerarquía no gana automáticamente si tiene conflicto interno o corresponde a otra variante.

---

## 4. Extracción en cascada

La extracción debe recopilar candidatos, no sobrescribir valores ciegamente.

Métodos, en orden aproximado de preferencia:

1. HTML / source HTML.
2. JSON-LD / Microdata / RDFa.
3. variables JavaScript embebidas.
4. endpoints internos XHR/fetch/API/GraphQL.
5. DOM renderizado.
6. PDFs oficiales / spec sheets / manuales.
7. versión imprimible / Print-to-PDF cuando aporte información pública útil.
8. OCR únicamente como último recurso cuando no existe texto estructurado utilizable.

Cada método debe producir **evidencias independientes**.

---

## 5. Evidence-first: guardar siempre el dato crudo

Nunca traducir ni normalizar antes de conservar el dato original.

Ejemplo:

```json
{
  "field_raw": "Weight (g)",
  "value_raw": "252",
  "source_type": "official_html",
  "url": "...",
  "extraction_method": "html",
  "language": "en",
  "identity_match": "EXACT",
  "confidence": 0.98
}
```

Toda especificación final debe poder responder:

> ¿De dónde salió este valor?

---

## 6. Normalización semántica de atributos

Primero se entiende qué significa el atributo. Después se decide cómo mostrarlo.

Ejemplos:

```text
Weight (g)
Peso
Product Weight
Net Weight
→ weight_g
```

```text
Driver (mm)
Driver Size
Dynamic Driver Size
→ driver_size_mm
```

```text
Battery Life
Maximum Play Time
Music Play Time
Autonomía
→ battery_life_h
```

Debe existir un diccionario/ontología por categoría, extensible y no dependiente de una sola marca.

---

## 7. Normalización de valores y unidades

Conservar siempre valor original y valor normalizado.

Ejemplos:

```text
0.252 kg → 252 g
1 in → 2.54 cm
22 hrs → 22 h
20Hz - 20kHz → 20 Hz–20 kHz
```

Representación interna sugerida:

```json
{
  "raw_value": "0.252 kg",
  "normalized_value": 252,
  "normalized_unit": "g"
}
```

No convertir unidades cuando exista ambigüedad de contexto, por ejemplo peso de producto vs peso del paquete.

---

## 8. Traducción técnica controlada

La traducción ocurre **después** de comprender el atributo y normalizar el valor.

No usar traducción literal palabra por palabra para descripciones técnicas largas.

Ejemplos de diccionario técnico de audio:

```text
driver_size → Tamaño del driver
frequency_response → Respuesta de frecuencia
sensitivity → Sensibilidad
impedance → Impedancia
battery_life → Autonomía de batería
detachable_boom_microphone → Micrófono boom desmontable
```

Para párrafos largos en inglés:

```text
texto fuente
→ extraer hechos verificables
→ normalizar atributos
→ redactar español natural usando solo hechos demostrados
```

Nunca introducir números o características nuevas durante la traducción/redacción.

---

## 9. Resolución de conflictos

No escoger al azar.

Ejemplo:

```text
HTML oficial: 22 h
PDF oficial: 22 h
Retailer: 18 h
```

Resultado:

```text
22 h
```

porque dos evidencias oficiales exactas coinciden.

Si dos fuentes oficiales exactas discrepan:

```json
{
  "status": "CONFLICT",
  "candidates": [
    {"value": "22 h", "source": "official_html"},
    {"value": "20 h", "source": "official_pdf"}
  ]
}
```

Un conflicto no debe desaparecer por tomar simplemente el primer valor encontrado.

---

## 10. Score de confianza

La confianza debe ser por **campo/evidencia**, no solo por dominio.

Factores positivos:

- part number exacto;
- EAN/UPC/GTIN exacto;
- fabricante oficial;
- variante exacta;
- valor explícito;
- unidad explícita;
- dos o más evidencias independientes coincidentes;
- PDF y página oficial coincidentes.

Factores negativos:

- valor inferido;
- familia/categoría en vez de producto exacto;
- variante no confirmada;
- OCR;
- marketplace;
- evidencia indirecta;
- conflicto entre fuentes.

Ejemplo:

```json
{
  "field": "driver_size_mm",
  "value": 40,
  "confidence": 0.99,
  "evidence_count": 2
}
```

---

## 11. Validación lógica

La validación lógica detecta anomalías; **nunca inventa un reemplazo**.

Ejemplos sospechosos para audífonos:

```text
driver_size = 400 mm
battery_life = 2200 h
weight = 25 kg
```

Resultado:

```text
status = REVIEW_REQUIRED
```

Las reglas deben ser por categoría y tolerantes a productos excepcionales.

---

## 12. JSON maestro

El JSON maestro se genera después de resolver identidad, evidencia, normalización y conflictos.

Ejemplo:

```json
{
  "identity": {
    "brand": "JBL",
    "model": "Quantum 350 Wireless",
    "part_number": "JBLQ350WLBLKAM",
    "ean": "6925281986505"
  },
  "specifications": {
    "general": {
      "weight_g": 252,
      "driver_size_mm": 40
    },
    "audio": {
      "frequency_response": "20 Hz–20 kHz",
      "sensitivity_db": 115,
      "impedance_ohm": 32
    },
    "battery": {
      "charging_time_h": 2,
      "max_playtime_h": 22
    }
  },
  "evidence": []
}
```

---

## 13. El Excel manda sobre la salida

La web aporta evidencia. **La plantilla define el formato final.**

Para cada columna se debe interpretar conjuntamente:

- encabezado;
- ID externo;
- descripción/instrucción de la plantilla;
- traducción ES/EN de la instrucción;
- `Syntax`;
- lista de opciones válidas;
- ejemplos declarados por la plantilla;
- contexto producto vs paquete.

Ejemplo:

```text
web: Wireless = Yes
Excel espera: Sí / No
→ Sí
```

```text
web: Bluetooth 5.4
Excel: “Selecciona si el producto cuenta con bluetooth. Syntax: One value from the list”
Opciones: Sí / No
→ Sí
```

La descripción de la columna es un **contrato funcional**, no texto decorativo.

### Regla para booleanos

- evidencia positiva explícita → `Sí`;
- evidencia negativa explícita → `No`;
- lista cerrada de capacidades que demuestra ausencia → puede inferirse `No` con trazabilidad;
- mera ausencia de la palabra → **no significa No**.

---

# 14. IMÁGENES — regla obligatoria y prioritaria

El motor actual debe mejorar especialmente aquí.

Una página oficial de producto suele contener varias imágenes válidas aunque el scraper encuentre solo una. La extracción de imágenes debe tratar la galería como una entidad estructurada, no como una búsqueda genérica de `<img>`.

## 14.1 Objetivo

Para un producto exacto, recuperar todas las imágenes de producto de alta calidad razonablemente disponibles, hasta el máximo que permita el Excel, sin contaminar con:

- logos;
- iconos;
- banners;
- badges;
- thumbnails de recomendaciones;
- productos relacionados;
- colores/variantes distintas;
- imágenes de categoría/familia;
- placeholders;
- imágenes de reseñas de usuarios;
- assets de navegación.

## 14.2 Fuentes de imagen a inspeccionar

En una página oficial validada se debe revisar, como mínimo:

1. JSON-LD `Product.image`.
2. JSON embebido del producto.
3. arrays de galería en JavaScript.
4. atributos `src`, `srcset`, `data-src`, `data-srcset`, `data-zoom-image`, `data-large`, `data-image`.
5. elementos `<picture>` / `<source>`.
6. carruseles/sliders de producto.
7. endpoints XHR/API que devuelvan la galería.
8. OpenGraph principal solo como respaldo.
9. imágenes asociadas a la variante seleccionada.

No detener la recolección después de encontrar la primera imagen válida.

## 14.3 Agrupación por galería

Las imágenes deben agruparse según su contexto DOM/JSON.

Una imagen tiene más confianza si pertenece al mismo:

- `Product` JSON-LD;
- array de media del SKU;
- carrusel principal;
- contenedor de galería del producto;
- endpoint de media ligado al SKU.

Una imagen aislada en footer/recomendaciones no debe entrar aunque el nombre del producto aparezca cerca.

## 14.4 Variante y color

Antes de aceptar una imagen:

- comprobar MPN/SKU cuando exista metadata;
- comprobar color/capacidad/variante cuando la página tiene selector;
- no mezclar imágenes de todos los colores solo porque comparten modelo base;
- si no se puede separar variante, marcar `REVIEW_REQUIRED` en lugar de rellenar múltiples imágenes dudosas.

## 14.5 Calidad y deduplicación

De una misma imagen disponible en múltiples tamaños:

```text
thumbnail 120x120
medium 600x600
zoom 1600x1600
```

conservar preferentemente la de mayor resolución válida.

Deduplicar mediante URL canónica y, cuando sea necesario, firma/hash perceptual o dimensiones/archivo.

Parámetros como `w`, `h`, `width`, `height`, `sw`, `sh`, `quality` no deben crear imágenes distintas del mismo asset.

## 14.6 Orden de imágenes

Orden sugerido:

1. imagen principal/heroe de la variante exacta;
2. vistas alternativas del producto;
3. lateral/trasera/detalles físicos;
4. accesorios/contenido si claramente pertenecen a la ficha;
5. imágenes de uso/lifestyle solo después de las imágenes técnicas del producto.

No usar una imagen lifestyle como `Imagen principal` si existe una foto limpia del producto.

## 14.7 Resultado esperado

Si la ficha oficial contiene 5 imágenes válidas del mismo SKU y el Excel admite 8:

```text
Imagen principal = galería[0]
Imagen2 = galería[1]
Imagen3 = galería[2]
Imagen4 = galería[3]
Imagen5 = galería[4]
```

No es aceptable quedarse con una sola imagen por detener el scraper al primer hallazgo.

Cada imagen debe conservar evidencia:

```json
{
  "url": "...",
  "role": "product_gallery",
  "source_url": "...",
  "source_type": "official_product_page",
  "extraction_method": "json_gallery",
  "variant_match": "EXACT",
  "width": 1600,
  "height": 1600,
  "confidence": 0.99
}
```

---

## 15. Estados de salida

Cada campo debe terminar en un estado explícito:

```text
COMPLETED
NOT_FOUND
CONFLICT
REVIEW_REQUIRED
REJECTED_IDENTITY
REJECTED_FORMAT
```

El Excel puede permanecer vacío cuando corresponde, pero `trazabilidad.json` debe explicar por qué.

---

## 16. Regla de desarrollo

Antes de agregar una regla específica para una marca o producto, preguntar:

> ¿Este problema puede resolverse a nivel de identidad, evidencia, semántica, unidad, galería, conflicto o contrato Excel de forma general?

La respuesta preferida debe ser una solución general.

No crear excepciones tipo:

```text
if JBLQ350...
if marca == JBL y modelo == ...
```

salvo que exista una peculiaridad documentada de una fuente que requiera un adapter reutilizable para ese proveedor.

---

## 17. Pruebas mínimas antes de considerar una mejora terminada

Una mejora no se considera completa solo porque pasan unit tests.

Debe probarse:

1. pruebas unitarias;
2. regresiones existentes;
3. scraping real de varios part numbers;
4. al menos una fuente oficial cuando exista;
5. una fuente secundaria como fallback;
6. plantilla Excel real;
7. revisión de trazabilidad;
8. revisión de galería de imágenes;
9. prueba de conflicto/variante;
10. comprobación de que no se degradaron campos antes correctos.

Para imágenes, la prueba debe comparar:

```text
cantidad visible en galería oficial
vs
cantidad de imágenes válidas extraídas
```

Si la web oficial muestra varias imágenes y solo se extrae una, la prueba debe considerarse incompleta aunque el Excel sea técnicamente válido.

---

## 18. Criterio final

El sistema debe privilegiar:

```text
exactitud > cantidad
```

pero **exactitud no significa abandonar datos disponibles**.

Si existen 4 imágenes oficiales claramente asociadas al mismo SKU, deben recuperarse las 4.

Si una descripción de Excel permite determinar claramente el formato esperado, debe utilizarse.

Si hay dos evidencias oficiales que coinciden, deben reforzarse mutuamente.

Si hay conflicto real, debe reportarse, no ocultarse.

El objetivo es maximizar el llenado **solo con información demostrable, correctamente normalizada y trazable**.
