# CHANGELOG V9

- GUI: cuadro para pegar múltiples part numbers.
- Modo manual: asigna part numbers a filas consecutivas del Excel aunque la plantilla esté vacía.
- Modo automático anterior se conserva si no se ingresan part numbers.
- Corregido import faltante de `AIConfig` en la GUI.
- Discovery con dos backends: DuckDuckGo HTML + Bing HTML; resultados siempre pasan validación de identidad.
- CLI: `batch -p PARTNUMBER` repetible.
- Build Windows: usa Python 3.12/3.11 explícitamente.
- `.gitignore` listo para GitHub, excluyendo secretos, Excel locales, outputs, builds y navegador Playwright.
