import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

import PyPDF2

try:  # permite ejecutar el módulo directamente
    from .config import Config
    from .logger import get_logger
    from .organizador_bienes import (
        extraer_numero_tarea_desde_pdf,
        extraer_proveedor_desde_pdf,
    )
    from .pdf_info import nombre_archivo_orden
except ImportError:  # pragma: no cover
    from config import Config
    from logger import get_logger
    from organizador_bienes import (
        extraer_numero_tarea_desde_pdf,
        extraer_proveedor_desde_pdf,
    )
    from pdf_info import nombre_archivo_orden

logger = get_logger(__name__)
REINTENTOS = 5
ESPERA_INICIAL = 0.3
LONGITUD_MAXIMA_PROVEEDOR = 50


def normalizar_nombre_archivo(nombre: str | None, longitud_maxima: int = LONGITUD_MAXIMA_PROVEEDOR) -> str:
    """Normaliza *nombre* para uso seguro en nombres de archivo."""

    texto = (nombre or "").strip()
    if not texto:
        return ""
    texto = re.sub(r"[^\w\- ]", "_", texto)
    texto = re.sub(r"\s+", "_", texto)
    texto = re.sub(r"_+", "_", texto).strip("_")
    if longitud_maxima and len(texto) > longitud_maxima:
        texto = texto[:longitud_maxima].rstrip("_- ")
    return texto.lower()


def _nombre_contiene_numero(nombre: str, numero: str | None) -> bool:
    if not nombre or not numero:
        return False
    patron = rf"(?<!\\d){re.escape(numero)}(?!\\d)"
    return re.search(patron, nombre) is not None


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
        mensaje = f"No se pudo renombrar '{ruta_path.name}' a '{nombre_deseado}'"
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
            except Exception as exc:  # pragma: no cover - limpieza de mejor esfuerzo
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


def _carpetas_origen(config: Config) -> list[Path]:
    """Obtiene las carpetas de descarga configuradas sin duplicados."""

    rutas: list[Path] = []
    for attr in ("carpeta_destino_local", "abastecimiento_carpeta_descarga"):
        valor = getattr(config, attr, None)
        if not valor:
            continue
        try:
            path = Path(valor)
        except (TypeError, ValueError, OSError):  # pragma: no cover - rutas inválidas
            continue
        if path not in rutas:
            rutas.append(path)
    return rutas


def _destino_no_bienes(
    config: Config, orden: Mapping[str, Any] | None
) -> Path | None:
    """Determina la carpeta destino apropiada para una OC que no es de bienes."""

    categoria = ""
    if isinstance(orden, Mapping):
        valor = orden.get("categoria")
        if valor:
            categoria = str(valor).strip().lower()

    rutas_preferidas: list[Any] = []
    if categoria == "abastecimiento":
        rutas_preferidas.extend(
            [
                getattr(config, "abastecimiento_carpeta_descarga", None),
                getattr(config, "carpeta_destino_local", None),
            ]
        )
    rutas_preferidas.append(getattr(config, "carpeta_analizar", None))

    for ruta in rutas_preferidas:
        if not ruta:
            continue
        try:
            return Path(ruta)
        except (TypeError, ValueError, OSError):  # pragma: no cover - ruta inválida
            continue
    return None


