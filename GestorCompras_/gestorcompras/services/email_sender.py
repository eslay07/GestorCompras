import os
import smtplib
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
    msg["Cc"] = "compras_locales_uio@telconet.ec, bodega_uio@telconet.ec"
    #msg["Cc"] = "jotoapanta@telconet.ec"
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
