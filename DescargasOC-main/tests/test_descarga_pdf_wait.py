"""Pruebas para la espera de descargas de PDF."""

from __future__ import annotations

import sys
import threading
import time
import types
from pathlib import Path

import pytest

fake_pdf = types.ModuleType("PyPDF2")
fake_pdf.PdfReader = object  # tipo mínimo para importar el módulo
sys.modules.setdefault("PyPDF2", fake_pdf)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from descargas_oc import selenium_modulo


def test_esperar_descarga_pdf_detecta_nuevo_archivo(tmp_path):
    existentes: dict = {}

    def crear_archivo():
        time.sleep(0.2)
        (tmp_path / "nuevo.pdf").write_bytes(b"contenido")

    hilo = threading.Thread(target=crear_archivo)
    hilo.start()
    try:
        archivo = selenium_modulo.esperar_descarga_pdf(
            tmp_path, existentes, timeout=3, intervalo=0.1
        )
    finally:
        hilo.join()

    assert archivo.name == "nuevo.pdf"


def test_esperar_descarga_pdf_detecta_sobrescritura(tmp_path):
    destino = tmp_path / "oc.pdf"
    destino.write_bytes(b"old")
    existentes = {destino: destino.stat().st_mtime}

    def reescribir_archivo():
        time.sleep(0.2)
        destino.write_bytes(b"nuevo contenido")

    hilo = threading.Thread(target=reescribir_archivo)
    hilo.start()
    try:
        archivo = selenium_modulo.esperar_descarga_pdf(
            tmp_path, existentes, timeout=3, intervalo=0.1
        )
    finally:
        hilo.join()

    assert archivo == destino


def test_esperar_descarga_pdf_timeout(tmp_path):
    with pytest.raises(RuntimeError):
        selenium_modulo.esperar_descarga_pdf(tmp_path, {}, timeout=0.3, intervalo=0.1)
