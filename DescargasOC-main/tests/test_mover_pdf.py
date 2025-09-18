import sys
import types
from types import SimpleNamespace

fake_pdf = types.ModuleType("PyPDF2")
fake_pdf.PdfReader = object
sys.modules.setdefault("PyPDF2", fake_pdf)

from descargas_oc import mover_pdf


def test_mover_oc_bienes_registra_error_si_no_se_mueve(tmp_path, monkeypatch):
    origen = tmp_path / "descargas"
    destino = tmp_path / "destino"
    origen.mkdir()
    destino.mkdir()

    pdf = origen / "123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    cfg = SimpleNamespace(
        compra_bienes=True,
        carpeta_destino_local=str(origen),
        carpeta_analizar=str(destino),
        abastecimiento_carpeta_descarga=str(origen),
    )

    monkeypatch.setattr(
        mover_pdf, "extraer_numero_tarea_desde_pdf", lambda ruta: "140144463"
    )
    monkeypatch.setattr(
        mover_pdf, "extraer_proveedor_desde_pdf", lambda ruta: "Proveedor X"
    )

    def failing_move(src, dst):
        raise PermissionError("sin permisos")

    monkeypatch.setattr(mover_pdf.shutil, "move", failing_move)

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == []
    assert faltantes == ["123456"]
    assert any("OC 123456" in msg for msg in errores)
    # el PDF debe permanecer en la carpeta de origen para reintentos
    assert any(item.suffix.lower() == ".pdf" for item in origen.iterdir())
