# Process Isolation and Audit UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ordenar Product Intelligence para que Scraping Excel, Multimedia y Precios sean funciones independientes, seguras entre sí y visibles en una Auditoría común, manteniendo soporte para productos generales.

**Architecture:** Conservar Tkinter y los motores actuales. Cada ejecución crea un snapshot inmutable antes de iniciar su thread. Un sink de eventos estructurados recibe eventos de EXCEL, MEDIA y PRICE y alimenta la nueva vista Auditoría.

**Tech Stack:** Python, Tkinter/ttk, threading, queue, pytest, Playwright/Chromium, PyInstaller, GitHub Actions.

## Global Constraints
- Productos generales; cero lógica runtime dependiente de marcas/modelos de prueba.
- EXCEL, MEDIA y PRICE independientes.
- Un worker no lee Tk variables ni colecciones UI mutables después de arrancar.
- Cambiar de vista no cancela ni reconfigura jobs activos.
- Un fallo solo restaura el módulo que falló.
- Preservar contratos Excel-first, identidad, SKU vendedor, media, precios, UI moderna y salidas.
- Release Windows solo con regression, modern desktop smoke, Chromium, PyInstaller, exe y artifact en PASS.

---

### Task 1: Execution snapshots
**Files:** Create `src/product_intelligence/execution_context.py`; test `tests/test_execution_context.py`.
**Produces:** `ExecutionSnapshot`, `ProductSnapshot`, `new_run_id(process_type)`.
- [ ] Escribir tests que demuestren que mutar listas/dicts originales no cambia el snapshot y que los IDs identifican EXCEL/MEDIA/PRICE.
- [ ] Ejecutar `pytest tests/test_execution_context.py -v` y comprobar FAIL.
- [ ] Implementar dataclasses frozen/tuples y generador de run_id.
- [ ] Reejecutar y exigir PASS.
- [ ] Commit: `feat: add immutable execution snapshots`.

### Task 2: Structured audit events
**Files:** Create `src/product_intelligence/audit_events.py`; test `tests/test_audit_events.py`.
**Produces:** `AuditEvent`, `AuditSink.emit`, `AuditSink.events`, `filter_events`.
- [ ] Tests para filtros por proceso, ERROR, REJECTED, run_id y producto.
- [ ] Ejecutar y comprobar FAIL.
- [ ] Implementar modelo inmutable y sink thread-safe.
- [ ] Ejecutar y exigir PASS.
- [ ] Commit: `feat: add structured audit event sink`.

### Task 3: Isolate Excel
**Files:** Modify `src/product_intelligence/desktop.py`; test `tests/test_process_isolation.py`.
- [ ] Test: crear job Excel, cambiar después workbook/output/overwrite/productos/URLs y demostrar que el worker conserva los valores iniciales.
- [ ] Ejecutar test y comprobar FAIL.
- [ ] Refactorizar `run()` para capturar workbook, output, overwrite, identities y URLs antes de crear el thread.
- [ ] Emitir STARTED/PROGRESS/ERROR/DONE con `run_id`, manteniendo el raw log actual.
- [ ] Ejecutar regresiones Excel + aislamiento y exigir PASS.
- [ ] Commit: `fix: isolate Excel scraping execution state`.

### Task 4: Isolate Media and Price
**Files:** Modify `media_desktop.py`, `price_desktop.py`; extend `tests/test_process_isolation.py`.
- [ ] Tests para EXCEL+MEDIA, EXCEL+PRICE y MEDIA+PRICE simultáneos sin contaminación de inputs/status.
- [ ] Ejecutar y comprobar FAIL.
- [ ] MEDIA crea snapshot propio de identidad/output/URLs/opciones y adjunta run_id a eventos.
- [ ] PRICE crea snapshot propio de identidad/output/opciones y adjunta run_id a eventos.
- [ ] Un error de un módulo solo restablece sus botones/estado.
- [ ] Ejecutar media/price/isolation tests y exigir PASS.
- [ ] Commit: `fix: isolate media and price job state`.

### Task 5: Order the modern UI
**Files:** Modify `src/product_intelligence/modern_desktop.py`; add/update modern desktop test.
- [ ] Test esperado: navegación principal = Inicio, Scraping Excel, Multimedia, Precios, Auditoría.
- [ ] Ejecutar y comprobar FAIL.
- [ ] Agrupar Productos, Identidad, Fuentes, Atributos y Ejecutar dentro del área Scraping Excel reutilizando widgets/callbacks existentes.
- [ ] Mantener Multimedia y Precios como áreas independientes.
- [ ] Ejecutar modern desktop tests y exigir PASS.
- [ ] Commit: `feat: organize desktop by independent functions`.

### Task 6: Real Audit view
**Files:** Modify `modern_desktop.py`; extend audit/UI tests.
- [ ] Test de columnas: Hora, Ejecución, Proceso, Producto, Etapa, Fuente, Estado, Detalle.
- [ ] Test de filtros: Todos, Scraping Excel, Multimedia, Precios, Errores, Rechazados.
- [ ] Ejecutar y comprobar FAIL.
- [ ] Implementar Treeview estructurado, filtros, búsqueda por run/producto y panel de detalle URL/raw.
- [ ] Mantener raw log como diagnóstico secundario, no como única auditoría.
- [ ] Probar eventos intercalados de tres run_ids y exigir separación correcta.
- [ ] Commit: `feat: add ordered cross-process audit view`.

### Task 7: Generic-product regression
**Files:** Tests.
- [ ] Añadir casos con identidad MPN, GTIN/EAN y fallback modelo/nombre.
- [ ] Confirmar que ningún branch runtime depende de JBL, HyperX, Ulefone u otro fixture.
- [ ] Ejecutar `python -m pytest -q` y exigir PASS completo.
- [ ] Ejecutar modern desktop smoke y exigir PASS.
- [ ] Revisar diff para confirmar que motores de extracción/media/precios no fueron reescritos innecesariamente.
- [ ] Commit: `test: certify generic isolated desktop workflows`.

### Task 8: Windows release gate
- [ ] Ejecutar CI/Build Windows sobre el SHA exacto de implementación.
- [ ] regression = PASS.
- [ ] modern desktop smoke = PASS.
- [ ] Chromium = PASS.
- [ ] PyInstaller = PASS.
- [ ] Verify executable exists = PASS.
- [ ] artifact upload = PASS.
- [ ] Registrar run ID, artifact ID y SHA.
- [ ] Solo con todos los gates PASS, preparar merge y actualizar `docs/handbook/CURRENT_STATE.md`.
