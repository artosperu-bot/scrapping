# Diseño: Correctness + Document Discovery + Redacción Validada

Fecha: 2026-08-14
Base: `release/windows` @ `a80e98b3902124bee824d01d054100f8a88be419`
Rama: `feat/evidence-correctness-doc-discovery`

## Objetivo

Mejorar la calidad de los resultados del motor de Product Intelligence sin degradar funcionalidades existentes. La prioridad es corregir resolución semántica y coherencia de datos antes de ampliar cobertura. `Scraping Excel`, `Multimedia` y `Price Intelligence` permanecen separados en la interfaz, pero comparten progresivamente identidad, evidencia y canonical cuando sea útil.

## Principios no negociables

- No rehacer el sistema ni crear un pipeline paralelo.
- No modificar scraping general salvo que una prueba demuestre una causa raíz allí.
- No romper OCR.space, Mistral, PDF evidence, Multimedia, Price Intelligence, Configuración ni auto-updater.
- `UNKNOWN` nunca se convierte implícitamente en `Sí` o `No`.
- Una celda vacía es preferible a una clasificación no defendible.
- El canonical final es la única verdad autorizada para escribir atributos en Excel.
- Mistral redacta; no decide hechos técnicos.
- Los módulos de interfaz siguen separados.
- Toda mejora debe quedar cubierta por regresiones antes de extender alcance.

## Arquitectura objetivo

### 1. Identity Layer

Reutilizar la identidad existente del producto: marca, nombre comercial, modelo, MPN/SKU, GTIN/EAN/UPC cuando existan. La identidad controla búsquedas y evita mezclar variantes o productos similares.

### 2. Evidence Pool compartido

Todas las evidencias relevantes se normalizan en una representación común antes de resolver atributos. Cada evidencia conserva al menos:

- producto/identidad asociada
- atributo o hecho candidato
- valor bruto
- valor normalizado cuando aplique
- URL/fuente
- tipo de fuente
- autoridad/confianza
- contexto de evidencia
- fecha de captura cuando aplique

No se escribe directamente en Excel desde una evidencia secundaria.

### 3. Canonical Resolver

Fortalecer `canonical_facts.py`, `resolution_engine.py`, `source_authority.py` y piezas relacionadas para resolver conflictos y mantener estado explícito: `SUPPORTED`, `NOT_SUPPORTED`, `UNKNOWN` o equivalente ya existente.

Reglas obligatorias de Fase 1:

- ausencia de evidencia != evidencia negativa
- Bluetooth operando en 2.4 GHz != RF propietario
- cable USB de carga != audio cableado
- una evidencia secundaria no puede sobreescribir un canonical más fuerte
- GTIN, marca, modelo y MPN válidos ya presentes en canonical deben reutilizarse antes de declarar `INSUFFICIENT_EVIDENCE`
- conflictos como IPX5 vs IP65 se resuelven por identidad + autoridad + especificidad de fuente, nunca por último valor visto
- normalizar unidades antes de escribir o redactar
- deduplicar atributos equivalentes
- traducir etiquetas técnicas a español para salidas comerciales sin alterar el dato canonical
- mapping de opciones marketplace solo cuando exista equivalencia defendible; si no existe, dejar vacío

### 4. Official Document Discovery

Añadir una etapa dirigida a documentación técnica, no una búsqueda web indiscriminada.

Para cada producto con identidad suficiente, generar consultas derivadas de identidad, por ejemplo:

- `"<marca> <modelo>" manual pdf`
- `"<marca> <modelo>" datasheet pdf`
- `"<marca> <modelo>" specifications pdf`
- `"<marca> <modelo>" user manual`
- `"<marca> <modelo>" filetype:pdf`

Las consultas pueden adaptarse usando MPN/SKU cuando mejoren precisión.

Prioridad de documentos:

1. fabricante / soporte oficial
2. datasheet o manual oficial
3. documentación técnica oficial regional
4. distribuidor autorizado
5. fuente técnica confiable

Antes de procesar un documento, validar que corresponde al mismo producto/modelo. Un PDF de variante distinta, región incompatible o modelo parecido no puede alimentar el canonical como evidencia autorizada.

Cuando existan varios documentos oficiales válidos (por ejemplo manual + datasheet + quick start), procesar varios porque pueden ser complementarios. La autoridad se conserva por documento y atributo.

El contenido extraído entra al Evidence Pool; no escribe Excel directamente.

### 5. Redacción Mistral

