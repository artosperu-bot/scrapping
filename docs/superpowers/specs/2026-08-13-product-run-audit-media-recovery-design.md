# Product Run, auditoría unificada y recuperación multimedia

## Objetivo

Cerrar tres comportamientos como contrato del producto:

1. `SKU vendedor` se completa por defecto con el `Part Number` del producto.
2. La aplicación ofrece una auditoría maestra transversal para identidad, fuentes, atributos, precios, imágenes, videos, descargas y errores.
3. El flujo de fotos/videos recupera cobertura real respecto al comportamiento previo sin aceptar media de productos relacionados o variantes incorrectas.
4. El sistema se certifica con productos generales de categorías distintas, no solo con un caso JBL.

## 1. Identidad y SKU vendedor

El `Part Number` es el identificador operativo canónico suministrado por el usuario para cada producto cuando está disponible.

Regla por defecto de salida:

```text
SKU vendedor = Part Number
```

La regla se aplica al mapear/generar la salida Excel. No depende de que una tienda externa publique un SKU propio. Una futura regla explícita podría sobrescribir este valor, pero el comportamiento por defecto debe ser determinista.

No se debe confundir `SKU vendedor` con el SKU, publication ID o seller SKU recuperado desde Falabella, Ripley, Mercado Libre u otro canal; esos valores siguen siendo evidencia de la oferta y no sustituyen el Part Number de STECH por defecto.

## 2. Auditoría maestra

La sección `Auditoría` se convierte en la vista transversal del Product Run. Las vistas `Multimedia` y `Precios` se mantienen como espacios especializados, pero todos los motores reportan eventos a un formato común.

Cada evento debe contener como mínimo:

- timestamp;
- Part Number / identidad del producto;
- módulo: `IDENTITY`, `SOURCE`, `ATTRIBUTE`, `PRICE`, `IMAGE`, `VIDEO`, `DOWNLOAD`, `EXCEL`;
- fuente/canal;
- URL si aplica;
- estado: `STARTED`, `FOUND`, `VALIDATED`, `REJECTED`, `NO_RESULT`, `ERROR`, `DONE`;
- motivo o detalle;
- resultado resumido.

La UI permitirá filtrar al menos por producto, módulo y estado. La auditoría debe permitir distinguir claramente entre:

- fuente no encontrada;
- fuente encontrada pero identidad rechazada;
- media encontrada pero filtrada;
- descarga fallida;
- precio encontrado/rechazado;
- timeout/bloqueo externo;
- resultado válido final.

## 3. Recuperación de fotos y videos

### Estado observado

El flujo actual de `media_workflow.py` valida primero la identidad de la página y después filtra cada recurso multimedia. Para recursos no oficiales exige actualmente confianza >= 0.95 y scopes limitados a `EXACT_VARIANT`, `EXACT_PRODUCT` o `PRODUCT_FAMILY`. Esto protege contra contaminación, pero puede reducir excesivamente cobertura.

Los últimos smokes multimedia también deben considerarse evidencia de regresión/inestabilidad y no ignorarse como simple variación externa hasta comparar la misma identidad y fuentes contra un baseline anterior.

### Estrategia

No se eliminarán los guards de identidad. Se separarán tres conceptos:

1. **page identity**: la página pertenece al producto correcto;
2. **media relevance**: el recurso parece ser galería/video del producto y no banner/relacionado;
3. **download viability**: la URL final es descargable o puede conservarse como metadata/link válido.

El Part Number/MPN/EAN/UPC/GTIN será la señal primaria. Marca+modelo se usará como fallback únicamente cuando no haya identificador fuerte visible y el contexto sea suficientemente inequívoco.

### Cobertura

Se comparará el motor actual contra un commit/baseline anterior que haya producido buen resultado para el mismo producto. La corrección deberá identificar si la pérdida proviene de:

- discovery de URLs;
- límite/orden de páginas candidatas;
- browser/lazy loading;
- clasificación de rol/scope/confidence;
- promoción de thumbnails a original;
- URLs firmadas/temporales;
- downloader;
- videos embebidos/YouTube/Vimeo/CDN;
- rechazo de páginas o medios oficiales.

No se aceptará como solución simplemente bajar globalmente el threshold de 0.95. Los umbrales podrán ser contextuales (oficial vs retailer, MPN explícito, rol de galería, evidencia estructurada), siempre con pruebas anti-cross-product.

## 4. Generalidad del producto

La certificación debe cubrir varias categorías. Como mínimo:

- laptop;
- smartphone;
- audio;
- accesorio/cable;
- un quinto producto con Part Number/MPN fuerte de otra categoría si hay fixture o fuente disponible.

Para cada producto se comprobará:

```text
identidad correcta
Part Number preservado
SKU vendedor = Part Number
fuentes razonables
atributos sin contaminación
fotos/videos asociados al producto
precios asociados al producto
logs/auditoría completos
```

No es requisito que todos los productos tengan video disponible en Internet; sí es requisito que el sistema explique `NO_RESULT` correctamente y no devuelva videos de otro producto.

## 5. Gates de calidad

Antes de generar el siguiente EXE:

1. tests unitarios/regresión completos = PASS;
2. test contractual `SKU vendedor = Part Number` = PASS;
3. tests de auditoría/eventos = PASS;
4. multimedia anti-cross-product = PASS;
5. smoke multimedia live con evidencia visible = PASS;
6. price smoke live = PASS;
7. matriz multiproducto = PASS o gaps externos documentados sin falsa atribución;
8. modern desktop smoke Windows = PASS;
9. PyInstaller = PASS;
10. `ProductIntelligence.exe` existe = PASS;
11. artifact Windows generado desde el mismo SHA de `main` = PASS.

## 6. No objetivos

- No reescribir el motor de precios que ya fue integrado y certificado.
- No eliminar validaciones de identidad para aumentar artificialmente el número de resultados.
- No hardcodear comportamiento específico para JBL como solución general.
- No sustituir la UI moderna por la anterior.

## Criterio de terminado

Se considera terminado cuando el mismo commit de `main` contiene:

```text
UI moderna
+ SKU vendedor = Part Number
+ auditoría maestra
+ multimedia recuperada y protegida contra cross-product
+ Price Intelligence actual
+ pruebas multiproducto
```

y ese commit produce un nuevo `ProductIntelligence-Windows` verificado por GitHub Actions.
