import poplib
from email import parser as email_parser
from email.header import decode_header, make_header
import re
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
REMITENTE_BASE = 'jotoapanta@telconet.ec'


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
    """Extrae número de OC, fechas y proveedor del asunto/cuerpo."""
    numero = None
    fecha_aut = None
    fecha_orden = None
    proveedor = None

    if asunto:
        patt = r"SISTEMA\s+NAF:.*?ORDEN\s+COMPRA\s+(?:NO|N[°º])\.?\s*(\d+)"
        m = re.search(patt, asunto, re.IGNORECASE)
        if m:
            numero = m.group(1)

    if cuerpo:
        if not numero:
            m = re.search(r"orden\s+de\s+compra\s+de\s+(?:No|N[°º])\.?\s*(\d+)", cuerpo, re.IGNORECASE)
            if m:
                numero = m.group(1)
        m = re.search(r"Fecha\s+Autorizaci(?:o|\xc3\xb3)n[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})", cuerpo, re.IGNORECASE)
        if m:
            fecha_aut = m.group(1)
        m = re.search(r"Fecha\s+Orden[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})", cuerpo, re.IGNORECASE)
        if m:
            fecha_orden = m.group(1)
        m = re.search(r"proveedor\s+([^\n]+?)(?:\s+con\s+Fecha|\n|$)", cuerpo, re.IGNORECASE)
        if m:
            proveedor = m.group(1).strip()

    return numero, fecha_aut, fecha_orden, proveedor


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

    remitentes_validos = {REMITENTE_BASE}
    extra = getattr(cfg, 'remitente_adicional', None)
    if extra:
        remitentes_validos.add(extra.lower())

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
                numero, fecha_aut, fecha_orden, proveedor = extraer_datos(asunto, cuerpo)
                asunto_ok = re.search(r'SISTEMA\s+NAF:.*AUTORIZACI', asunto or '', re.IGNORECASE)
                remitente_ok = any(r in remitente.lower() for r in remitentes_validos)
                if remitente_ok and asunto_ok and numero:
                    ordenes.append({'uidl': uidl_res, 'numero': numero, 'fecha_aut': fecha_aut, 'fecha_orden': fecha_orden, 'proveedor': proveedor})
                else:
                    guardar_procesado(uidl_res)
            except Exception as e:
                logger.error('Error procesando mensaje %s: %s', num, e)

    logger.info('Órdenes encontradas: %d', len(ordenes))
    return ordenes, nuevo_ultimo

