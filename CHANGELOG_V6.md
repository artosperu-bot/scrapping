# V6 — Semantic Guard / General Product Mapping

V6 corrige la causa general observada al probar SSD y audífonos: una extracción técnicamente relacionada no puede escribirse en una columna solo por similitud semántica.

## Cambios principales

- Nuevo `semantic_guard.py` con **contrato por campo**: semántica, contexto, tipo y dimensión física esperada.
- Distingue estrictamente **producto vs paquete** (`weight` != `package_weight`, `length` != `package_length`).
- Rechaza subcomponentes incompatibles: `cable length` no puede convertirse en `product length`; medida de almohadilla no puede convertirse en alto/largo del producto.
- Rechaza incompatibilidad dimensional: `m/s` no puede ser potencia; `mAh` no puede ser autonomía; `g` no puede ser longitud.
- Rechaza unidades solas, ejemplos y placeholders como `(cm)`, `Ej. ...`, `........`.
- El fuzzy mapping ya no concatena la descripción larga de la plantilla. Las descripciones se usan para **validar intención**, no para forzar alias.
- Nuevos atributos canónicos generales: bluetooth, autonomía, potencia, tipo de auricular, resistencia al agua, alimentación, salida, características y medidas/peso de paquete.
- El reporte de trazabilidad ahora contiene dos bloques: `written` y `rejected`, con motivo de rechazo (`UNIT_DIMENSION_MISMATCH`, `PACKAGE_CONTEXT_NOT_PROVEN`, etc.).
- Las imágenes siguen limitadas a `EXACT_VARIANT` / `EXACT_PRODUCT`, sin inventar recursos de familia u otra variante.

## Principio V6

> Encontrar un valor no implica que exista una celda válida para él. Primero se identifica el atributo real; después se valida que la columna pida exactamente ese concepto.

Si no hay equivalencia demostrable, la celda queda vacía y el valor permanece en el JSON maestro.
