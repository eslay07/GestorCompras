import os
import smtplib
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader

# ============================================================
# MÓDULO PARA EL ENVÍO DE CORREOS ELECTRÓNICOS
# Propósito: Renderizar plantillas y enviar correos usando SMTP.
# ============================================================

# Configuración de la ruta de plantillas para renderizar correos
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

# Configuración del servidor SMTP
SMTP_SERVER = "smtp.telconet.ec"
SMTP_PORT = 587

def render_email(template_name, context):
    """
    Renderiza la plantilla indicada utilizando el contexto proporcionado.
    """
    template = env.get_template(template_name)
    return template.render(context)

def send_email(email_session, subject, template_text, template_html, context, attachment_path=None):
    """
    Envía un correo electrónico utilizando SMTP.
    
    Parámetros:
        email_session: Diccionario con "address" y "password".
        subject: Asunto del correo.
        template_text: Archivo de plantilla para el texto plano.
        template_html: Archivo de plantilla para el contenido HTML.
        context: Diccionario de datos para renderizar las plantillas.
        attachment_path: Ruta del archivo PDF a adjuntar (opcional).
    
    Proceso:
        - Renderiza el contenido a partir de las plantillas.
        - Adjunta un archivo PDF si se especifica.
        - Envía el correo a través del servidor SMTP.
    """
    msg = EmailMessage()
    msg["Subject"] = subject.upper()  # Asunto en mayúsculas para uniformidad
    msg["From"] = email_session["address"]
    msg["To"] = context.get("email_to", "")
    # Se define el CC (puedes modificar según sea necesario)
    msg["Cc"] = "jotoapanta@telconet.ec"
    
    # Renderización del contenido de correo en texto y HTML
    content_text = render_email(template_text, context)
    content_html = render_email(template_html, context)
    msg.set_content(content_text)
    msg.add_alternative(content_html, subtype="html")

    # Adjunta un archivo PDF si se proporciona la ruta
    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype="application", subtype="pdf",
                               filename=os.path.basename(attachment_path))
        except Exception as e:
            raise Exception(f"Error al adjuntar PDF: {str(e)}")

    try:
        # Envío del correo utilizando el servidor SMTP configurado
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Aseguramos la conexión
            server.login(email_session["address"], email_session["password"])
            server.send_message(msg)
    except Exception as e:
        raise Exception(f"Error al enviar correo: {str(e)}")
