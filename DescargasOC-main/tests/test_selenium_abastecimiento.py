import importlib


def test_normalizar_fecha_formats():
    modulo = importlib.import_module("descargas_oc.selenium_abastecimiento")

    assert modulo._normalizar_fecha("01/02/25") == "01/02/2025"
    assert modulo._normalizar_fecha("2025-03-15") == "15/03/2025"
    assert modulo._normalizar_fecha("04/05/2026") == "04/05/2026"
    assert modulo._normalizar_fecha("") == ""
