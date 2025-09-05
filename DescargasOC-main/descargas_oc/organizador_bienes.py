import os
import re
import shutil

try:
    from pypdf import PdfReader  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from PyPDF2 import PdfReader  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Falta 'pypdf' o 'PyPDF2'. Instálalo con: py -m pip install --user pypdf") from exc

try:
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from logger import get_logger

logger = get_logger(__name__)

PATRON_TAREA = re.compile(r"#\s*([0-9]{6,11})\s*//")


def extraer_numero_tarea_desde_pdf(ruta_pdf: str) -> str | None:
    try:
        reader = PdfReader(ruta_pdf)
    except Exception as e:
        logger.error("No se pudo abrir '%s': %s", ruta_pdf, e)
        return None
    for page in getattr(reader, "pages", []):
        try:
            texto = page.extract_text() or ""
        except Exception:
            texto = ""
        if not texto:
            continue
        m = PATRON_TAREA.search(texto)
        if m:
            return m.group(1)
    return None


def indexar_carpetas_destino(raiz: str) -> list[tuple[str, str]]:
    indice = []
    for root, dirs, _files in os.walk(raiz):
        for nombre in dirs:
            indice.append((os.path.join(root, nombre), nombre))
    return indice


def elegir_mejor_carpeta_para_numero(numero: str, indice_carpetas: list[tuple[str, str]]) -> str | None:
    candidatos = [ruta for ruta, nombre in indice_carpetas if nombre.startswith(numero)]
    if not candidatos:
        return None
    candidatos_ordenados = sorted(candidatos, key=lambda p: (len(os.path.basename(p)), p.lower()))
    return candidatos_ordenados[0]


def mover_sin_sobrescribir(ruta_archivo_origen: str, carpeta_destino: str) -> str | None:
    nombre = os.path.basename(ruta_archivo_origen)
    base, ext = os.path.splitext(nombre)
    destino = os.path.join(carpeta_destino, nombre)
    os.makedirs(carpeta_destino, exist_ok=True)
    if os.path.exists(destino):
        i = 1
        while True:
            nuevo_nombre = f"{base} ({i}){ext}"
            destino = os.path.join(carpeta_destino, nuevo_nombre)
            if not os.path.exists(destino):
                break
            i += 1
    try:
        shutil.move(ruta_archivo_origen, destino)
        return destino
    except Exception as e:  # pragma: no cover
        logger.error("No se pudo mover '%s' a '%s': %s", ruta_archivo_origen, carpeta_destino, e)
        return None


def organizar(origen: str, raiz_destino: str):
    try:
        archivos_pdf = [a for a in os.listdir(origen) if a.lower().endswith('.pdf')]
    except FileNotFoundError:
        logger.error("La ruta de origen no existe: %s", origen)
        return
    if not archivos_pdf:
        return
    indice = indexar_carpetas_destino(raiz_destino)
    for nombre_pdf in archivos_pdf:
        ruta_pdf = os.path.join(origen, nombre_pdf)
        numero_tarea = extraer_numero_tarea_desde_pdf(ruta_pdf)
        if not numero_tarea:
            logger.info("No se encontró número en '%s'", nombre_pdf)
            continue
        carpeta_destino = elegir_mejor_carpeta_para_numero(numero_tarea, indice)
        if not carpeta_destino:
            logger.info("No hay carpeta que empiece con '%s' para '%s'", numero_tarea, nombre_pdf)
            continue
        ruta_final = mover_sin_sobrescribir(ruta_pdf, carpeta_destino)
        if ruta_final:
            logger.info("%s movido a %s", nombre_pdf, carpeta_destino)
