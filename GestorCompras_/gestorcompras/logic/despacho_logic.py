import os
import re
import pdfplumber
from gestorcompras.services.db import (
    get_config,
    get_suppliers,
    get_email_template_by_name,
)
from gestorcompras.services.email_sender import send_email_custom

def buscar_archivo_mas_reciente(orden):
    """
    Busca y retorna el PDF más reciente que contenga el número de orden.
    """
    base_dir = get_config("PDF_FOLDER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdfs"))
    archivos_encontrados = []
    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith(".pdf") and orden in file:
                archivos_encontrados.append(os.path.join(root, file))
    if archivos_encontrados:
        pdf_path = max(archivos_encontrados, key=os.path.getctime)
        folder_name = os.path.basename(os.path.dirname(pdf_path))
        return pdf_path, folder_name
    return None, None

def extraer_info_de_pdf(pdf_path):
    """
    Extrae el RUC y la tarea del contenido del PDF.
    Se corrige la decodificación utilizando 'latin1' y luego se decodifica a 'utf-8' con reemplazo de errores.
    """
    import re, pdfplumber
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
                # Se intenta reencodear en caso de problemas
                try:
                    # Convertimos el texto a bytes usando latin1 y luego lo decodificamos a utf-8
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

def obtener_resumen_orden(orden):
    """Obtiene la información necesaria para previsualizar el envío."""
    pdf_path, folder_name = buscar_archivo_mas_reciente(orden)
    if not pdf_path:
        return None, f"No se encontró archivo para la OC {orden}."
    ruc, tarea = extraer_info_de_pdf(pdf_path)
    suppliers = {
        ruc_db: (email, email_alt)
        for (_id, name, ruc_db, email, email_alt) in get_suppliers()
    }
    if not (ruc and ruc in suppliers):
        return None, f"No se encontró correo para el RUC {ruc} (OC: {orden})."
    emails = list(filter(None, suppliers[ruc]))
    return {
        "orden": orden,
        "tarea": tarea,
        "folder_name": folder_name,
        "emails": emails,
        "pdf_path": pdf_path,
        "ruc": ruc,
    }, None

def process_order(email_session, orden, include_pdf=True, template_name=None, cc_key="EMAIL_CC_DESPACHO", provider_name=None):
    info, error = obtener_resumen_orden(orden)
    if not info:
        return f"⚠ {error}"

    pdf_path = info["pdf_path"]
    tarea = info["tarea"]
    folder_name = info["folder_name"]
    emails = info["emails"]
    if not include_pdf:
        pdf_path = None
    email_to = ", ".join(emails) if emails else ""

    context = {
        "orden": orden,
        "tarea": tarea,
        "folder_name": folder_name,
        "email_to": email_to,
    }
    
    # Seleccionar formato de correo según la configuración
    formato = template_name or get_config("EMAIL_TEMPLATE", "FORMATO")
    template_db = get_email_template_by_name(formato)
    if not template_db or not template_db[2].strip():
        return f"⚠ Formato de correo '{formato}' no encontrado."
    _, _name, html_content, signature_path = template_db
    
    # Construimos el asunto con carpeta y tarea
    subject = f"DESPACHO DE OC {orden}" + (f" TAREA {tarea}" if tarea else "") + f" - {folder_name}"
    subject = subject.upper()  # Forzamos mayúsculas
    
    try:
        send_email_custom(
            email_session,
            subject,
            html_content,
            context,
            attachment_path=pdf_path if include_pdf else None,
            signature_path=signature_path,
            cc_key=cc_key,
        )
        return f"✅ Correo enviado a {context['email_to']} con la OC {orden}" + (f" (Tarea: {tarea})" if tarea else "")
    except Exception as e:
        return f"❌ Error al enviar el correo para OC {orden}: {str(e)}"


def process_orders_grouped(email_session, orders, include_pdf=True, template_name=None, cc_key="EMAIL_CC_DESPACHO"):
    grouped: dict[str, list[dict]] = {}
    results: list[str] = []
    for orden in orders:
        info, error = obtener_resumen_orden(orden)
        if info:
            grouped.setdefault(info["ruc"], []).append(info)
        else:
            results.append(f"⚠ {error}")
    formato = template_name or get_config("EMAIL_TEMPLATE", "FORMATO")
    template_db = get_email_template_by_name(formato)
    if not template_db or not template_db[2].strip():
        results.append(f"⚠ Formato de correo '{formato}' no encontrado.")
        return results
    _, _name, html_content, signature_path = template_db
    for infos in grouped.values():
        ordenes = [i["orden"] for i in infos]
        tareas = [i["tarea"] for i in infos if i["tarea"]]
        folder_name = infos[0]["folder_name"] if infos else ""
        emails = infos[0]["emails"] if infos else []
        pdf_paths = [i["pdf_path"] for i in infos] if include_pdf else None
        email_to = ", ".join(emails) if emails else ""
        context = {
            "orden": ", ".join(ordenes),
            "tarea": ", ".join(tareas),
            "folder_name": folder_name,
            "email_to": email_to,
        }
        subject = (
            "DESPACHO DE OC "
            + ", ".join(ordenes)
            + (f" TAREA {tareas[0]}" if tareas else "")
            + f" - {folder_name}"
        ).upper()
        try:
            send_email_custom(
                email_session,
                subject,
                html_content,
                context,
                attachment_paths=pdf_paths,
                signature_path=signature_path,
                cc_key=cc_key,
            )
            results.append(
                f"✅ Correo enviado a {email_to} con las OC {', '.join(ordenes)}"
            )
        except Exception as e:
            results.append(
                f"❌ Error al enviar el correo para OCs {', '.join(ordenes)}: {str(e)}"
            )
    return results

