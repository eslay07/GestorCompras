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
    for pdf in Path(carpeta).rglob(f"{numero}*.[Pp][Dd][Ff]"):
        tarea = extraer_numero_tarea_desde_pdf(str(pdf))
        if tarea:
            return tarea
    return None


def _formatear_tabla(
    filas: list[tuple[str, ...]],
    headers: tuple[str, ...] | None = None,
) -> str:
    """Tabla de texto con bordes y columnas alineadas. Usa box-drawing."""

    if not filas:
        return "─ Sin datos ─"

    headers = headers or ("Orden", "Tarea", "Proveedor")
    num_cols = len(headers)

    # Límite de ancho por columna para que no se rompa la vista en correos
    default_max = [16, 18, 40]
    maxw = [default_max[i] if i < len(default_max) else 30 for i in range(num_cols)]

    def _clip(x: str, w: int) -> str:
        s = str(x).replace("\n", " ").strip()
        return (s[: w - 1] + "…") if len(s) > w else s

    filas_clip = [
        tuple(_clip(row[i], maxw[i]) for i in range(num_cols))
        for row in ([headers] + filas)
    ]

    anchos = [max(len(r[i]) for r in filas_clip) for i in range(num_cols)]

    top = "┌" + "┬".join("─" * (a + 2) for a in anchos) + "┐"
    mid = "├" + "┼".join("─" * (a + 2) for a in anchos) + "┤"
    bottom = "└" + "┴".join("─" * (a + 2) for a in anchos) + "┘"

    def _fmt_row(row: tuple[str, ...]) -> str:
        return "│ " + " │ ".join(row[i].ljust(anchos[i]) for i in range(num_cols)) + " │"

    lines = [top, _fmt_row(filas_clip[0]), mid]
    for row in filas_clip[1:]:
        lines.append(_fmt_row(row))
    lines.append(bottom)
    return "\n".join(lines)


