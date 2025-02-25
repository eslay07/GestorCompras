# 📌 Proyecto Cotizador - Fase Preliminar

## ⚠️ Estado del Proyecto
Este proyecto se encuentra **en una fase de pruebas** y aún **no ha sido entregado oficialmente**.  
El autor **Jimmy Toapanta** está realizando ajustes y optimizaciones antes de su versión final.  

⚠ **IMPORTANTE:** No utilizar esta versión en entornos de producción hasta que se confirme su estabilidad.  

---

## 🚀 Descripción del Proyecto
El **Proyecto Cotizador** es una herramienta diseñada para la gestión automatizada de cotizaciones y publicaciones en plataformas de licitación. Su objetivo principal es **optimizar y agilizar la generación de cotizaciones** a través de dos procesos automatizados:

### 📌 **Modos de Cotización**
1️⃣ **Cotizar en Katuk (Automatización con Selenium)**
   - 📤 **Genera un archivo JSON con los datos de la cotización.**
   - 🤖 **Ejecuta un script en Python** con Selenium, el cual:
     - **Inicia sesión** en la plataforma **Katuk**.
     - **Toma los datos del JSON** y los **ingresa automáticamente en Katuk**.
     - **Crea y publica** la licitación sin intervención manual.
   
2️⃣ **Cotizar por Correo (Generación de Email a Proveedores)**
   - 📤 **Genera un archivo JSON con los datos de la cotización.**
   - 📧 **Ejecuta un script en Python**, que:
     - **Selecciona proveedores** en base a la categoría del producto.
     - **Genera un correo automático** con los datos de la cotización.
     - **Envía el correo** a los proveedores correspondientes.

---

## 🛠 Características del Módulo Cotizador
✅ **Carga de datos desde PostgreSQL al ingresar un código**  
✅ **Generación de JSON con la información estructurada**  
✅ **Autocompletado de "Producto" y "Precio" si el código existe en la BD**  
✅ **Permite ingresar productos sin código y completar manualmente**  
✅ **Validaciones antes de generar JSON (no permite campos vacíos en filas con código)**  
✅ **Automatización con Selenium para Katuk** *(desactivada temporalmente, lista para pruebas)*  
✅ **Generación automática de correos a proveedores** *(desactivada temporalmente, lista para pruebas)*  
✅ **Compatibilidad con selección múltiple y eliminación de datos con "Delete"**  
✅ **Copiar y pegar datos desde el portapapeles (Ctrl+C, Ctrl+V)**  
✅ **Siempre mantiene dos filas vacías al final para facilitar el ingreso de datos**  

---

## ⚙️ Requisitos Técnicos
- **Lenguaje:** C# (.NET Framework)  
- **Base de Datos:** PostgreSQL  
- **Automatización:** Python 3.x con Selenium  
- **Librerías utilizadas:**  
  - `Newtonsoft.Json` (manejo de JSON en C#)  
  - `Npgsql` (conexión con PostgreSQL)  
  - `Selenium` (automatización en Python)  

---

## 📂 Archivos Clave
- `CotizadorForm.cs` → Módulo principal en C#.  
- `Cotizador_katuk.py` → Script en Python para automatizar publicaciones en **Katuk**.  
- `busqueda_de_tarea.py` → Script en Python para **generar y enviar correos** a proveedores.  
- `datos_automatizacion_temp.json` → Archivo JSON con los datos de cada cotización.  

---

## 📌 Funcionamiento del Módulo
1️⃣ **El usuario llena la tabla con los productos a cotizar.**  
2️⃣ **Valida que todos los campos obligatorios estén llenos.**  
3️⃣ **Genera un JSON con los datos de la cotización.**  
4️⃣ **Ejecuta un script Python según el botón seleccionado:**  
   - **Cotizar Katuk:** Automatización con Selenium para publicar en Katuk.  
   - **Cotizar Correo:** Genera y envía un correo a proveedores.  

🚨 **Actualmente, la ejecución de los scripts Python está desactivada por pruebas.**  

---

## 🛠 Instalación y Configuración
### 🔹 **1. Clonar el repositorio**
```bash
git clone https://github.com/usuario/proyecto-cotizador.git
🔹 2. Configurar la conexión a PostgreSQL
Editar DatabaseHelper.cs con los datos de conexión.

🔹 3. Instalar dependencias en Python
Si vas a probar la automatización con Selenium:

bash
Copiar
Editar
pip install selenium
🔹 4. Ejecutar la aplicación
Abrir en Visual Studio y ejecutar CotizadorForm.cs.

⚠️ Nota Final
Este es un proyecto preliminar en fase de pruebas. No se recomienda su uso en producción hasta su versión final.
Última actualización: [25/02/2025]
