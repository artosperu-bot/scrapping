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
8. No publicar si existe una regresión crítica atribuible al cambio.

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

## Versiones y regresiones conocidas

Cuando un usuario reporte "en la versión anterior funcionaba y en la nueva no", la comparación entre tags/commits forma parte obligatoria del diagnóstico. Si el componente no cambió entre versiones, no atribuir el fallo a ese componente sin nueva evidencia: revisar empaquetado, estado persistido, entorno, dependencias y coordinación entre componentes.

## Principio de entrega

**Evidence before claims.** No decir "listo", "corregido", "GREEN" o "puedes actualizar" sin evidencia fresca del gate correspondiente.
