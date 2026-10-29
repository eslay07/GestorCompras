# Documentos actuales para conocer GestorCompras

Actualizados el **29 de octubre de 2026** a partir del código y de la documentación de la edición pública actual. Sustituyen las presentaciones históricas del portafolio.

| Documento | Contenido | Uso recomendado |
| --- | --- | --- |
| [Presentación profesional (PDF, 3 páginas)](GestorCompras_Presentacion_Actual.pdf) | Problema, aporte del autor, módulos, tiempos de referencia, escenario mensual y arquitectura. | Primera lectura para reclutadores y responsables de operaciones. |
| [Guía visual actual (PDF, 9 páginas)](GestorCompras_Guia_Visual_Actual.pdf) | Capturas, recorrido de los seis módulos, configuración, instalación y enlaces. | Revisar el funcionamiento y preparar una demostración. |

Los PDF contienen enlaces clicables. Las capturas muestran la interfaz real con datos de demostración; no contienen el catálogo operativo de proveedores ni acreditan transacciones ejecutadas al producir las imágenes. Bienes es el flujo actual y Servicios permanece en desarrollo.

Los tiempos por módulo son referencias aproximadas reportadas por el autor. El ahorro mensual de 11-15 horas es un escenario calculado con supuestos y no una medición de horas netas de personal. [Consultar cálculo y supuestos](../IMPACTO_OPERATIVO.md).

## Documentación ampliada

- [Código y presentación del proyecto](../../README.md).
- [25 capturas y explicación de módulos](../MODULOS.md).
- [Instalación y arquitectura](../GUIA_TECNICA.md).
- [Instalador completo](https://github.com/eslay07/GestorCompras/releases/tag/v2.0.0).

## Regenerar los documentos

Con Python y `reportlab` y `Pillow` instalados, ejecute `python tools/docs/generar_portafolio_pdf.py` desde la raíz del repositorio. El generador usa fuentes Segoe UI de Windows o DejaVu Sans de Linux y las capturas públicas de `docs/capturas/`. Después de regenerar, renderice y revise todas las páginas antes de publicar.

**Autor:** [Jimmy Toapanta](https://www.linkedin.com/in/jimmy-toapanta-950a441b8/).
