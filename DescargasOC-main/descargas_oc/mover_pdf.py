import os
import re
import shutil
from pathlib import Path

import PyPDF2

try:  # allow running as script
    from .config import Config
    from .logger import get_logger
    from .seafile_client import SeafileClient
    from .organizador_bienes import extraer_numero_tarea_desde_pdf
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger
    from seafile_client import SeafileClient
    from organizador_bienes import extraer_numero_tarea_desde_pdf

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
    indice_ordenes = {o.get("numero"): o for o in ordenes}

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
    encontrados: dict[str, str] = {}

    # intentar asociar por nombre de archivo primero (más rápido y confiable)
    for archivo in archivos:
        ruta = os.path.join(carpeta_origen, archivo)
        m = re.match(r"^(\d+)", archivo)
        if m:
            num = m.group(1)
            if num in numeros_oc and num not in encontrados:
                encontrados[num] = ruta

    # para los que no se encontraron, buscar dentro del contenido del PDF
    restantes = [a for a in archivos if os.path.join(carpeta_origen, a) not in encontrados.values()]
    for archivo in restantes:
        ruta = os.path.join(carpeta_origen, archivo)
        try:
            with open(ruta, 'rb') as f:
                pdf = PyPDF2.PdfReader(f)
                texto = ''.join(p.extract_text() or '' for p in pdf.pages)
        except Exception as e:
            logger.warning('Error leyendo %s: %s', archivo, e)
            continue
        for numero in numeros_oc:
            if numero in encontrados:
                continue
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
            if ruta != nuevo_nombre:
                try:
                    os.rename(ruta, nuevo_nombre)
                    ruta = nuevo_nombre
                except Exception as e:
                    logger.warning('No se pudo renombrar %s: %s', ruta, e)

        # extraer número de tarea para organizar y para el reporte
        tarea = extraer_numero_tarea_desde_pdf(ruta)
        if indice_ordenes.get(numero) is not None:
            indice_ordenes[numero]["tarea"] = tarea

        if tarea:
            # buscar carpeta existente que comience con el número de tarea
            destino = None
            for root, dirs, _files in os.walk(carpeta_destino):
                for d in dirs:
                    if d.startswith(tarea):
                        destino = os.path.join(root, d)
                        break
                if destino:
                    break
            if not destino:
                destino = os.path.join(carpeta_destino, tarea)
                os.makedirs(destino, exist_ok=True)
            try:
                nombre_archivo = os.path.basename(ruta)
                destino_archivo = os.path.join(destino, nombre_archivo)
                if os.path.exists(destino_archivo):
                    base, ext = os.path.splitext(nombre_archivo)
                    i = 1
                    while os.path.exists(destino_archivo):
                        destino_archivo = os.path.join(destino, f"{base} ({i}){ext}")
                        i += 1
                shutil.copy2(ruta, destino_archivo)
                logger.info("%s copiado a %s", nombre_archivo, destino)
            except Exception as e:
                logger.warning("No se pudo copiar %s a %s: %s", ruta, destino, e)

        try:
            cliente.upload_file(repo_id, ruta, parent_dir=subfolder)
            subidos.append(numero)
            logger.info('Subido %s', os.path.basename(ruta))
        except Exception as e:
            logger.error('Error subiendo %s: %s', ruta, e)

    # limpiar carpeta de origen después del proceso
    for f in Path(carpeta_origen).glob("*.pdf"):
        try:
            f.unlink()
        except Exception:
            pass
    return subidos, faltantes

