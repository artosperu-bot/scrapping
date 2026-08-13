# Product Intelligence Handbook

Memoria operativa del proyecto. Antes de modificar un módulo, leer este índice y el documento específico.

## Regla principal
No arreglar A rompiendo B. Cada cambio debe preservar contratos compartidos y pasar sus gates antes de mergear a `main`.

## Documentos
- `ARCHITECTURE.md`: arquitectura y flujo general.
- `CODE_MAP.md`: mapa operativo de módulos y archivos reales.
- `EXCEL_AND_IDENTITY.md`: Excel, Part Number, identidad y SKU vendedor.
- `PRICE_INTELLIGENCE.md`: precios, canales, sellers y validación.
- `MEDIA.md`: fotos, videos y reglas anti-contaminación.
- `AUDIT_AND_UI.md`: interfaz y logs generales.
- `TESTING_AND_RELEASE.md`: CI, smokes, build Windows y EXE.
- `CURRENT_STATE.md`: estado operativo vigente.

## Flujo canónico
`Excel -> Identidad -> Fuentes -> Atributos -> Multimedia -> Precios -> Excel de salida -> Auditoría`

El Part Number/MPN es la identidad primaria cuando existe. Ningún módulo puede inventar datos.
