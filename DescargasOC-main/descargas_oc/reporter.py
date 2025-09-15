import smtplib
import poplib
import json
from email.message import EmailMessage
from pathlib import Path
from html import escape

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
SMTP_PORT = 587
SMTP_SSL_PORT = 465
SMTP_PLAIN_PORT = 25

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
ORDENES_TMP = DATA_DIR / 'ordenes_tmp.json'


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
    """Tabla de texto con bordes y columnas alineadas. Usa box-drawing."""
    if not filas:
        return "─ Sin datos ─"

    headers = ("Orden", "Tarea", "Proveedor")

    # Límite de ancho por columna para que no se rompa la vista en correos
    MAXW = (16, 18, 40)  # ajusta a tu gusto

    def _clip(x: str, w: int) -> str:
        s = str(x).replace("\n", " ").strip()
        return (s[: w - 1] + "…") if len(s) > w else s

    # Aplica clipping a todas las filas
    filas_clip = [tuple(_clip(c, MAXW[i]) for i, c in enumerate(row)) for row in ([headers] + filas)]

    # Calcula anchos reales
    anchos = [max(len(r[i]) for r in filas_clip) for i in range(3)]

    # Helpers de bordes
    top    = "┌" + "┬".join("─" * (a + 2) for a in anchos) + "┐"
    mid    = "├" + "┼".join("─" * (a + 2) for a in anchos) + "┤"
    bottom = "└" + "┴".join("─" * (a + 2) for a in anchos) + "┘"

    def _fmt_row(row: tuple[str, str, str]) -> str:
        return "│ " + " │ ".join(row[i].ljust(anchos[i]) for i in range(3)) + " │"

    # Construye líneas
    lines = [top, _fmt_row(filas_clip[0]), mid]
    for row in filas_clip[1:]:
        lines.append(_fmt_row(row))
    lines.append(bottom)
    return "\n".join(lines)


def _tabla_html(filas: list[tuple[str, str, str]]) -> str:
    """Tabla HTML con bordes, padding, zebra y ajuste de ancho. Seguro con escape()."""
    if not filas:
        return "<p style='font-family:Segoe UI, Arial, sans-serif;font-size:13px;'>– Sin datos –</p>"

    # Definición de estilos inline para que Outlook/cliente no los ignore
    table_style = (
        "border-collapse:collapse;"
        "border:1px solid #d0d7de;"
        "width:100%;"
        "font-family:Segoe UI, Arial, sans-serif;"
        "font-size:13px;"
        "table-layout:fixed;"
        "word-wrap:break-word;"
        "line-height:1.35;"
    )
    th_style = (
        "text-align:left;"
        "padding:8px 10px;"
        "border:1px solid #d0d7de;"
        "background:#f6f8fa;"
        "font-weight:600;"
        "white-space:nowrap;"
    )
    td_style = (
        "padding:6px 10px;"
        "border:1px solid #d0d7de;"
        "vertical-align:top;"
        "word-break:break-word;"
    )

    # Colgroup para controlar anchos relativos/por ch (caracteres)
    colgroup = (
        "<colgroup>"
        "<col style='width:16ch'>"
        "<col style='width:20ch'>"
        "<col style='width:auto'>"
        "</colgroup>"
    )

    # Construye filas con zebra
    filas_html = []
    for i, (o, t, p) in enumerate(filas):
        bg = "#ffffff" if i % 2 == 0 else "#fafbfc"
        filas_html.append(
            f"<tr style='background:{bg};'>"
            f"<td style='{td_style}'>{escape(str(o))}</td>"
            f"<td style='{td_style}'>{escape(str(t))}</td>"
            f"<td style='{td_style}'>{escape(str(p))}</td>"
            "</tr>"
        )
    rows = "".join(filas_html)

    return (
        f"<table style='{table_style}'>"
        f"{colgroup}"
        "<thead>"
        f"<tr><th style='{th_style}'>Orden</th>"
        f"<th style='{th_style}'>Tarea</th>"
        f"<th style='{th_style}'>Proveedor</th></tr>"
        "</thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def enviar_reporte(exitosas, faltantes, ordenes, cfg: Config, categoria: str | None = None) -> bool:
    if not exitosas and not faltantes:
        return False
    if not ordenes:
        try:
            with open(ORDENES_TMP, 'r', encoding='utf-8') as f:
                ordenes = json.load(f)
        except Exception:
            ordenes = []
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

    # Algunos servidores requieren autenticarse vía POP3 antes de enviar SMTP
    try:
        pop = poplib.POP3_SSL(cfg.pop_server, cfg.pop_port)
        pop.user(usuario)
        pop.pass_(password)
        pop.quit()
    except Exception as exc:  # pragma: no cover - la ausencia de POP no debe abortar
        logger.warning("Autenticación POP fallida: %s", exc)
    mensaje = EmailMessage()
    subject = 'Reporte de órdenes descargadas'
    if categoria:
        subject += f' - {categoria}'
    mensaje['Subject'] = subject
    mensaje['From'] = usuario
    mensaje['To'] = destinatario
    texto = ''
    if categoria:
        texto += f'Categoría: {categoria}\n\n'
    texto += 'Órdenes subidas correctamente:\n'
    filas_ok: list[tuple[str, str, str]] = []
    for num in exitosas_uniq:
        data = info.get(num, {})
        prov = data.get('proveedor') or '-'
        tarea = data.get('tarea') or _buscar_tarea(num, cfg) or '-'
        filas_ok.append((num, tarea, prov))
    html = ''
    if categoria:
        html += f"<p>Categoría: {escape(categoria)}</p>"
    html += '<h3>Órdenes subidas correctamente:</h3>' + _tabla_html(filas_ok)
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
    usernames = [usuario]
    if "@" in usuario:
        base = usuario.split("@")[0]
        usernames.append(base)
        dominio = usuario.split("@")[1].split(".")[0].upper()
        usernames.append(f"{dominio}\\{base}")

    def _intentar_envio(factory):
        try:
            with factory() as smtp:
                for u in usernames:
                    try:
                        smtp.login(u, password)
                        break
                    except smtplib.SMTPAuthenticationError:
                        logger.warning("Fallo de autenticación con '%s'", u)
                else:
                    raise smtplib.SMTPAuthenticationError(535, b"Authentication failed")
                smtp.send_message(mensaje)
            logger.info('Reporte enviado')
            return True
        except Exception as e:
            logger.error('No se pudo enviar reporte: %s', e)
            return False

    def _smtp_tls():
        s = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        s.ehlo()
        s.starttls()
        s.ehlo()
        return s

    if _intentar_envio(_smtp_tls):
        try:
            ORDENES_TMP.unlink(missing_ok=True)
        except Exception:
            pass
        return True

    if _intentar_envio(lambda: smtplib.SMTP_SSL(SMTP_SERVER, SMTP_SSL_PORT)):
        try:
            ORDENES_TMP.unlink(missing_ok=True)
        except Exception:
            pass
        return True

    if _intentar_envio(lambda: smtplib.SMTP(SMTP_SERVER, SMTP_PLAIN_PORT)):
        try:
            ORDENES_TMP.unlink(missing_ok=True)
        except Exception:
            pass
        return True

    return False

