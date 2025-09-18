import poplib
from email import parser as email_parser
from email.header import decode_header, make_header
from email.utils import getaddresses
import json
import re
import html
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:  # allow running as script without package
    from .config import Config
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
PROCESADOS_FILE = DATA_DIR / 'procesados.txt'
LAST_UIDL_FILE = DATA_DIR / 'last_uidl.txt'
ORDENES_TMP = DATA_DIR / 'ordenes_tmp.json'
REMITENTES_BASE = {
    'jotoapanta@telconet.ec',
    'naf@telconet.ec',
}


def _normalizar_remitentes(valor: str | None) -> set[str]:
    """Extrae direcciones de correo en minúsculas desde un encabezado."""

    if not valor:
        return set()
    parsed = {
        addr.strip().lower()
        for _, addr in getaddresses([valor.replace(';', ',')])
        if addr
    }
    if parsed:
        return parsed
    return {valor.strip().lower()}


def _conjunto_remitentes(valor) -> set[str]:
    """Convierte diferentes formatos (str, lista) en un conjunto de correos."""

    if not valor:
        return set()
    if isinstance(valor, str):
        return _normalizar_remitentes(valor)
    remitentes: set[str] = set()
    try:
        iterable = list(valor)
    except TypeError:
        return _normalizar_remitentes(str(valor))
    for item in iterable:
        remitentes.update(_normalizar_remitentes(str(item)))
    return remitentes


def _limpiar_html(valor: str) -> str:
    """Convierte HTML básico en texto plano preservando saltos de línea."""

    if not valor:
        return ""
    texto = re.sub(r"(?i)<br\s*/?>", "\n", valor)
    texto = re.sub(r"(?i)</p>", "\n", texto)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = html.unescape(texto)
    return texto.replace("\xa0", " ")


def cargar_procesados() -> set[str]:
    try:
        with open(PROCESADOS_FILE, 'r') as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()


def guardar_procesado(uidl: str):
    PROCESADOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PROCESADOS_FILE, 'a') as f:
        f.write(uidl + '\n')


def cargar_ultimo_uidl() -> str:
    try:
        with open(LAST_UIDL_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        return ''


def guardar_ultimo_uidl(uidl: str):
    LAST_UIDL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_UIDL_FILE, 'w') as f:
        f.write(uidl)


def registrar_procesados(uidls: list[str], ultimo: str | None):
    """Marca los mensajes como procesados y actualiza el último UIDL."""
    for uidl in uidls:
        guardar_procesado(uidl)
    if ultimo:
        guardar_ultimo_uidl(ultimo)


def extraer_datos(asunto: str, cuerpo: str):
    """Extrae número de OC, fechas, proveedor y tarea del asunto/cuerpo."""
    numero = None
    fecha_aut = None
    fecha_orden = None
    proveedor = None
    tarea = None

    if asunto:
        patt = r"SISTEMA\s+NAF:.*?ORDEN\s+COMPRA\s+(?:NO|N[°º])\.?\s*(\d+)"
        m = re.search(patt, asunto, re.IGNORECASE)
        if m:
            numero = m.group(1)

    cuerpo_texto = _limpiar_html(cuerpo or "")

    if cuerpo_texto:
        if not numero:
            m = re.search(r"orden\s+de\s+compra\s+de\s+(?:No|N[°º])\.?\s*(\d+)", cuerpo_texto, re.IGNORECASE)
            if m:
                numero = m.group(1)
        m = re.search(r"Fecha\s+Autorizaci(?:o|\xc3\xb3)n[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})", cuerpo_texto, re.IGNORECASE)
        if m:
            fecha_aut = m.group(1)
        m = re.search(r"Fecha\s+Orden[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})", cuerpo_texto, re.IGNORECASE)
        if m:
            fecha_orden = m.group(1)
        m = re.search(r"proveedor\s*:?[\s\xa0]+([^\n]+?)(?:\s+con\s+Fecha|\n|$)", cuerpo_texto, re.IGNORECASE)
        if m:
            proveedor = re.sub(r"\s+", " ", m.group(1)).strip()
        m = re.search(r"#(\d+)\s*//", cuerpo_texto)
        if m:
            tarea = m.group(1)

    return numero, fecha_aut, fecha_orden, proveedor, tarea


def _descargar_mensaje(num: int, cfg: Config) -> tuple[str, bytes]:
    conn = poplib.POP3_SSL(cfg.pop_server, cfg.pop_port)
    conn.user(cfg.usuario)
    conn.pass_(cfg.password)
    resp_uidl = conn.uidl(num)
    line = resp_uidl.decode() if isinstance(resp_uidl, bytes) else resp_uidl
    uidl = line.split()[-1]
    resp = conn.retr(num)
    conn.quit()
    raw = b"\n".join(resp[1])
    return uidl, raw