`description_narrator.py` o capa equivalente recibe únicamente hechos ya resueltos y normalizados. Debe:

- conservar valores y unidades
- evitar atributos duplicados
- traducir etiquetas técnicas al español cuando corresponda
- producir redacción natural/comercial sin inventar claims
- omitir hechos `UNKNOWN`
- no alterar números ni unidades canonical

Si Mistral falla o agrega información no autorizada, la salida debe fallar cerrada o usar una redacción determinística segura.

## Módulos de interfaz

Se mantiene la opción A aprobada:

- Scraping Excel permanece independiente.
- Multimedia permanece independiente.
- Price Intelligence permanece independiente.

Compartirán por debajo identidad/evidencia/canonical donde corresponda, pero no se fuerza a que una corrida de Excel descargue también todos los precios, imágenes y videos.

## Fases

### Fase 1A — Correctness semántico

Corregir los defectos ya observados y establecer contratos generales de resolución.

Casos de regresión iniciales:

- JBL Quantum 350: UNKNOWN→Sí en Bluetooth, RF/cableado, marca Harman→JBL solo con evidencia defendible.
- JBL Endurance Run 3: Bluetooth 2.4 GHz no implica RF propietario; coherencia IP; autonomía no puede escribirse si el resolver la declara insuficiente.
- JBL Tune 530C: UNKNOWN→No en Bluetooth; reutilización GTIN/marca/modelo; USB-C cableado correcto debe mantenerse.

### Fase 1B — Document Discovery

Añadir descubrimiento y validación de manuales/datasheets/PDFs para elevar autoridad de la evidencia técnica.

### Fase 1C — Redacción validada

Mejorar descripciones con Mistral solo después de canonicalizar y normalizar.

### Fase 2 — Coverage ampliado

Solo después de cerrar Fase 1: ampliar fuentes, precios, imágenes, videos y documentación adicional. Esta fase queda fuera del primer PR salvo utilidades estrictamente necesarias para Fase 1.

## Métricas

Separar calidad y cobertura:

- Correctness: porcentaje de valores escritos que respetan canonical y evidencia.
- Coverage: porcentaje de campos con evidencia suficiente para resolverse.

Criterio de éxito de Fase 1:

- 0 conversiones UNKNOWN→Sí/No sin evidencia explícita
- 0 RF propietario inferido únicamente desde Bluetooth 2.4 GHz
- 0 audio cableado inferido únicamente desde cable de carga
- 0 valores Excel que contradigan canonical final
- GTIN/marca/modelo canonical reutilizados cuando sean válidos
- unidades conservadas en salidas
- descripciones sin duplicación ni invención demostrable
- casos JBL existentes pasan sin degradar sus aciertos actuales
- suite general existente permanece verde

## Estrategia de pruebas

TDD por defecto:

1. añadir una regresión mínima que reproduzca un defecto real
2. verificar RED por la causa esperada
3. aplicar el cambio mínimo en la capa correcta
4. verificar GREEN del test nuevo
5. ejecutar regresión del módulo afectado
6. ejecutar suite completa antes de integrar

No se agregan reglas específicas por SKU salvo fixtures de prueba. La lógica implementada debe ser general.

## Riesgos y mitigaciones

- Riesgo: subir coverage a costa de falsos positivos. Mitigación: canonical autorizado + UNKNOWN explícito.
- Riesgo: mezclar variantes con PDFs parecidos. Mitigación: validación de identidad antes de usar documento.
- Riesgo: Mistral reescriba hechos. Mitigación: input canonical-only y validación de salida.
- Riesgo: romper Multimedia/Price Intelligence. Mitigación: no cambiar sus flujos funcionales en Fase 1 salvo interfaces compartidas con pruebas de regresión.
- Riesgo: reglas para audífonos no generalicen. Mitigación: tests adicionales con al menos una categoría distinta antes de cerrar Fase 1.

## Fuera de alcance de este primer ciclo

- rediseño de interfaz
- unificar visualmente módulos
- ejecutar precios/multimedia automáticamente desde Scraping Excel
- ampliar masivamente crawlers o buscadores
- cambiar OCR.space o Mistral de proveedor/modelo
- reescribir arquitectura de scraping
- tocar `main`

## Entrega esperada

Un PR contra `release/windows`, nunca contra `main`, con cambios incrementales, tests de regresión, documentación de los nuevos contratos de resolución y evidencia de que la suite completa permanece verde.