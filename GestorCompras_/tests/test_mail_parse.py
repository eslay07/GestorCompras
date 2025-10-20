import pytest

from gestorcompras.core.mail_parse import parse_body, parse_subject


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("NOTIFICACION A PROVEEDOR: TAREA: \"142959682\"", "142959682"),
        ("Aviso - TAREA:\"123456\"", "123456"),
        ("TAREA: 987654321 - actualización", "987654321"),
        ("Sin número", "N/D"),
    ],
)
def test_parse_subject(subject, expected):
    assert parse_subject(subject)["task_number"] == expected


@pytest.mark.parametrize(
    "body,correo,expect_found",
    [
        (
            "Estimados \"Proveedor Uno\"\ncoordinando el mantenimiento con \"Juan Perez (0999999999)\".\n\"OT-12345\"",
            "user@telconet.ec",
            False,
        ),
        (
            "Estimados \"Proveedor Dos\" correo user@telconet.ec\ncoordinando el mantenimiento con \"María López (09-888-7777)\"\n\"OT 98765\"",
            "user@telconet.ec",
            True,
        ),
        (
            "Estimados \"Proveedor Tres\"\ncoordinando el mantenimiento con \"Carlos Gómez (593-2-123456)\"\n\"OT 222\"",
            "otro@telconet.ec",
            False,
        ),
    ],
)
def test_parse_body_identifica_correo(body, correo, expect_found):
    parsed = parse_body(body, correo)
    assert parsed["correo_usuario_encontrado"] is expect_found


@pytest.mark.parametrize(
    "body,expected_tel",
    [
        ("coordinando el mantenimiento con \"Nombre (09-999-8888)\".", "099998888"),
        ("coordinando el mantenimiento con \"Nombre (593099998888)\".", "593099998888"),
        ("coordinando el mantenimiento con \"Nombre (09 999 8888)\".", "099998888"),
    ],
)
def test_parse_body_normaliza_telefono(body, expected_tel):
    parsed = parse_body(body, "user@telconet.ec")
    assert parsed["mecanico_telefono"] == expected_tel


def test_parse_body_mojibake_y_comillas_tipograficas():
    cuerpo = (
        "Estimados “ProveedÃ³r Ñandú”\n"
        "coordinando el mantenimiento con “Mecánico (09 111 2222)”\n"
        "“OT para revisión” user@telconet.ec"
    )
    parsed = parse_body(cuerpo, "user@telconet.ec")
    assert parsed["proveedor"] == "Proveedór Ñandú"
    assert parsed["mecanico_nombre"] == "Mecánico"
    assert parsed["mecanico_telefono"] == "091112222"
    assert parsed["inf_vehiculo"].startswith("OT")
    assert parsed["correo_usuario_encontrado"] is True


def test_parse_body_valores_por_defecto():
    parsed = parse_body("Sin coincidencias", "user@telconet.ec")
    assert parsed["proveedor"] == "N/D"
    assert parsed["mecanico_nombre"] == "N/D"
    assert parsed["mecanico_telefono"] == "N/D"
    assert parsed["inf_vehiculo"] == "N/D"


def test_parse_body_formato_servicios():
    cuerpo = (
        "Estimados MAVESA QUITO\n"
        "Su ayuda coordinando el mantenimiento con Miguel García (093-558-7896)\n"
        "[GTI-1566] [107082] OT MG-3363 MANT, GREAT WALL 335 GTI-1566 KM 107082\n"
        "Agradezco su atención\n"
        "Sistema Compras - Alex Cárdenas\n"
        "AVISO IMPORTANTE: Dirija cualquier consulta a acardenas@telconet.ec\n"
    )
    parsed = parse_body(cuerpo, "acardenas@telconet.ec")
    assert parsed["proveedor"] == "MAVESA QUITO"
    assert parsed["mecanico_nombre"] == "Miguel García"
    assert parsed["mecanico_telefono"] == "0935587896"
    assert "OT" in parsed["inf_vehiculo"]
    assert parsed["correo_usuario_encontrado"] is True
