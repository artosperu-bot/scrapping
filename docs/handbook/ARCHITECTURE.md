# Arquitectura

## Objetivo
Sistema genérico de inteligencia de producto para partir de Excel, identificar productos, buscar evidencia web verificable, enriquecer atributos, multimedia y precios, y generar una salida trazable.

## Flujo
1. Preflight detecta productos y atributos.
2. Identidad canónica define MPN/Part Number, EAN/UPC/GTIN, marca y modelo.
3. Fuentes prioriza URLs manuales, oficiales y búsqueda web.
4. Atributos extrae solo evidencia compatible.
5. Multimedia usa la misma identidad.
6. Precios descubre y valida ofertas.
7. Excel writer guarda datos permitidos.
8. Auditoría registra decisiones, rechazos y errores.

## Fronteras
- Identidad manda sobre precios y multimedia.
- Precios no modifica identidad.
- Multimedia no modifica precios.
- UI orquesta; no replica motores.
- El EXE debe empaquetar exactamente `main`.

## Generalidad
No hardcodear lógica a un SKU usado en smoke. Probar distintas categorías cuando el cambio sea común.
