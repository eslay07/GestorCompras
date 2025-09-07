import os
import re
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


def mover_oc(config: Config, ordenes=None):
    """Sube y mueve los PDF de las órdenes descargadas.

    ``ordenes`` debe ser una lista de diccionarios con al menos la clave
    ``numero`` y opcionalmente ``proveedor``.
    """
    ordenes = ordenes or []
    # evitar números repetidos para no procesar la misma OC varias veces
    numeros_oc = list(dict.fromkeys(o.get("numero") for o in ordenes))
    proveedores = {o.get("numero"): o.get("proveedor") for o in ordenes}

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
            if numero and numero in texto:
                encontrados[numero] = ruta
                break

    faltantes = []
    subidos = []
    for numero in numeros_oc:
        ruta = encontrados.get(numero)
        if not ruta:
            faltantes.append(numero)
            continue

        prov = proveedores.get(numero)
        if prov:
            prov_clean = re.sub(r"[^\w\- ]", "_", prov)
            nuevo_nombre = os.path.join(carpeta_origen, f"{numero} - {prov_clean}.pdf")
            try:
                os.rename(ruta, nuevo_nombre)
                ruta = nuevo_nombre
            except Exception as e:
                logger.warning('No se pudo renombrar %s: %s', ruta, e)

        try:
            # Subir primero y luego copiar manualmente para evitar archivos corruptos
            cliente.upload_file(repo_id, ruta, parent_dir=subfolder)
            os.makedirs(carpeta_destino, exist_ok=True)
            destino_final = os.path.join(carpeta_destino, os.path.basename(ruta))
            with open(ruta, "rb") as src, open(destino_final, "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.remove(ruta)
            subidos.append(numero)
            logger.info('Subido %s', os.path.basename(destino_final))
        except Exception as e:
            logger.error('Error subiendo %s: %s', ruta, e)
    return subidos, faltantes

