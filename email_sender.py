import os
import smtplib
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader

# Configuración del directorio de plantillas para los correos.
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

# Configuración del servidor SMTP.
SMTP_SERVER = "smtp.telconet.ec"
SMTP_PORT = 587

def render_email(template_name, context):
    """
    Renderiza una plantilla de correo con el contexto dado.
    
    Args:
        template_name (str): Nombre de la plantilla.
        context (dict): Datos para rellenar la plantilla.
    
    Returns:
        str: Contenido renderizado.
    """
    template = env.get_template(template_name)
    return template.render(context)

def send_email(email_session, subject, template_text, template_html, context, attachment_path=None):
    """
    Envía un correo electrónico utilizando SMTP.
    
    Args:
        email_session (dict): Diccionario con "address" y "password".
        subject (str): Asunto del correo.
        template_text (str): Nombre del archivo de la plantilla para texto plano.
        template_html (str): Nombre del archivo de la plantilla para HTML.
        context (dict): Datos para renderizar las plantillas.
        attachment_path (str, opcional): Ruta del archivo PDF a adjuntar.
    
    Raises:
        Exception: Si ocurre un error al adjuntar el PDF o enviar el correo.
    """
    msg = EmailMessage()
    msg["Subject"] = subject.upper()
    msg["From"] = email_session["address"]
    msg["To"] = context.get("email_to", "")
    msg["Cc"] = "jotoapanta@telconet.ec"

    # Renderiza el contenido del correo.
    content_text = render_email(template_text, context)
    content_html = render_email(template_html, context)
    msg.set_content(content_text)
    msg.add_alternative(content_html, subtype="html")

    # Adjunta el archivo PDF si se especifica.
    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype="application", subtype="pdf",
                               filename=os.path.basename(attachment_path))
        except Exception as e:
            raise Exception(f"Error al adjuntar PDF: {str(e)}")

    # Envía el correo mediante el servidor SMTP.
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(email_session["address"], email_session["password"])
            server.send_message(msg)
    except Exception as e:
        raise Exception(f"Error al enviar correo: {str(e)}")
