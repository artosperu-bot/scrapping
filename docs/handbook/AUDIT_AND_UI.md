# Auditoría e interfaz

## UI
La aplicación final usa la shell moderna con navegación por:
Inicio, Productos, Fuentes, Atributos, Multimedia, Precios, Ejecutar y Auditoría.

## Auditoría general
Debe reunir eventos de:
- ejecución;
- identidad;
- fuentes;
- atributos;
- multimedia;
- precios;
- rechazos;
- errores;
- resultado final.

## Evento recomendado
Campos:
`timestamp, part_number, module, source, url, status, detail, result`

Estados principales:
`FOUND, REJECTED, ERROR, DONE`

Las vistas Multimedia y Precios siguen siendo especializadas. Auditoría es la vista transversal.
