# Product Intelligence V8

## Objetivo
Hacer que el programa replique la lógica de revisión humana usada en las pruebas reales: aprovechar toda la evidencia correcta, completar más campos y redactar descripciones más completas sin inventar.

## Cambios principales

- **Descripción enriquecida determinística**: combina descripción oficial + varias especificaciones verificadas cuando la descripción original es corta.
- **IA asistida opcional** (`ollama` u endpoint `openai_compatible`).
- La IA **solo ve evidencia que ya pasó los filtros del scraper**; no recibe acceso libre a Internet.
- Toda sugerencia de IA debe devolver `evidence_ids`. Si no cita evidencia, se descarta.
- Los campos controlados solo aceptan opciones exactas de la hoja `Opciones`.
- Guardia anti-alucinación numérica: un número generado por IA debe existir en las evidencias citadas o en la identidad del producto.
- La IA nunca procesa `SELLER_DATA` ni elige imágenes fuera de la lógica estricta de medios.
- Identidad `CONFLICT`/`LOW`: IA deshabilitada automáticamente.
- UI de escritorio con panel de configuración de IA.
- El modo sin IA continúa siendo completamente funcional.

## Filosofía V8

1. Scraping + identidad estricta.
2. Evidencia limpia.
3. Motor determinístico.
4. IA opcional solo para enriquecimiento/ambigüedad.
5. Validación determinística final.
6. Escribir o dejar vacío.

## Pruebas
55/55 tests pasan, incluyendo regresiones V3-V7 y nuevas pruebas de descripción enriquecida y anti-alucinación de IA.
