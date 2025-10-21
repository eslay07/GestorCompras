import sys
import types
from pathlib import Path
from types import SimpleNamespace

fake_pdf = types.ModuleType("PyPDF2")


class DummyReader:
    def __init__(self, _file):
        self.pages = []


fake_pdf.PdfReader = DummyReader
sys.modules.setdefault("PyPDF2", fake_pdf)

from descargas_oc import mover_pdf


def _config(tmp_path, bienes=True):
    origen = tmp_path / "descargas"
    destino = tmp_path / "destino"
    origen.mkdir()
    destino.mkdir()
    return (
        SimpleNamespace(
            compra_bienes=bienes,
            carpeta_destino_local=str(origen),
            carpeta_analizar=str(destino),
            abastecimiento_carpeta_descarga=str(origen),
        ),
        origen,
        destino,
    )


def _listar_pdfs(carpeta: Path) -> list[Path]:
    """Devuelve los PDFs de ``carpeta`` ignorando diferencias de mayúsculas."""

    encontrados: list[Path] = []
    vistos: set[Path] = set()
    for patron in ("*.pdf", "*.PDF"):
        for item in carpeta.glob(patron):
            if item not in vistos:
                vistos.add(item)
                encontrados.append(item)
    return encontrados


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
    monkeypatch.setattr(mover_pdf.shutil, "copy2", failing_move)

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == []
    assert faltantes == ["123456"]
    assert any("OC 123456" in msg for msg in errores)
    # el PDF debe permanecer en la carpeta de origen para reintentos
    assert bool(_listar_pdfs(origen))


def test_mover_oc_bienes_copia_si_move_falla(tmp_path, monkeypatch):
    cfg, origen, destino = _config(tmp_path)
    carpeta_tarea = destino / "140144463"
    carpeta_tarea.mkdir()

    pdf = origen / "123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        mover_pdf, "extraer_numero_tarea_desde_pdf", lambda ruta: "140144463"
    )
    monkeypatch.setattr(
        mover_pdf, "extraer_proveedor_desde_pdf", lambda ruta: "Proveedor X"
    )

    def failing_move(_src, _dst):
        raise PermissionError("sin permisos")

    monkeypatch.setattr(mover_pdf.shutil, "move", failing_move)

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == ["123456"]
    assert faltantes == []
    assert errores == []
    archivos = _listar_pdfs(carpeta_tarea)
    assert len(archivos) == 1
    assert archivos[0].name.startswith("ORDEN 123456")
    assert not _listar_pdfs(origen)


def test_mover_oc_reporta_error_si_no_puede_renombrar(tmp_path, monkeypatch):
    cfg, origen, _destino = _config(tmp_path)

    pdf = origen / "123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        mover_pdf, "extraer_proveedor_desde_pdf", lambda ruta: "Proveedor X"
    )

    def failing_rename(self, target):
        raise PermissionError("bloqueado")

    monkeypatch.setattr(mover_pdf.Path, "rename", failing_rename)

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == []
    assert faltantes == ["123456"]
    assert any("renombrar" in err for err in errores)
    assert any(p.name == "123456.pdf" for p in origen.iterdir())


def test_mover_oc_bienes_mueve_a_carpeta_existente(tmp_path, monkeypatch):
    cfg, origen, destino = _config(tmp_path)
    carpeta_tarea = destino / "140144463 - carpeta"
    carpeta_tarea.mkdir()

    pdf = origen / "123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        mover_pdf, "extraer_numero_tarea_desde_pdf", lambda ruta: "140144463"
    )
    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == ["123456"]
    assert faltantes == []
    assert errores == []
    archivos = _listar_pdfs(carpeta_tarea)
    assert len(archivos) == 1
    assert "PROVEEDOR_X" in archivos[0].stem
    assert "ORDEN 123456" in archivos[0].stem
    assert not _listar_pdfs(origen)


def test_mover_oc_bienes_resuelve_conflictos(tmp_path, monkeypatch):
    cfg, origen, destino = _config(tmp_path)
    monkeypatch.setattr(
        mover_pdf, "extraer_numero_tarea_desde_pdf", lambda ruta: "140144463"
    )

    carpeta_tarea = destino / "140144463"
    carpeta_tarea.mkdir()
    conflicto = carpeta_tarea / "ORDEN 123456 - PROVEEDOR_X.PDF"
    conflicto.write_text("existing")

    pdf = origen / "123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == ["123456"]
    assert faltantes == []
    assert errores == []
    archivos = sorted(_listar_pdfs(carpeta_tarea))
    assert len(archivos) == 2
    nombres = [p.name for p in archivos]
    assert any(name.lower().endswith("(1).pdf") for name in nombres)


