import os
import smtplib
import base64
import re
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader

# Configuración de la ruta donde se ubicarán las plantillas
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

SMTP_SERVER = "smtp.telconet.ec"
SMTP_PORT = 587

def render_email(template_name, context):
    """
    Renderiza la plantilla con el contexto dado.
    """
    template = env.get_template(template_name)
    return template.render(context)

def send_email(email_session, subject, template_text, template_html, context, attachment_path=None):
    """
    Envía un correo utilizando SMTP.
    
    email_session: diccionario con "address" y "password".
    subject: asunto del correo.
    template_text: nombre del archivo de plantilla para texto plano.
    template_html: nombre del archivo de plantilla para HTML.
    context: diccionario de datos para renderizar las plantillas.
    attachment_path: ruta del archivo PDF a adjuntar (opcional).
    """
    msg = EmailMessage()
    msg["Subject"] = subject.upper()
    msg["From"] = email_session["address"]
    msg["To"] = context.get("email_to", "")
    msg["Cc"] = "jotoapanta@telconet.ec"
    # Renderizamos el contenido
    content_text = render_email(template_text, context)
    content_html = render_email(template_html, context)
    msg.set_content(content_text)
    msg.add_alternative(content_html, subtype="html")

    # Adjuntar PDF si se indica
    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype="application", subtype="pdf",
                               filename=os.path.basename(attachment_path))
        except Exception as e:
            raise Exception(f"Error al adjuntar PDF: {str(e)}")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(email_session["address"], email_session["password"])
            server.send_message(msg)
    except Exception as e:
        raise Exception(f"Error al enviar correo: {str(e)}")

def render_email_string(template_str, context):
    """Renderiza una plantilla proporcionada como cadena."""
    template = env.from_string(template_str)
    return template.render(context)

def image_to_data_uri(path):
    """Convierte una imagen en ruta local a un data URI base64."""
    if not path or not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(path)[1].lower().strip(".") or "png"
    return f"data:image/{ext};base64,{data}"

def send_email_custom(email_session, subject, html_template, context, attachment_path=None, signature_path=None):
    """Envía un correo usando una plantilla HTML personalizada."""
    if signature_path:
        context = dict(context)
        context["signature_image"] = image_to_data_uri(signature_path)

    content_html = render_email_string(html_template, context)
    content_text = re.sub(r"<[^>]+>", "", content_html)

    msg = EmailMessage()
    msg["Subject"] = subject.upper()
    msg["From"] = email_session["address"]
    msg["To"] = context.get("email_to", "")
    msg["Cc"] = "jotoapanta@telconet.ec"

    msg.set_content(content_text)
    msg.add_alternative(content_html, subtype="html")

    if attachment_path:
        try:
            with open(attachment_path, "rb") as f:
                pdf_data = f.read()
            msg.add_attachment(
                pdf_data,
                maintype="application",
                subtype="pdf",
                filename=os.path.basename(attachment_path),
            )
        except Exception as e:
            raise Exception(f"Error al adjuntar PDF: {str(e)}")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(email_session["address"], email_session["password"])
            server.send_message(msg)
    except Exception as e:
        raise Exception(f"Error al enviar correo: {str(e)}")
