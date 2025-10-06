import importlib

def test_limpiar_proveedor_elimina_prefijo():
    modulo = importlib.import_module("descargas_oc.pdf_info")

    assert modulo.limpiar_proveedor("Nombre: 004465 - Proveedor") == "004465 - Proveedor"
    assert modulo.limpiar_proveedor("nombre-004465 - Otro") == "004465 - Otro"
    assert modulo.limpiar_proveedor(None) == ""


def test_actualizar_proveedores_desde_pdfs(tmp_path, monkeypatch):
    modulo = importlib.import_module("descargas_oc.pdf_info")

    carpeta = tmp_path / "descargas"
    carpeta.mkdir()
    pdf = carpeta / "ORDEN # 123456.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    ordenes = [{"numero": "123456", "proveedor": ""}]

    monkeypatch.setattr(
        modulo, "extraer_proveedor_desde_pdf", lambda ruta: "Nombre: 004465 - PROVEEDOR"
    )

    actualizados = modulo.actualizar_proveedores_desde_pdfs(ordenes, carpeta)

    assert actualizados == {"123456": "004465 - PROVEEDOR"}
    assert ordenes[0]["proveedor"] == "004465 - PROVEEDOR"


def test_nombre_archivo_orden_formatea_y_respeta_extension():
    modulo = importlib.import_module("descargas_oc.pdf_info")

    nombre = modulo.nombre_archivo_orden("123456", "Proveedor / Test", "pdf")
    assert nombre == "123456 - PROVEEDOR_TEST.PDF"

    nombre_sin_datos = modulo.nombre_archivo_orden(None, None, None)
    assert nombre_sin_datos == "ARCHIVO.PDF"


def test_proveedor_desde_pdf_normaliza(monkeypatch):
    modulo = importlib.import_module("descargas_oc.pdf_info")

    monkeypatch.setattr(
        modulo, "extraer_proveedor_desde_pdf", lambda ruta: "Nombre: 001 - TEST"
    )

    proveedor = modulo.proveedor_desde_pdf("dummy.pdf")
    assert proveedor == "001 - TEST"
