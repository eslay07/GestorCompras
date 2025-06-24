GestorCompras - Versión Preliminar
 
 Descripción del Proyecto
 -------------------------
 GestorCompras es una herramienta de gestión automatizada de compras diseñada para facilitar la administración de proveedores, la asignación de tareas y el envío de solicitudes de despacho mediante una interfaz gráfica desarrollada en Python con Tkinter. Este software ha sido desarrollado de forma autónoma e independiente por Jimmy Toapanta, como iniciativa personal, y NO constituye un encargo realizado para ninguna empresa.
 
 Estado del Proyecto
 -------------------
 ADVERTENCIA:
 Este proyecto se encuentra en fase de pruebas y desarrollo. La versión actual es preliminar y NO se recomienda su uso en entornos de producción hasta que se confirme su estabilidad y se complete la versión final.
 
 Características Principales
 ----------------------------
 - Gestión de Proveedores: Registro, edición y eliminación de proveedores.
 - Configuración de Asignaciones: Asignación única de personas a departamentos.
 - Gestión de Tareas Temporales: Carga, procesamiento y eliminación de tareas notificadas por correo.
- Automatización de Despachos: Envío automatizado de solicitudes de despacho mediante correo electrónico, con plantillas configurables.
- Formatos de Correo Personalizados: desde la configuración es posible crear, editar y eliminar plantillas en HTML, incluyendo una imagen de firma.
 - Interfaz Gráfica Profesional: Desarrollada en Tkinter, ofreciendo una experiencia intuitiva y ordenada.
 - Integración con Base de Datos SQLite: Manejo local de datos a través de una base de datos autogenerada.
 
 Instalación y Configuración
 ---------------------------
 Requisitos:
   - Python 3.x
   - Librerías de Python (entre otras): tkinter, sqlite3, pdfplumber, smtplib, jinja2, selenium, webdriver_manager
   - Conexión a Internet para autenticación SMTP y servicios externos.
 
 Pasos de Instalación:
   1. Clonar el repositorio:
        git clone https://github.com/eslay07/GestorCompras.git
   2. Instalar las dependencias:
        pip install -r requirements.txt
      (Asegúrese de tener instaladas todas las librerías necesarias según su entorno de desarrollo.)
   3. Configuración de la Base de Datos:
      La base de datos SQLite se inicializa automáticamente al ejecutar la aplicación. Los datos se almacenan en el directorio "data".
   4. Carga rápida de Proveedores:
      Se incluye el script "import_proveedores.py" que permite agregar de forma rápida proveedores a la base de datos a partir de un archivo Excel (correos.xlsx). Para ejecutarlo, desde el directorio del proyecto, ejecute:
        python import_proveedores.py
   5. Ejecutar la Aplicación:
        python main.py
 
 Uso
 ---
 Al iniciar la aplicación se presenta una pantalla de inicio de sesión. Una vez autenticado, el usuario accede a un menú principal que permite:
   - Administrar proveedores.
   - Configurar asignaciones de departamentos.
   - Cargar y gestionar tareas temporales notificadas por correo.
   - Enviar solicitudes de despacho a través de correos electrónicos predefinidos.
 
 Aclaraciones y Disclaimer Legal
 ---------------------------------
 Propiedad Intelectual:
   Todo el código, documentación y recursos incluidos en este repositorio son propiedad exclusiva de Jimmy Toapanta.
 
 Proyecto Autónomo:
   Este proyecto ha sido desarrollado por iniciativa propia y NO representa ni ha sido solicitado por ninguna empresa. Su desarrollo se realiza de forma completamente independiente.
 
 Estado Preliminar:
   La versión actual es preliminar y se encuentra en fase de pruebas. Se recomienda que cualquier usuario realice pruebas y validaciones antes de utilizar el software en un entorno real o productivo.
 
 Deslinde de Responsabilidad:
   El autor no asume responsabilidad alguna por el uso de este software. Cualquier riesgo o daño derivado de su implementación será responsabilidad exclusiva del usuario final. Este proyecto se ofrece "tal cual", sin garantías de ningún tipo, expresas o implícitas.
 
 Futuras Mejoras
 ---------------
- Se está diseñando un nuevo módulo para solicitar cotizaciones de manera automática, tanto mediante correo electrónico como a través de la plataforma Katuk, con el objetivo de optimizar aún más el proceso.
- Se continuarán mejorando las plantillas de correo para facilitar su edición y personalización.
 
 Contribuciones y Mejoras
 ------------------------
 Las contribuciones son bienvenidas siempre que se mantenga el enfoque del proyecto y se respeten los derechos de autor. Para sugerencias, mejoras o reportar errores, por favor utilice los canales de contacto indicados a continuación.
 
 Contacto
 --------
 - Correo Electrónico: omar777j@gmail.com
 - Teléfonos:
     - Personal: 0967629643
 
 Última actualización: 24/06/2025
 
 Este README ha sido actualizado para reflejar la versión actual del proyecto, garantizando claridad en sus funcionalidades, estado de desarrollo y un completo deslinde de responsabilidad legal.