import os
import re
import pdfplumber
from db import get_config, get_suppliers
from email_sender import send_email

def buscar_archivo_mas_reciente(orden):
    """
    Busca y retorna el archivo PDF más reciente que contenga el número de orden.
    
    Args:
        orden (str): Número de orden a buscar en el nombre del archivo.
    
    Returns:
        tuple: (ruta del PDF, nombre de la carpeta) o (None, None) si no se encuentra.
    """
    base_dir = get_config("PDF_FOLDER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdfs"))
    archivos_encontrados = []
    # Recorre el directorio de PDFs en busca de archivos que contengan la orden.
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".pdf") and orden in file:
                archivos_encontrados.append(os.path.join(root, file))
    if archivos_encontrados:
        # Selecciona el archivo PDF más reciente basándose en la fecha de creación.
        pdf_path = max(archivos_encontrados, key=os.path.getctime)
        folder_name = os.path.basename(os.path.dirname(pdf_path))
        return pdf_path, folder_name
    return None, None

def extraer_info_de_pdf(pdf_path):
    """
    Extrae el RUC y la tarea del contenido del PDF.
    Corrige la decodificación utilizando 'latin1' y 'utf-8'.
    
    Args:
        pdf_path (str): Ruta del PDF.
    
    Returns:
        tuple: (ruc, tarea) extraídos o (None, None) si no se encuentran.
    """
    ruc_pattern = re.compile(r"\b(\d{13})\b")
    tarea_pattern = re.compile(r"Tarea\s+(\d+)", re.IGNORECASE)
    ruc = None
    tarea = None
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                try:
                    text = text.encode('latin1', errors='replace').decode('utf-8', errors='replace')
                except Exception:
                    pass
                if not ruc:
                    match_ruc = ruc_pattern.search(text)
                    if match_ruc:
                        ruc = match_ruc.group(1)
                if not tarea:
                    match_tarea = tarea_pattern.search(text)
                    if match_tarea:
                        tarea = match_tarea.group(1)
                if ruc and tarea:
                    break
    except Exception:
        pass
    return ruc, tarea

def process_order(email_session, orden):
    """
    Procesa una orden de compra:
      - Busca el PDF correspondiente.
      - Extrae el RUC y la tarea.
      - Selecciona la plantilla de correo adecuada.
      - Envía el correo con el PDF adjunto.
    
    Args:
        email_session (dict): Información de la sesión de correo.
        orden (str): Número de orden de compra.
    
    Returns:
        str: Mensaje con el resultado del proceso.
    """
    pdf_path, folder_name = buscar_archivo_mas_reciente(orden)
    if not pdf_path:
        return f"⚠ No se encontró archivo para la OC {orden}."
    
    ruc, tarea = extraer_info_de_pdf(pdf_path)
    suppliers = {ruc_db: email for (_id, name, ruc_db, email) in get_suppliers()}
    if not (ruc and ruc in suppliers):
        return f"⚠ No se encontró correo para el RUC {ruc} (OC: {orden})."
    
    # Prepara el contexto para el correo.
    context = {
        "orden": orden,
        "tarea": tarea,
        "folder_name": folder_name,
        "email_to": suppliers[ruc]
    }
    
    # Selecciona las plantillas según la configuración de correo.
    formato = get_config("EMAIL_TEMPLATE", "Bienes")
    if formato == "Bienes":
        template_text = "correo_bienes.txt"
        template_html = "correo_bienes.html"
    else:
        template_text = "correo_servicios.txt"
        template_html = "correo_servicios.html"
    
    # Construye el asunto del correo.
    subject = f"DESPACHO DE OC {orden}" + (f" TAREA {tarea}" if tarea else "") + f" - {folder_name}"
    subject = subject.upper()
    
    try:
        send_email(email_session, subject, template_text, template_html, context, attachment_path=pdf_path)
        return f"✅ Correo enviado a {context['email_to']} con la OC {orden}" + (f" (Tarea: {tarea})" if tarea else "")
    except Exception as e:
        return f"❌ Error al enviar el correo para OC {orden}: {str(e)}"
