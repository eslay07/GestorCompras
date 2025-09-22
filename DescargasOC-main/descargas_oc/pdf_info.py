"""Herramientas para extraer metadatos de las órdenes descargadas."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Mapping

try:  # pragma: no cover - soporte ejecución directa
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from logger import get_logger

try:  # pragma: no cover - ejecución directa
    from .organizador_bienes import extraer_proveedor_desde_pdf
except ImportError:  # pragma: no cover
    from organizador_bienes import extraer_proveedor_desde_pdf


logger = get_logger(__name__)

MAX_NOMBRE_ARCHIVO = 180

def limpiar_proveedor(valor: str | None) -> str:
    """Normaliza el texto obtenido desde el PDF."""

    if not valor:
        return ""
    texto = re.sub(r"(?i)^nombre\s*[:\-]?\s*", "", valor)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def nombre_archivo_orden(
    numero: str | None,
    proveedor: str | None,
    extension: str | None = ".pdf",
) -> str:
    """Genera un nombre de archivo seguro usando número y proveedor."""

    numero = (numero or "").strip()
    base = numero
    if proveedor:
        prov_clean = re.sub(r"[^\w\- ]", "_", proveedor)
        prov_clean = re.sub(r"\s+", " ", prov_clean).strip()
        base = f"{base} - {prov_clean}" if base else prov_clean
    base = re.sub(r"\s+", " ", base).strip()
    if not base:
        base = "archivo"
    if len(base) > MAX_NOMBRE_ARCHIVO:
        base = base[:MAX_NOMBRE_ARCHIVO].rstrip(" .-_") or "archivo"
    if not extension:
        extension = ".pdf"
    if not extension.startswith("."):
        extension = f".{extension}"
    return f"{base}{extension}"


def proveedor_desde_pdf(ruta_pdf: str | Path | None) -> str:
    """Obtiene y normaliza el proveedor leyendo el PDF indicado."""

    if not ruta_pdf:
        return ""
    try:
        proveedor = extraer_proveedor_desde_pdf(str(ruta_pdf))
    except Exception as exc:  # pragma: no cover - defensivo
        logger.debug("No se pudo extraer proveedor de %s: %s", ruta_pdf, exc)
        return ""
    return limpiar_proveedor(proveedor)


def _buscar_numero_en_nombre(nombre: str, numeros: Iterable[str]) -> str | None:
    for numero in numeros:
        if not numero:
            continue
        if re.search(rf"(?<!\\d){re.escape(numero)}(?!\\d)", nombre):
            return numero
    return None


def actualizar_proveedores_desde_pdfs(
    ordenes: Iterable[Mapping[str, object]] | None,
    carpeta_descargas: str | Path | None,
) -> dict[str, str]:
    """Actualiza la información de proveedor leyendo cada PDF descargado.

    Devuelve un diccionario con los números de OC cuyo proveedor fue
    encontrado en el contenido del PDF.
    """

    if not ordenes or not carpeta_descargas:
        return {}

    carpeta = Path(carpeta_descargas)
    if not carpeta.exists():
        logger.debug("Carpeta de descargas inexistente: %s", carpeta)
        return {}

    ordenes_dict = {
        str(o.get("numero")).strip(): o
        for o in ordenes
        if o and o.get("numero")
    }
    if not ordenes_dict:
        return {}

    pdfs = sorted(carpeta.glob("*.pdf"))
    if not pdfs:
        logger.debug("No se encontraron PDFs en %s", carpeta)
        return {}

    actualizados: dict[str, str] = {}
    for pdf in pdfs:
        numero = _buscar_numero_en_nombre(pdf.name, ordenes_dict.keys())
        if not numero:
            continue
        proveedor = limpiar_proveedor(extraer_proveedor_desde_pdf(str(pdf)))
        if not proveedor:
            continue
        orden = ordenes_dict.get(numero)
        if isinstance(orden, dict):
            orden["proveedor"] = proveedor
        actualizados[numero] = proveedor
        logger.debug("OC %s: proveedor '%s' leído desde %s", numero, proveedor, pdf)

    return actualizados
