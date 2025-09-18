import os
import re
import shutil
from pathlib import Path

import PyPDF2

try:  # allow running as script
    from .config import Config
    from .logger import get_logger
    from .organizador_bienes import (
        extraer_numero_tarea_desde_pdf,
        extraer_proveedor_desde_pdf,
    )
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger
    from organizador_bienes import (
        extraer_numero_tarea_desde_pdf,
        extraer_proveedor_desde_pdf,
    )

logger = get_logger(__name__)


def mover_oc(config: Config, ordenes=None):
    """Renombra y mueve los PDF de las órdenes descargadas.

    ``ordenes`` debe ser una lista de diccionarios con al menos la clave
    ``numero`` y opcionalmente ``proveedor``.  Devuelve una tupla con las
    órdenes subidas, las que faltaron y una lista de errores descriptivos.
    """
    ordenes = ordenes or []
    # evitar números repetidos para no procesar la misma OC varias veces
    numeros_oc = list(dict.fromkeys(o.get("numero") for o in ordenes))
    proveedores = {o.get("numero"): o.get("proveedor") for o in ordenes}
    indice_ordenes = {o.get("numero"): o for o in ordenes}

    carpeta_origen = (
        getattr(config, 'abastecimiento_carpeta_descarga', None)
        or config.carpeta_destino_local
    )
    carpeta_destino = config.carpeta_analizar
    errores: list[str] = []
    if not carpeta_origen:
        logger.error("Configuración incompleta")
        errores.append("Carpeta de descarga no configurada")
        return [], numeros_oc, errores
    if not os.path.exists(carpeta_origen):
        logger.error('Carpeta origen inexistente: %s', carpeta_origen)
        errores.append(f"Carpeta origen inexistente: {carpeta_origen}")
        return [], numeros_oc, errores

    archivos = [f for f in os.listdir(carpeta_origen) if f.lower().endswith('.pdf')]
    encontrados: dict[str, str] = {}
    procesados_en_origen: set[Path] = set()

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

    faltantes: list[str] = []
    subidos: list[str] = []
    es_bienes = bool(getattr(config, "compra_bienes", False))
    for numero in numeros_oc:
        ruta = encontrados.get(numero)
        if not ruta:
            faltantes.append(numero)
            errores.append(f"OC {numero}: archivo no encontrado en carpeta de descarga")
            continue

        prov = proveedores.get(numero)
        if not prov:
            prov = extraer_proveedor_desde_pdf(ruta)
            if indice_ordenes.get(numero) is not None and prov:
                indice_ordenes[numero]["proveedor"] = prov
        if prov:
            prov_clean = re.sub(r"[^\w\- ]", "_", prov)
            nuevo_nombre = os.path.join(
                carpeta_origen, f"{numero} - NOMBRE {prov_clean}.pdf"
            )
            if ruta != nuevo_nombre:
                try:
                    os.rename(ruta, nuevo_nombre)
                    ruta = nuevo_nombre
                except Exception as e:
                    logger.warning('No se pudo renombrar %s: %s', ruta, e)

        tarea = None
        if es_bienes:
            # extraer número de tarea para organizar y para el reporte
            tarea = extraer_numero_tarea_desde_pdf(ruta)
            if indice_ordenes.get(numero) is not None:
                indice_ordenes[numero]["tarea"] = tarea

        if es_bienes:
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
            else:
                destino = os.path.join(carpeta_destino, "ordenes sin tarea")
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
                shutil.move(ruta, destino_archivo)
                ruta = destino_archivo
                logger.info("%s movido a %s", nombre_archivo, destino)
            except Exception as e:
                logger.warning("No se pudo mover %s a %s: %s", ruta, destino, e)
                errores.append(
                    f"OC {numero}: no se pudo mover a '{destino}': {e}"
                )
                faltantes.append(numero)
                # intentar mantener el archivo en la carpeta de origen para reintentos
                continue

        subidos.append(numero)
        if not es_bienes:
            procesados_en_origen.add(Path(ruta))

    # limpiar carpeta de origen después del proceso
    for f in Path(carpeta_origen).glob("*.pdf"):
        if f in procesados_en_origen:
            try:
                f.unlink()
            except Exception:
                pass
    return subidos, faltantes, errores

