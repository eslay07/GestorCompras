import importlib


def test_normalizar_fecha_formats():
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    assert modulo._normalizar_fecha("01/02/25") == "01/02/2025"
    assert modulo._normalizar_fecha("2025-03-15") == "15/03/2025"
    assert modulo._normalizar_fecha("04/05/2026") == "04/05/2026"
    assert modulo._normalizar_fecha("") == ""


def test_nombre_archivo_normaliza_datos():
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    assert (
        modulo._nombre_archivo("123456", "Proveedor S.A.")
        == "123456 - PROVEEDOR S_A"
    )
    assert (
        modulo._nombre_archivo("", "Proveedor Especial")
        == "PROVEEDOR ESPECIAL"
    )
    assert modulo._nombre_archivo(None, None) is None


def test_extraer_variantes_y_consultas_prioriza_numeros():
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    variantes = modulo._extraer_variantes("00123 - SOLICITANTE;Otro Valor")
    assert variantes == ["00123 - SOLICITANTE", "Otro Valor"]

    consultas = modulo._construir_consultas(variantes, "00123 - SOLICITANTE")
    assert consultas[0] == "00123"
    assert "00123 - SOLICITANTE" in consultas
    assert "Otro Valor" in consultas


def test_valor_coincide_detecta_nombre_y_codigo():
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    variantes = modulo._extraer_variantes("00045 - APROV")
    consultas = modulo._construir_consultas(variantes, "00045 - APROV")

    assert modulo._valor_coincide("00045 - APROV TEST", variantes, consultas)
    assert modulo._valor_coincide("Código 00045", variantes, consultas)
    assert not modulo._valor_coincide("Sin coincidencia", variantes, consultas)


def test_numero_desde_texto_identifica_oc():
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    assert modulo._numero_desde_texto("ORDEN # 342050") == "342050"
    assert modulo._numero_desde_texto("OC 00342059") == "342059"
    assert modulo._numero_desde_texto("keyboard_arrow_down") == ""


def test_renombrar_pdf_respeta_nombre_original(tmp_path):
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    pdf = tmp_path / "ORDEN # 342050.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    renombrado = modulo._renombrar_pdf_descargado(pdf, "342050", "Electroleg S.A.")

    assert renombrado.name.startswith("ORDEN #342050 - ELECTROLEG_S_A_")
    assert renombrado.suffix == ".PDF"
