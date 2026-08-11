# Referencias técnicas usadas para V3

Estas referencias se usaron para elegir componentes y patrones de arquitectura. No son fuentes de datos de productos.

- Playwright — Network (captura de requests, responses, XHR y fetch): https://playwright.dev/python/docs/network
- Playwright — Response API (lectura de respuestas JSON): https://playwright.dev/python/docs/api/class-response
- Extruct — extracción de JSON-LD, Microdata y OpenGraph: https://github.com/scrapinghub/extruct
- Scrapy — framework de crawling/extracción estructurada para escalado futuro: https://github.com/scrapy/scrapy
- Beautiful Soup — parsing HTML/XML: https://beautiful-soup-4.readthedocs.io/en/latest/

## Decisión sobre bloqueos HTTP

La implementación usa `requests` como fast path y un Chromium normal mediante Playwright cuando la página pública depende de JavaScript/cookies. No contiene CAPTCHA solvers, plugins stealth ni rutinas destinadas a evadir controles de acceso. Si el navegador continúa recibiendo denegación, esa fuente se descarta y el pipeline puede probar otra fuente válida.
