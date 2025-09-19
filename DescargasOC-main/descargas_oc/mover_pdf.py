import os
import re
import shutil
import time
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

MAX_NOMBRE = 180
REINTENTOS = 5
ESPERA_INICIAL = 0.3


def _nombre_destino(numero: str | None, proveedor: str | None, ext: str) -> str:
    numero = (numero or "").strip()
    base = numero
    if proveedor:
        prov_clean = re.sub(r"[^\w\- ]", "_", proveedor)
        prov_clean = re.sub(r"\s+", " ", prov_clean).strip()
        base = f"{base} - NOMBRE {prov_clean}" if base else prov_clean
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        base = "archivo"
    if len(base) > MAX_NOMBRE:
        base = base[:MAX_NOMBRE].rstrip(" .-_")
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


def _asegurar_nombre(ruta_path: Path, nombre_deseado: str) -> tuple[Path | None, str | None]:
    if ruta_path.name == nombre_deseado:
        return ruta_path, None
    ultimo_error: Exception | None = None
    destino_final: Path | None = None
    for intento in range(REINTENTOS):
        destino = _resolver_conflicto(ruta_path.parent, nombre_deseado)
        destino_final = destino
        try:
            ruta_path.rename(destino)
            return destino, None
        except PermissionError as exc:
            ultimo_error = exc
        except OSError as exc:
            ultimo_error = exc
            break
        if intento < REINTENTOS - 1:
            time.sleep(ESPERA_INICIAL * (intento + 1))
    if ultimo_error:
        logger.warning(
            "No se pudo renombrar '%s' como '%s': %s",
            ruta_path,
            destino_final or (ruta_path.parent / nombre_deseado),
            ultimo_error,
        )
        mensaje = (
            f"No se pudo renombrar '{ruta_path.name}' a "
            f"'{(destino_final or Path(nombre_deseado)).name}': {ultimo_error}"
        )
    else:
        mensaje = (
            f"No se pudo renombrar '{ruta_path.name}' a '{nombre_deseado}'"
        )
    return None, mensaje


def _mover_archivo(
    ruta_path: Path, destino_dir: Path, nombre_final: str
) -> tuple[Path | None, str | None]:
    ultimo_error: Exception | None = None
    destino_final: Path | None = None
    for intento in range(REINTENTOS):
        destino = _resolver_conflicto(destino_dir, nombre_final)
        destino_final = destino
        try:
            resultado = Path(shutil.move(str(ruta_path), destino))
            return resultado, None
        except PermissionError as exc:
            ultimo_error = exc
        except OSError as exc:
            ultimo_error = exc
        if intento < REINTENTOS - 1:
            time.sleep(ESPERA_INICIAL * (intento + 1))

    if ruta_path.exists():
        destino_final = _resolver_conflicto(destino_dir, nombre_final)
        try:
            shutil.copy2(str(ruta_path), str(destino_final))
            try:
                ruta_path.unlink()
            except Exception as exc:  # pragma: no cover - best effort cleanup
                logger.warning(
                    "No se pudo eliminar '%s' tras copiarlo a '%s': %s",
                    ruta_path,
                    destino_final,
                    exc,
                )
            return destino_final, None
        except Exception as exc:
            ultimo_error = exc

    if ultimo_error:
        logger.warning(
            "No se pudo mover '%s' a '%s': %s",
            ruta_path,
            destino_final.parent if destino_final else destino_dir,
            ultimo_error,
        )
        return (
            None,
            f"No se pudo mover '{ruta_path.name}' a "
            f"'{destino_final or destino_dir}': {ultimo_error}",
        )
    return None, f"No se pudo mover '{ruta_path.name}' a '{destino_dir}'"


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

        ruta_path, error_nombre = _asegurar_nombre(ruta_path, nombre_deseado)
        if ruta_path is None:
            errores.append(f"OC {numero}: {error_nombre}")
            faltantes.append(numero)
            continue

        ruta = str(ruta_path)
        nombre_archivo = ruta_path.name

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
            destino_path, error_mov = _mover_archivo(ruta_path, Path(destino), nombre_archivo)
            if destino_path is None:
                errores.append(f"OC {numero}: {error_mov}")
                faltantes.append(numero)
                # mantener el archivo disponible en origen para reintentos
                continue
            ruta = str(destino_path)
            logger.info("%s movido a %s", destino_path.name, destino_path.parent)
        else:
            procesados_en_origen.add(ruta_path)

        subidos.append(numero)

    # limpiar carpeta de origen después del proceso
    for f in Path(carpeta_origen).glob("*.pdf"):
        if f in procesados_en_origen:
            try:
                f.unlink()
            except Exception:
                pass
    return subidos, faltantes, errores