def test_mover_oc_no_bienes_identifica_numero_en_nombre(tmp_path):
    cfg, origen, destino = _config(tmp_path, bienes=False)

    pdf = origen / "ORDEN # 123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": "Proveedor X"}]
    )

    assert subidos == ["123456"]
    assert faltantes == []
    assert errores == []
    archivos = _listar_pdfs(destino)
    assert len(archivos) == 1
    assert archivos[0].name == "ORDEN 123456 - PROVEEDOR_X.PDF"
    assert not _listar_pdfs(origen)


def test_mover_oc_no_bienes_renombra_en_origen_si_no_hay_destino(tmp_path):
    cfg, origen, destino = _config(tmp_path, bienes=False)
    cfg.carpeta_analizar = str(origen)

    pdf = origen / "ORDEN # 654321.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "654321", "proveedor": "Proveedor Y"}]
    )

    assert subidos == ["654321"]
    assert faltantes == []
    assert errores == []
    archivos = _listar_pdfs(origen)
    assert len(archivos) == 1
    assert archivos[0].name == "ORDEN 654321 - PROVEEDOR_Y.PDF"


def test_mover_oc_no_bienes_registra_error_si_no_puede_mover(tmp_path, monkeypatch):
    cfg, origen, destino = _config(tmp_path, bienes=False)

    pdf = origen / "ORDEN # 999999.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(
        mover_pdf,
        "_mover_archivo",
        lambda ruta, dest, nombre: (None, "fallo de movimiento"),
    )

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "999999", "proveedor": "Proveedor Z"}]
    )

    assert subidos == []
    assert faltantes == ["999999"]
    assert any("fallo de movimiento" in err for err in errores)
    assert (origen / "ORDEN # 999999.pdf").exists()


def test_mover_oc_no_bienes_registra_error_si_no_puede_renombrar(tmp_path, monkeypatch):
    cfg, origen, _destino = _config(tmp_path, bienes=False)
    cfg.carpeta_analizar = str(origen)

    pdf = origen / "ORDEN # 777777.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def failing_rename(self, target):  # pragma: no cover - comportamiento forzado
        raise PermissionError("bloqueado")

    monkeypatch.setattr(mover_pdf.Path, "rename", failing_rename)

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "777777", "proveedor": "Proveedor W"}]
    )

    assert subidos == []
    assert faltantes == ["777777"]
    assert any("renombrar" in err for err in errores)
    assert any(p.name == "ORDEN # 777777.pdf" for p in origen.iterdir())


def test_mover_oc_abastecimiento_permanecen_en_descarga(tmp_path):
    origen_normal = tmp_path / "descargas_normales"
    origen_abas = tmp_path / "descargas_abastecimiento"
    destino_general = tmp_path / "destino_general"

    origen_normal.mkdir()
    origen_abas.mkdir()
    destino_general.mkdir()

    cfg = SimpleNamespace(
        compra_bienes=False,
        carpeta_destino_local=str(origen_normal),
        carpeta_analizar=str(destino_general),
        abastecimiento_carpeta_descarga=str(origen_abas),
    )

    pdf = origen_abas / "ORDEN # 555555.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    orden = {
        "numero": "555555",
        "proveedor": "Proveedor Uno",
        "categoria": "abastecimiento",
    }

    subidos, faltantes, errores = mover_pdf.mover_oc(cfg, [orden])

    assert subidos == ["555555"]
    assert faltantes == []
    assert errores == []

    archivos_abas = _listar_pdfs(origen_abas)
    assert len(archivos_abas) == 1
    assert archivos_abas[0].name.startswith("ORDEN 555555 - PROVEEDOR_UNO")
    # no se debe mover a la carpeta general
    assert not _listar_pdfs(destino_general)
def test_mover_oc_no_bienes_identifica_numero_en_nombre(tmp_path, monkeypatch):
    cfg, origen, _destino = _config(tmp_path, bienes=False)

    pdf = origen / "ORDEN # 123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(mover_pdf, "extraer_proveedor_desde_pdf", lambda ruta: None)

    subidos, faltantes, errores = mover_pdf.mover_oc(
        cfg, [{"numero": "123456", "proveedor": None}]
    )

    assert subidos == ["123456"]
    assert faltantes == []
    assert errores == []
