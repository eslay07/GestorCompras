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


def _nombre_destino(numero: str | None, proveedor: str | None, ext: str) -> str:
    numero = numero or ""
    base = numero.strip()
    if proveedor:
        prov_clean = re.sub(r"[^\w\- ]", "_", proveedor)
        base = f"{base} - NOMBRE {prov_clean}" if base else prov_clean
    if not base:
        base = "archivo"
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ".pdf"
    return f"{base}{ext}"


def _resolver_conflicto(destino_dir: Path, nombre: str) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / nombre
    if not destino.exists():
        return destino
    base, ext = os.path.splitext(nombre)
    i = 1
    while True:
        candidato = destino_dir / f"{base} ({i}){ext}"
        if not candidato.exists():
            return candidato
        i += 1


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

        tarea = None
        if es_bienes:
            # extraer número de tarea para organizar y para el reporte
            tarea = extraer_numero_tarea_desde_pdf(ruta)
            if indice_ordenes.get(numero) is not None:
                indice_ordenes[numero]["tarea"] = tarea

        ruta_path = Path(ruta)
        ext = ruta_path.suffix or ".pdf"
        nombre_deseado = _nombre_destino(numero, prov, ext)

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
            destino_path = _resolver_conflicto(Path(destino), nombre_deseado)
            try:
                shutil.move(str(ruta_path), destino_path)
                ruta = str(destino_path)
                logger.info("%s movido a %s", destino_path.name, destino_path.parent)
            except Exception as e:
                logger.warning("No se pudo mover %s a %s: %s", ruta, destino_path.parent, e)
                errores.append(
                    f"OC {numero}: no se pudo mover a '{destino_path.parent}': {e}"
                )
                faltantes.append(numero)
                # intentar mantener el archivo en la carpeta de origen para reintentos
                continue
        else:
            destino_path = _resolver_conflicto(ruta_path.parent, nombre_deseado)
            if destino_path != ruta_path:
                try:
                    shutil.move(str(ruta_path), destino_path)
                    ruta_path = destino_path
                    ruta = str(destino_path)
                except Exception as e:
                    logger.warning("No se pudo renombrar %s a %s: %s", ruta, destino_path.name, e)
                    ruta = str(ruta_path)
            procesados_en_origen.add(Path(ruta))

        subidos.append(numero)

    # limpiar carpeta de origen después del proceso
    for f in Path(carpeta_origen).glob("*.pdf"):
        if f in procesados_en_origen:
            try:
                f.unlink()
            except Exception:
                pass
    return subidos, faltantes, errores

