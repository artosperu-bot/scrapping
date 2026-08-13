# Price Intelligence Final Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consolidar en `main` la mejor lógica de precios disponible, preservando la UI moderna y generando un nuevo `.exe` Windows verificado.

**Architecture:** Partir del `main` moderno y portar únicamente el conjunto final de archivos de Price Intelligence del PR #10. Mantener scraping/Excel/media/UI desacoplados; validar identidad antes de aceptar precios y usar discovery multifuente para retailers y marketplaces de Perú.

**Tech Stack:** Python 3.12, requests/BeautifulSoup, Playwright, Tkinter, PyInstaller, pytest, GitHub Actions.

## Global Constraints

- No perder ni revertir `modern_desktop` ni el entrypoint moderno.
- No inventar precios ni aceptar una oferta con conflicto de identidad.
- Priorizar MPN/EAN/UPC/GTIN; alias marca+modelo solo como discovery cuando el sitio no publica identificador fuerte.
- Mantener cobertura de retailers grandes, marketplaces y tiendas especializadas de Perú.
- Un 403 o sitio inaccesible debe quedar como fuente no recuperada, no como precio inferido.
- El cierre exige CI, Price Smoke, Windows modern shell smoke, PyInstaller, verificación de EXE y artifact.

---

### Task 1: Portar Price Intelligence estable
- [ ] Copiar desde `price-intelligence-multilayer` los archivos de producción y tests de precios que difieren de `main`.
- [ ] Preservar archivos UI modernos de `main` sin modificaciones regresivas.
- [ ] Confirmar que el diff final no toca motores ajenos salvo `discovery.py` por concurrencia de proveedores.

### Task 2: Verificar cobertura y seguridad de identidad
- [ ] Confirmar registry de canales Perú, Shopify/VTEX/API/JSON-LD/HTML/browser fallbacks y dedupe por seller/PDP.
- [ ] Confirmar rechazo de outliers y de conflictos MPN/modelo.
- [ ] Confirmar que fallos externos (403/bloqueos) no generan precios artificiales.

### Task 3: Gates automáticos y live
- [ ] Ejecutar CI completo y exigir PASS.
- [ ] Ejecutar Price Intelligence Smoke y exigir PASS.
- [ ] Confirmar que Modern Desktop Windows smoke sigue PASS.

### Task 4: Integración y EXE definitivo
- [ ] Fusionar la rama validada a `main`.
- [ ] Ejecutar Build Windows EXE sobre el SHA mergeado.
- [ ] Exigir `ProductIntelligence.exe` verificado y artifact `ProductIntelligence-Windows` nuevo.
