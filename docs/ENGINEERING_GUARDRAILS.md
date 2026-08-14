# ProductIntelligence — Engineering & Regression Guardrails

Este documento es un contrato permanente del proyecto. Aplica a cualquier cambio, corrección, mejora visual, optimización, nueva fuente, nueva versión o release.

## Regla principal

**NO arreglar A rompiendo B.**

Un cambio no se considera terminado porque su función nueva funciona. Se considera terminado únicamente cuando la función objetivo funciona y las capacidades existentes relevantes continúan funcionando.

## Preservación de comportamiento

- Preservar por defecto todo comportamiento ya validado y útil.
- No reemplazar, rediseñar ni simplificar lógica funcional que no sea necesaria para resolver la causa raíz demostrada.
- Un cambio visual no puede alterar scraping, precios, multimedia, OCR, Mistral, PDF evidence, canonical, Excel, updater ni threading/event flow salvo evidencia directa de que una corrección funcional es necesaria.
- Un cambio de un motor no puede modificar otro motor por conveniencia.
- Ante duda, preferir compatibilidad hacia atrás y cambios incrementales.

## Causa raíz antes de fix

- No aplicar parches por síntomas.
- Reproducir el fallo y localizar el componente exacto antes de modificar código.
- Comparar contra la última versión estable conocida cuando exista una regresión entre versiones.
- Distinguir fallos de código de variaciones externas de sitios web, APIs, OneDrive, antivirus, red o proveedores.

## Contrato de estados terminales de UI

Todo proceso de escritorio debe terminar visualmente en exactamente uno de estos estados:

- COMPLETED: el worker terminó correctamente y la UI muestra finalización real.
- ERROR: el worker o el procesamiento de eventos falló y la UI muestra el error.
- RUNNING: únicamente mientras exista trabajo activo.

Nunca se permite que un worker ya terminado deje la UI permanentemente en "En curso", una barra indeterminada o un porcentaje obsoleto. El drenaje de eventos debe seguir programándose aun si un evento individual genera una excepción; el error debe quedar observable y no matar silenciosamente la actualización de UI.

## Contrato de release

Antes de publicar una versión:

1. Definir baseline de la versión estable anterior.
2. Revisar el diff real para conocer qué componentes cambiaron y cuáles no.
3. Ejecutar tests del cambio objetivo.
4. Ejecutar regresión completa.
5. Ejecutar smokes de las capacidades adyacentes relevantes.
6. Verificar estados terminales de UI: inicio, progreso, completado y error.
7. Verificar build Windows y updater cuando corresponda.
8. Comparar contra el baseline histórico mínimo v0.10.4 y confirmar que ninguna capacidad previamente validada desapareció salvo cambio explícitamente aprobado.
9. No publicar si existe una regresión crítica atribuible al cambio.

Un smoke externo puede fallar por una fuente web cambiante. En ese caso debe investigarse y clasificarse; no se debe modificar lógica no relacionada solo para convertir el check en verde.

## Correctness sobre apariencia de éxito

- No inventar porcentajes, resultados ni estados.
- No convertir UNKNOWN en un dato afirmativo o negativo sin evidencia.
- No declarar una release sana solo porque compila.
- No declarar un fix cerrado solo porque el test nuevo pasa; la regresión existente también debe permanecer verde.

## Cambios visuales

Los cambios visuales deben preservar callbacks, nombres públicos utilizados por handlers, workers, colas, eventos y motores. Se puede reorganizar layout, tamaño, jerarquía, espaciado y presentación sin cambiar el significado funcional.

## Cambios funcionales

Todo cambio funcional requiere como mínimo:

- evidencia de causa raíz;
- test que reproduzca el fallo cuando sea automatizable;
- fix mínimo/general, no específico a un solo producto salvo que el dominio lo requiera;
- regresión de casos conocidos;
- comprobación de que no degrada otras categorías o workflows.

## Baseline histórico de versiones

### v0.10.4 — baseline funcional mínimo

Capacidades a preservar:
- Scraping Excel y completado seguro.
- OCR.space.
- Mistral.
- PDF evidence.
- Multimedia.
- Price Intelligence.
- Configuración y persistencia de API keys.
- separación entre workflows.
- resultados visibles en UI al terminar.

### v0.10.5 — progreso visual compartido

Añadió `processing.gif`, `completed.gif`, `ProgressAnimation` y estados RUNNING / COMPLETED / ERROR.

Debe preservar v0.10.4 y además:
- GIF visible durante procesamiento.
- GIF/estado de completado.
- integración visual sin porcentajes falsos.

### v0.10.6 — updater standalone estable

Añadió updater standalone desde `%TEMP%` con runtime PyInstaller y verificación de bundle.

Debe preservar lo anterior y además:
- actualización desde GitHub Releases.
- SHA256.
- bundle Windows con app + updater.

### v0.10.7 — correctness + documentos técnicos

Añadió:
- UNKNOWN no auto → Sí/No.
- Bluetooth 2.4 GHz no auto → RF propietario.
- USB carga no implica audio cableado.
- mejor canonical GTIN/marca/modelo.
- conflictos por autoridad/confianza.
- búsqueda de manuales/datasheets/PDFs.
- ingestión PDF por Evidence Pool.
- Mistral desde canonical validado.

Nota: `price_desktop.py` y `price_workflow.py` no cambiaron entre v0.10.6 y v0.10.7.

### v0.10.8 — UI organizada + terminal-state hardening

Hereda todo lo anterior y añade:
- reorganización visual de Price Intelligence, Multimedia y Scraping Excel.
- área fija suficiente para el GIF compartido.
- resultados como área principal.
- Price Intelligence no puede quedar permanentemente en RUNNING si el worker terminó.
- errores de procesamiento de eventos quedan visibles y el event pump continúa programándose.
- `batch_done` fuerza estado terminal coherente COMPLETED o ERROR.
- contrato histórico de regresión documentado en este archivo.

Clasificación conocida de smoke externo de Precios durante esta release:
- se obtuvieron 3 ofertas peruanas válidas para JBL Quantum 350 (Memory Kings, PlazaVea y Sodimac).
- MercadoLibre respondió HTTP 403.
- un gate antiguo exigía `>3` ofertas y por eso podía marcar FAIL aun sin regresión del motor.
- ese resultado se clasifica como variación/cobertura externa, no como degradación introducida por la reorganización visual.

## Regla para futuras versiones

Antes de versionar `vX.Y.Z`, actualizar esta sección con:
1. baseline inmediato;
2. qué se agregó/corrigió;
3. qué capacidades heredadas deben seguir funcionando;
4. qué motores cambiaron realmente;
5. qué regresiones históricas se probaron;
6. resultado de tests/smokes/build/updater;
7. fallos externos conocidos.

Una nueva versión debe ser acumulativa: **hereda capacidades validadas y agrega mejoras; no puede perder silenciosamente una capacidad previa.**

## Principio de entrega

**Evidence before claims.** No decir "listo", "corregido", "GREEN" o "puedes actualizar" sin evidencia fresca del gate correspondiente.
