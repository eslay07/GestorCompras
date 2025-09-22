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
        == "123456 - Proveedor S_A"
    )
    assert (
        modulo._nombre_archivo("", "Proveedor Especial")
        == "Proveedor Especial"
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