def mover_oc(config: Config, ordenes=None):
    """Renombra y mueve los PDF de las órdenes descargadas.

    Devuelve (subidos, faltantes, errores, ubicaciones), donde ubicaciones es un
    diccionario numero->ruta final del PDF.
    """

    ordenes = ordenes or []
    numeros_oc = list(dict.fromkeys(o.get("numero") for o in ordenes))
    proveedores = {o.get("numero"): o.get("proveedor") for o in ordenes}
    indice_ordenes = {o.get("numero"): o for o in ordenes}

    carpetas_origen = _carpetas_origen(config)
    errores: list[str] = []
    if not carpetas_origen:
        logger.error("Carpetas de descarga no configuradas")
        errores.append("Carpetas de descarga no configuradas")
        return [], numeros_oc, errores, {}

    archivos: list[Path] = []
    for carpeta in carpetas_origen:
        if not carpeta.exists():
            logger.warning("Carpeta origen inexistente: %s", carpeta)
            continue
        archivos.extend(p for p in carpeta.glob("*.pdf"))

    encontrados: dict[str, Path] = {}

    for ruta_path in archivos:
        archivo = ruta_path.name
        for numero in numeros_oc:
            if not numero or numero in encontrados:
                continue
            if _nombre_contiene_numero(archivo, numero):
                encontrados[numero] = ruta_path
                break

    restantes = [ruta for ruta in archivos if ruta not in set(encontrados.values())]
    for ruta_path in restantes:
        ruta = str(ruta_path)
        try:
            with open(ruta, "rb") as archivo_pdf:
                lector = PyPDF2.PdfReader(archivo_pdf)
                texto = "".join(pagina.extract_text() or "" for pagina in lector.pages)
        except Exception as exc:
            logger.warning("Error leyendo %s: %s", ruta_path.name, exc)
            continue
        for numero in numeros_oc:
            if numero in encontrados:
                continue
            if numero and numero in texto:
                encontrados[numero] = ruta_path
                break

    faltantes: list[str] = []
    subidos: list[str] = []
    ubicaciones: dict[str, str] = {}
    es_bienes = bool(getattr(config, "compra_bienes", False))

    for numero in numeros_oc:
        ruta_path = encontrados.get(numero)
        if not ruta_path:
            faltantes.append(numero)
            errores.append(
                f"OC {numero}: archivo no encontrado en carpeta de descarga"
            )
            continue

        proveedor = proveedores.get(numero)
        ruta_str = str(ruta_path)
        if not proveedor:
            proveedor = extraer_proveedor_desde_pdf(ruta_str)
            if indice_ordenes.get(numero) is not None and proveedor:
                indice_ordenes[numero]["proveedor"] = proveedor

        tarea = None
        if es_bienes:
            tarea = extraer_numero_tarea_desde_pdf(ruta_str)
            if indice_ordenes.get(numero) is not None:
                indice_ordenes[numero]["tarea"] = tarea

        extension = ruta_path.suffix or ".pdf"
        nombre_deseado = nombre_archivo_orden(numero, proveedor, extension)
        nombre_original = ruta_path.name
        origen_descarga = ruta_path.parent

        if es_bienes:
            base_bienes = getattr(config, "carpeta_analizar", None) or str(origen_descarga)
            if tarea:
                destino = None
                for raiz, carpetas, _ in os.walk(base_bienes):
                    for nombre_carpeta in carpetas:
                        if nombre_carpeta.startswith(tarea):
                            destino = os.path.join(raiz, nombre_carpeta)
                            break
                    if destino:
                        break
                if not destino:
                    destino = os.path.join(base_bienes, tarea)
                    os.makedirs(destino, exist_ok=True)
            else:
                destino = os.path.join(base_bienes, "ordenes sin tarea")
                os.makedirs(destino, exist_ok=True)

            destino_dir = Path(destino)
            destino_path, error_mov = _mover_archivo(
                ruta_path, destino_dir, nombre_original
            )
            if destino_path is None:
                errores.append(f"OC {numero}: {error_mov}")
                faltantes.append(numero)
                continue
            ruta_path = destino_path

            ruta_path, error_nombre = _asegurar_nombre(ruta_path, nombre_deseado)
            if ruta_path is None:
                errores.append(f"OC {numero}: {error_nombre}")
                faltantes.append(numero)
                try:
                    regreso = _resolver_conflicto(origen_descarga, nombre_original)
                    shutil.move(str(destino_path), regreso)
                except Exception as exc:  # pragma: no cover - recuperación de mejor esfuerzo
                    logger.warning(
                        "No se pudo regresar '%s' a '%s' tras un fallo de renombre: %s",
                        destino_path,
                        origen_descarga,
                        exc,
                    )
                continue

            logger.info("%s movido a %s", ruta_path.name, ruta_path.parent)
        else:
            destino_dir = _destino_no_bienes(config, indice_ordenes.get(numero))

            if destino_dir and destino_dir != ruta_path.parent:
                destino_dir.mkdir(parents=True, exist_ok=True)
                destino_path, error_mov = _mover_archivo(
                    ruta_path, destino_dir, nombre_deseado
                )
                if destino_path is None:
                    errores.append(f"OC {numero}: {error_mov}")
                    faltantes.append(numero)
                    continue
                ruta_path = destino_path
            else:
                ruta_path, error_nombre = _asegurar_nombre(ruta_path, nombre_deseado)
                if ruta_path is None:
                    errores.append(f"OC {numero}: {error_nombre}")
                    faltantes.append(numero)
                    continue

            logger.info("%s listo en %s", ruta_path.name, ruta_path.parent)

        subidos.append(numero)
        ubicaciones[numero] = str(ruta_path)

    return subidos, faltantes, errores, ubicaciones
