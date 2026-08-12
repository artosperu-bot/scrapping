# Contrato Excel — regla de entrada del motor

El sistema **no empieza scrapeando Internet**. Primero analiza la plantilla Excel completa y decide exactamente qué necesita.

## Orden obligatorio

```text
EXCEL
  ↓
encabezados + IDs + descripciones + requerido/opcional + listas permitidas
  ↓
clasificar cada columna
  ↓
crear template_contract.json
  ↓
recién entonces buscar el producto
  ↓
obtener solo evidencia útil
  ↓
resolver campo por campo
  ↓
llenar Excel
```

La descripción situada sobre cada encabezado forma parte del contrato. Puede ser más importante que el nombre corto de la columna cuando explica su intención o formato.

## Roles de columna

### IDENTITY
Datos técnicos que ayudan a identificar/validar el producto: MPN, EAN, UPC, GTIN, marca, modelo, nombre exacto.

### SCRAPE_TARGET
Datos de producto que pueden demostrarse desde fabricante, datasheet, API, HTML, PDF u otra fuente validada: conectividad, Bluetooth, dimensiones, autonomía, color, resistencia, contenido, garantía del fabricante, etc.

### MEDIA_TARGET
Slots de imágenes/videos. El número de columnas de imagen define cuántos assets útiles debe intentar recuperar el motor.

### DERIVED_OUTPUT
Datos generables únicamente a partir de identidad/evidencia ya validada, por ejemplo nombres logísticos o traducciones controladas. No son una excusa para inventar características.

### SELLER_INPUT
Información propia del vendedor: SKU vendedor, precio, precio oferta, cantidad, fechas de oferta, garantía vendedor, SKU padre y equivalentes. **Nunca se busca ni se inventa por scraping.**

### MARKETPLACE_INPUT
Información definida por la operación/catálogo del marketplace y no por la ficha técnica, por ejemplo categoría de publicación o condición comercial cuando corresponda.

### REVIEW_REQUIRED
Campo cuya intención no pudo determinarse con suficiente seguridad. Se mantiene separado hasta clasificarlo; no se rellena por aproximación.

## Ejemplo Bluetooth

Columna:

```text
CuentaConBluetooth #1568
Selecciona si el producto cuenta con bluetooth.
Syntax: One value from the list
```

Contrato:

```text
semantic = bluetooth
role = SCRAPE_TARGET
value_type = controlled
output = una opción exacta de la lista del Excel
```

Si la fuente dice `Bluetooth 5.4` y la lista del Excel es `Sí / No`, la salida es `Sí`.

La mera ausencia de la palabra Bluetooth no autoriza a escribir `No`; debe existir evidencia negativa o una especificación cerrada que demuestre la ausencia.

## Ejemplo precio

```text
PriceFalabella #52
```

Contrato:

```text
role = SELLER_INPUT
scrape = false
```

El motor preserva el dato que coloque el usuario y nunca intenta encontrar un precio público para sustituirlo.

## Imágenes

Si existen:

```text
Imagen principal
Imagen2
...
Imagen8
```

el contrato registra `media_slots = 8`.

Eso significa que, una vez validada la ficha exacta, la capa Media Intelligence debe intentar obtener hasta 8 imágenes válidas del mismo producto/variante. No debe detenerse en la primera imagen si la galería oficial contiene más.

## Regla de implementación

El scraper recibe el contrato ya resuelto. Por tanto, no debe decidir por sí mismo qué campos interesa obtener.

```text
plantilla → necesidades
fuente web → evidencia
resolver → celda
```

No:

```text
scrapear todo → guardar ruido → intentar adivinar qué servía
```

## Salidas de diagnóstico

Cada ejecución debe generar como mínimo:

- `template_contract.json`: qué pide la plantilla;
- `json/<producto>.json`: evidencia y producto normalizado;
- `trazabilidad.json`: por qué se llenó/rechazó cada celda;
- `resumen.json`: estado global de la ejecución;
- Excel completado.

Este documento y `ARCHITECTURE_PRODUCT_INTELLIGENCE.md` son normas de diseño del proyecto.
