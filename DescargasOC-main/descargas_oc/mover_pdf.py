import os
import shutil
import PyPDF2

try:  # allow running as script
    from .config import Config
    from .logger import get_logger
    from .seafile_client import SeafileClient
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger
    from seafile_client import SeafileClient

logger = get_logger(__name__)


def mover_oc(config: Config, numeros_oc=None):
    if numeros_oc is None:
        numeros_oc = []
    carpeta_origen = config.carpeta_destino_local
    carpeta_destino = config.carpeta_analizar
    repo_id = config.seafile_repo_id
    subfolder = config.seafile_subfolder or '/'
    if not carpeta_origen or not repo_id:
        logger.error("Configuración incompleta")
        return [], numeros_oc
    if not os.path.exists(carpeta_origen):
        logger.error('Carpeta origen inexistente: %s', carpeta_origen)
        return [], numeros_oc

    cliente = SeafileClient(config.seafile_url, config.usuario, config.password)

    archivos = [f for f in os.listdir(carpeta_origen) if f.lower().endswith('.pdf')]
    encontrados = {}
    for archivo in archivos:
        ruta = os.path.join(carpeta_origen, archivo)
        try:
            with open(ruta, 'rb') as f:
                pdf = PyPDF2.PdfReader(f)
                texto = ''.join(p.extract_text() or '' for p in pdf.pages)
        except Exception as e:
            logger.warning('Error leyendo %s: %s', archivo, e)
            continue
        if 'ORDEN DE COMPRA' not in texto.upper():
            continue
        for numero in numeros_oc:
            if numero in texto:
                encontrados[numero] = ruta
                break

    faltantes = []
    subidos = []
    for numero in numeros_oc:
        ruta = encontrados.get(numero)
        if not ruta:
            faltantes.append(numero)
            continue
        try:
            cliente.upload_file(repo_id, ruta, parent_dir=subfolder)
            os.makedirs(carpeta_destino, exist_ok=True)
            shutil.move(ruta, os.path.join(carpeta_destino, os.path.basename(ruta)))
            subidos.append(numero)
            logger.info('Subido %s', os.path.basename(ruta))
        except Exception as e:
            logger.error('Error subiendo %s: %s', ruta, e)
    return subidos, faltantes