def buscar_ocs(cfg: Config) -> tuple[list[dict], str | None]:
    procesados = cargar_procesados()
    last_uidl = cargar_ultimo_uidl()

    remitentes_validos = {r.lower() for r in REMITENTES_BASE}
    remitentes_validos.update(_conjunto_remitentes(getattr(cfg, 'usuario', None)))
    remitentes_validos.update(_conjunto_remitentes(getattr(cfg, 'remitente_adicional', None)))
    remitentes_validos.discard('')

    conn = poplib.POP3_SSL(cfg.pop_server, cfg.pop_port)
    conn.user(cfg.usuario)
    conn.pass_(cfg.password)

    resp, uidl_lines, _ = conn.uidl()
    entries = [line.decode().split() for line in uidl_lines]
    mensajes = [(int(num), uidl) for num, uidl in entries]
    conn.quit()

    indices: list[tuple[int, str]] = []
    nuevo_ultimo = None
    for num, uidl in reversed(mensajes):
        if uidl == last_uidl:
            break
        if nuevo_ultimo is None:
            nuevo_ultimo = uidl
        if uidl in procesados:
            continue
        indices.append((num, uidl))
        if len(indices) >= cfg.batch_size:
            break

    ordenes: list[dict] = []
    if not indices:
        return ordenes, nuevo_ultimo

    with ThreadPoolExecutor(max_workers=cfg.max_threads) as ex:
        futures = {ex.submit(_descargar_mensaje, num, cfg): (num, uidl) for num, uidl in indices}
        for fut in futures:
            num, uidl = futures[fut]
            try:
                uidl_res, raw = fut.result()
                logger.debug("Procesado UIDL %s", uidl_res)
                mensaje = email_parser.BytesParser().parsebytes(raw)
                raw_sub = mensaje.get('Subject', '')
                raw_from = mensaje.get('From', '')
                asunto = str(make_header(decode_header(raw_sub)))
                remitente = str(make_header(decode_header(raw_from)))
                cuerpo = ''
                if mensaje.is_multipart():
                    for parte in mensaje.walk():
                        if parte.get_content_type() == 'text/plain':
                            try:
                                charset = parte.get_content_charset() or 'utf-8'
                                cuerpo += parte.get_payload(decode=True).decode(charset, errors='replace')
                            except Exception:
                                pass
                else:
                    charset = mensaje.get_content_charset() or 'utf-8'
                    cuerpo = mensaje.get_payload(decode=True).decode(charset, errors='replace')
                numero, fecha_aut, fecha_orden, proveedor, tarea = extraer_datos(asunto, cuerpo)
                asunto_ok = re.search(r'SISTEMA\s+NAF:.*AUTORIZACI', asunto or '', re.IGNORECASE)
                remitentes_mensaje: set[str] = set()
                for header_name in ('From', 'Reply-To', 'Sender', 'Return-Path'):
                    raw_header = mensaje.get(header_name)
                    if not raw_header:
                        continue
                    decoded_header = str(make_header(decode_header(raw_header)))
                    remitentes_mensaje.update(_normalizar_remitentes(decoded_header))
                if not remitentes_mensaje:
                    remitentes_mensaje = _normalizar_remitentes(remitente)
                remitente_ok = bool(remitentes_mensaje & remitentes_validos)
                if remitente_ok and asunto_ok and numero:
                    ordenes.append({'uidl': uidl_res, 'numero': numero, 'fecha_aut': fecha_aut, 'fecha_orden': fecha_orden, 'proveedor': proveedor, 'tarea': tarea})
                elif remitente_ok:
                    logger.warning(
                        'Mensaje UIDL %s de remitente válido sin datos de OC. Asunto="%s"',
                        uidl_res,
                        asunto,
                    )
                else:
                    guardar_procesado(uidl_res)
            except Exception as e:
                logger.error('Error procesando mensaje %s: %s', num, e)

    logger.info('Órdenes encontradas: %d', len(ordenes))
    try:
        ORDENES_TMP.parent.mkdir(parents=True, exist_ok=True)
        with open(ORDENES_TMP, 'w', encoding='utf-8') as f:
            json.dump(ordenes, f, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover
        logger.warning('No se pudo guardar ordenes_tmp: %s', exc)
    return ordenes, nuevo_ultimo