def _tabla_html(
    filas: list[tuple[str, ...]],
    headers: tuple[str, ...] | None = None,
) -> str:
    """Tabla HTML con bordes, padding, zebra y ajuste de ancho. Seguro con escape()."""

    if not filas:
        return "<p style='font-family:Segoe UI, Arial, sans-serif;font-size:13px;'>– Sin datos –</p>"

    headers = headers or ("Orden", "Tarea", "Proveedor")
    num_cols = len(headers)

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

    default_widths = ["16ch", "20ch", "auto"]
    colgroup = "<colgroup>" + "".join(
        f"<col style='width:{default_widths[i] if i < len(default_widths) else 'auto'}'>"
        for i in range(num_cols)
    ) + "</colgroup>"

    header_html = "".join(
        f"<th style='{th_style}'>{escape(str(h))}</th>" for h in headers
    )

    filas_html = []
    for i, row in enumerate(filas):
        bg = "#ffffff" if i % 2 == 0 else "#fafbfc"
        celdas = "".join(
            f"<td style='{td_style}'>{escape(str(row[j]))}</td>" for j in range(num_cols)
        )
        filas_html.append(f"<tr style='background:{bg};'>{celdas}</tr>")
    rows = "".join(filas_html)

    return (
        f"<table style='{table_style}'>"
        f"{colgroup}"
        "<thead>"
        f"<tr>{header_html}</tr>"
        "</thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def enviar_reporte(
    exitosas,
    faltantes,
    ordenes,
    cfg: Config,
    categoria: str | None = None,
    destinatario: str | None = None,
) -> bool:
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

    destinatario = destinatario or cfg.correo_reporte
    usuario_pop = getattr(cfg, "usuario", None)
    password_pop = getattr(cfg, "password", None)
    smtp_usuario = getattr(cfg, "smtp_usuario", None) or usuario_pop
    smtp_password = getattr(cfg, "smtp_password", None) or password_pop
    smtp_server = getattr(cfg, "smtp_server", None) or SMTP_SERVER
    smtp_port = getattr(cfg, "smtp_port", None) or SMTP_PORT
    smtp_ssl_port = getattr(cfg, "smtp_ssl_port", None) or SMTP_SSL_PORT
    smtp_plain_port = getattr(cfg, "smtp_plain_port", None) or SMTP_PLAIN_PORT

    def _as_int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    smtp_port = _as_int(smtp_port, SMTP_PORT)
    smtp_ssl_port = _as_int(smtp_ssl_port, SMTP_SSL_PORT)
    smtp_plain_port = _as_int(smtp_plain_port, SMTP_PLAIN_PORT)

    if not destinatario or not smtp_usuario or not smtp_password:
        logger.warning('Datos de correo SMTP incompletos, no se enviará reporte')
        return False

    # Algunos servidores requieren autenticarse vía POP3 antes de enviar SMTP
    if usuario_pop and password_pop:
        try:
            pop = poplib.POP3_SSL(cfg.pop_server, cfg.pop_port)
            pop.user(usuario_pop)
            pop.pass_(password_pop)
            pop.quit()
        except Exception as exc:  # pragma: no cover - la ausencia de POP no debe abortar
            logger.warning("Autenticación POP fallida: %s", exc)
    else:  # pragma: no cover - se deja registro para diagnósticos
        logger.warning('Credenciales POP incompletas, se omite autenticación previa')
    mensaje = EmailMessage()
    subject = 'Reporte de órdenes descargadas'
    if categoria:
        subject += f' - {categoria}'
    mensaje['Subject'] = subject
    if smtp_usuario and "@" in smtp_usuario:
        remitente = smtp_usuario
    elif usuario_pop:
        remitente = usuario_pop
    else:
        remitente = smtp_usuario
    mensaje['From'] = remitente
    mensaje['To'] = destinatario
    texto = ''
    if categoria:
        texto += f'Categoría: {categoria}\n\n'
    texto += 'Órdenes subidas correctamente:\n'

    usar_tabla_categoria = bool(categoria and categoria.lower() == 'abastecimiento')
    tabla_headers = (
        ("Orden", "Proveedor", "Categoría")
        if usar_tabla_categoria
        else ("Orden", "Tarea", "Proveedor")
    )

    filas_ok: list[tuple[str, ...]] = []
    for num in exitosas_uniq:
        data = info.get(num, {})
        prov = data.get('proveedor') or '-'
        if usar_tabla_categoria:
            cat_valor = data.get('categoria') or categoria or '-'
            filas_ok.append((num, prov, cat_valor))
        else:
            tarea = data.get('tarea') or _buscar_tarea(num, cfg) or '-'
            filas_ok.append((num, tarea, prov))

    html = ''
    if categoria:
        html += f"<p>Categoría: {escape(categoria)}</p>"
    html += '<h3>Órdenes subidas correctamente:</h3>' + _tabla_html(filas_ok, tabla_headers)
    if filas_ok:
        texto += _formatear_tabla(filas_ok, tabla_headers) + '\n'
    if faltantes_uniq:
        texto += '\nNo se encontraron archivos para las siguientes OC:\n'
        filas_bad: list[tuple[str, ...]] = []
        for num in faltantes_uniq:
            data = info.get(num, {})
            prov = data.get('proveedor') or '-'
            if usar_tabla_categoria:
                cat_valor = data.get('categoria') or categoria or '-'
                filas_bad.append((num, prov, cat_valor))
            else:
                tarea = data.get('tarea') or '-'
                filas_bad.append((num, tarea, prov))
        texto += _formatear_tabla(filas_bad, tabla_headers) + '\n'
        html += '<h3>No se encontraron archivos para las siguientes OC:</h3>' + _tabla_html(filas_bad, tabla_headers)
    mensaje.set_content(texto)
    mensaje.add_alternative(html, subtype='html')
    candidatos: list[str] = []

    def _agregar_candidato(valor: str | None):
        if not valor:
            return
        candidatos.append(valor)
        if "@" in valor:
            base, _, resto = valor.partition("@")
            dominio = resto.split(".")[0].upper() if resto else ""
            if base:
                candidatos.append(base)
                if dominio:
                    candidatos.append(f"{dominio}\\{base}")

    _agregar_candidato(smtp_usuario)
    if usuario_pop != smtp_usuario:
        _agregar_candidato(usuario_pop)

    usernames = list(dict.fromkeys(c for c in candidatos if c))

    def _intentar_envio(factory):
        last_error: Exception | None = None
        for u in usernames:
            try:
                with factory() as smtp:
                    try:
                        smtp.login(u, smtp_password)
                    except smtplib.SMTPAuthenticationError as exc:
                        logger.warning("Fallo de autenticación con '%s'", u)
                        last_error = exc
                        continue
                    smtp.send_message(mensaje)
                    logger.info('Reporte enviado')
                    return True
            except smtplib.SMTPAuthenticationError as exc:
                logger.warning("Fallo de autenticación con '%s'", u)
                last_error = exc
            except Exception as exc:
                logger.error('No se pudo enviar reporte: %s', exc)
                return False
        if last_error:
            logger.error('No se pudo enviar reporte: %s', last_error)
        return False

    def _smtp_tls():
        s = smtplib.SMTP(smtp_server, smtp_port)
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

    if _intentar_envio(lambda: smtplib.SMTP_SSL(smtp_server, smtp_ssl_port)):
        try:
            ORDENES_TMP.unlink(missing_ok=True)
        except Exception:
            pass
        return True

    def _smtp_plain():
        s = smtplib.SMTP(smtp_server, smtp_plain_port)
        s.ehlo()
        return s

    if _intentar_envio(_smtp_plain):
        try:
            ORDENES_TMP.unlink(missing_ok=True)
        except Exception:
            pass
        return True

    return False

