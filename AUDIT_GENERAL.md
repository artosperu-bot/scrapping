# Auditoría general del mapper V6

La V6 se diseñó a partir de errores reales observados en plantillas de SSD y audífonos, pero las reglas son generales para cualquier categoría.

## Regla de escritura

Un valor solo se escribe cuando se cumplen simultáneamente:

1. La identidad del producto/fuente es válida.
2. El atributo extraído tiene semántica canónica conocida.
3. La columna pide el mismo concepto, no uno parecido.
4. El contexto coincide: producto, subcomponente, paquete, vendedor o logística.
5. La unidad/dimensión física es compatible.
6. Si es campo controlado, el valor existe o puede convertirse de forma segura a una opción de la propia plantilla.
7. No es placeholder, ejemplo, etiqueta ni unidad aislada.

## Casos bloqueados

- `Cable length 1.3 m` -> `Largo del producto`: rechazado.
- `21.06 g` peso neto -> `Peso del paquete`: rechazado sin evidencia de packaging.
- `10 m/s` -> `PotenciaDeAudio`: rechazado por dimensión física.
- `500 mAh` -> `Autonomía`: rechazado; capacidad de batería no es tiempo.
- `(cm)` -> `Alto`: rechazado como unidad/placeholder.
- `Ej. 80 cm x 45 cm ...` -> `Dimensiones`: rechazado como ejemplo.
- Texto desconocido -> lista controlada del marketplace: rechazado si no coincide con una opción válida.

## Casos permitidos

- `Dimensions 22 mm x 80 mm x 2.3 mm` -> `Dimensiones`.
- `Bluetooth 5.3` -> campo booleano `CuentaConBluetooth` -> `Si`, si la plantilla solo permite `Si/No`.
- `IPX5` -> `ResistenteAlAgua` -> `Si`, cuando el campo es explícitamente booleano.
- Color exacto -> opción de color idéntica de la plantilla.
- Imágenes solo `EXACT_VARIANT` / `EXACT_PRODUCT`.

## Principio

**El JSON maestro conserva información que no cabe en la plantilla. La plantilla nunca debe deformar la verdad técnica del producto.**
