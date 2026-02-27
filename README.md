# GestorCompras

Aplicación de escritorio para gestión de compras, proveedores y automatización de comunicaciones operativas.

## Estado del proyecto

Proyecto en uso interno y en evolución continua. Incluye funcionalidades de operación diaria para los flujos de **Compras Bienes** y **Compras Servicios**.

## Funcionalidades principales

- Inicio de sesión SMTP corporativo y validación de credenciales.
- Menú principal con dos flujos:
  - **Compras Bienes**
  - **Compras Servicios**
- **Correos Masivos (Despacho)**:
  - envío por OC individual o agrupado por proveedor,
  - uso de plantillas HTML configurables,
  - adjuntos PDF automáticos,
  - soporte de correos en copia (CC) desde Configuración.
- **Seguimientos** con formato de correo configurable y CC independiente.
- **Reasignación de tareas** (bienes/servicios) con filtros y actualización de estado.
- **Configuración centralizada**:
  - proveedores (correo principal y alterno),
  - asignaciones por subdepartamento,
  - carpeta de PDFs,
  - credenciales de Google Sheets,
  - plantillas de correo.
- **Editor HTML de formatos de correo**:
  - edición visual,
  - firma en imagen,
  - envío de correo de prueba.
- Integración con módulo auxiliar **DescargasOC-main** para descarga y procesamiento de OCs.

## Mejoras incorporadas en la versión actual

- Interfaz unificada con estilos consistentes en Tkinter/ttk.
- Separación clara de módulos para GUI, lógica y servicios.
- Soporte para segundo correo por proveedor.
- Selección de formato por envío (no solo formato global).
- Validaciones operativas para evitar envíos incompletos.
- Configuración de CC separada por proceso:
  - `EMAIL_CC_DESPACHO`
  - `EMAIL_CC_SEGUIMIENTO`
- Compatibilidad de ejecución desde raíz con `run.py`.

## Estructura general

- `run.py`: lanzador principal desde la raíz.
- `GestorCompras_/run.py`: lanzador interno del paquete.
- `GestorCompras_/gestorcompras/main.py`: arranque de la app y ruteo UI.
- `GestorCompras_/gestorcompras/gui/`: pantallas y ventanas principales.
- `GestorCompras_/gestorcompras/logic/`: lógica de negocio.
- `GestorCompras_/gestorcompras/services/`: acceso a DB, correo y servicios auxiliares.
- `GestorCompras_/tests/`: pruebas automatizadas del paquete principal.
- `DescargasOC-main/`: módulo de descargas de órdenes de compra.

## Requisitos

- Python 3.10+
- Dependencias del proyecto:
  - `pip install -r requirements.txt`
- Dependencias de desarrollo (pruebas):
  - `pip install -r requirements-dev.txt`

## Ejecución

Desde la raíz del repositorio:

```bash
python run.py
```

Alternativa desde el subproyecto principal:

```bash
cd GestorCompras_
python run.py
```

## Configuración recomendada inicial

1. Abrir **Configuración**.
2. Registrar carpeta de PDFs para despacho.
3. Cargar proveedores y correos.
4. Definir CC por módulo (Despacho y Seguimiento).
5. Crear/editar formatos de correo.
6. Probar formato con correo de prueba.

## Pruebas

```bash
pytest
```

## Módulo complementario: Descargas OC

Para detalles de instalación y uso del módulo de descarga automatizada de OCs, revisar:

- `DescargasOC-main/README.md`

## Licencia y uso

Uso interno según lineamientos del propietario del repositorio.
