import pytest

from gestorcompras.modules.reasignacion_gui import ServiciosReasignacion


def test_normaliza_busqueda_sin_acentos():
    normalizado = ServiciosReasignacion._normalize_for_search("Notificación a Proveedor: Tarea")
    assert "NOTIFICACION A PROVEEDOR" in normalizado


@pytest.mark.parametrize(
    "subject",
    [
        "Notificación a Proveedor: aviso",
        "notificacion a proveedor: actualización",
        "Aviso NOTIFICACIÓN A PROVEEDOR: detalle",
    ],
)
def test_subcadena_detectada(subject):
    patron = ServiciosReasignacion._normalize_for_search("NOTIFICACION A PROVEEDOR:")
    sujeto = ServiciosReasignacion._normalize_for_search(subject)
    assert patron in sujeto
