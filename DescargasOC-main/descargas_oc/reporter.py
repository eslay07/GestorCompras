import smtplib
from email.message import EmailMessage
from pathlib import Path

try:  # allow running as script
    from .config import Config
    from .logger import get_logger
    from .organizador_bienes import extraer_numero_tarea_desde_pdf
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger
    from organizador_bienes import extraer_numero_tarea_desde_pdf

logger = get_logger(__name__)

SMTP_SERVER = "smtp.telconet.ec"
SMTP_PORT = 465


def _buscar_tarea(numero: str, cfg: Config) -> str | None:
    """Busca el número de tarea dentro del PDF de la OC."""
    carpeta = getattr(cfg, "carpeta_analizar", None)
    if not carpeta:
        return None
    # Buscar recursivamente por si los archivos fueron movidos a subcarpetas
    for pdf in Path(carpeta).rglob(f"{numero}*.pdf"):
        tarea = extraer_numero_tarea_desde_pdf(str(pdf))
        if tarea:
            return tarea
    return None


def _formatear_tabla(filas: list[tuple[str, str, str]]) -> str:
    """Genera una tabla simple alineada por columnas."""
    headers = ("Orden", "Tarea", "Proveedor")
    filas_completas = [headers] + filas
    anchos = [max(len(str(f[i])) for f in filas_completas) for i in range(3)]
    linea_sep = " | ".join("-" * a for a in anchos)
    lines = [
        " | ".join(str(f[i]).ljust(anchos[i]) for i in range(3)) for f in filas_completas
    ]
    return "\n".join([lines[0], linea_sep] + lines[1:])


def _tabla_html(filas: list[tuple[str, str, str]]) -> str:
    """Genera una tabla HTML sencilla."""
    if not filas:
        return "<p>-</p>"
    filas_html = "".join(
        f"<tr><td>{o}</td><td>{t}</td><td>{p}</td></tr>" for o, t, p in filas
    )
    return (
        "<table style='border-collapse:collapse'>"
        "<tr><th>Orden</th><th>Tarea</th><th>Proveedor</th></tr>"
        f"{filas_html}</table>"
    )


def enviar_reporte(exitosas, faltantes, ordenes, cfg: Config) -> bool:
    if not exitosas and not faltantes:
        return False
    # asegurarse de no repetir números
    exitosas_uniq = list(dict.fromkeys(exitosas))
    faltantes_uniq = list(dict.fromkeys(faltantes))
    info = {o["numero"]: o for o in ordenes}

    destinatario = cfg.correo_reporte
    usuario = cfg.usuario
    password = cfg.password
    if not destinatario or not usuario or not password:
        logger.warning('Datos de correo incompletos, no se enviará reporte')
        return False
    mensaje = EmailMessage()
    mensaje['Subject'] = 'Reporte de órdenes descargadas'
    mensaje['From'] = usuario
    mensaje['To'] = destinatario
    texto = 'Órdenes subidas correctamente:\n'
    filas_ok: list[tuple[str, str, str]] = []
    for num in exitosas_uniq:
        data = info.get(num, {})
        prov = data.get('proveedor') or '-'
        tarea = data.get('tarea') or _buscar_tarea(num, cfg) or '-'
        filas_ok.append((num, tarea, prov))
    html = '<h3>Órdenes subidas correctamente:</h3>' + _tabla_html(filas_ok)
    if filas_ok:
        texto += _formatear_tabla(filas_ok) + '\n'
    if faltantes_uniq:
        texto += '\nNo se encontraron archivos para las siguientes OC:\n'
        filas_bad: list[tuple[str, str, str]] = []
        for num in faltantes_uniq:
            data = info.get(num, {})
            prov = data.get('proveedor') or '-'
            tarea = data.get('tarea') or '-'
            filas_bad.append((num, tarea, prov))
        texto += _formatear_tabla(filas_bad) + '\n'
        html += '<h3>No se encontraron archivos para las siguientes OC:</h3>' + _tabla_html(filas_bad)
    mensaje.set_content(texto)
    mensaje.add_alternative(html, subtype='html')
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as smtp:
            try:
                smtp.login(usuario, password)
            except smtplib.SMTPAuthenticationError:
                smtp.login(usuario.split('@')[0], password)
            smtp.send_message(mensaje)
        logger.info('Reporte enviado')
        return True
    except Exception as e:
        logger.error('No se pudo enviar reporte: %s', e)
        return False

