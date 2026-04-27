import pytest

from gestorcompras.services.credentials import resolve_telcos_credentials


def test_resolve_telcos_credentials_from_address_normalizes_user():
    username, password = resolve_telcos_credentials(
        {"address": "Usuario.Test@telconet.ec", "password": "clave123"}
    )

    assert username == "USUARIO.TEST"
    assert password == "clave123"


def test_resolve_telcos_credentials_accepts_user_aliases():
    username, password = resolve_telcos_credentials(
        {"user": "agente@dominio.com", "pass": "123"}
    )

    assert username == "AGENTE"
    assert password == "123"


@pytest.mark.parametrize(
    "session, expected",
    [
        (None, "Credenciales de Telcos incompletas: no existe sesión activa."),
        ({"address": ""}, "Credenciales de Telcos incompletas: falta el usuario."),
        ({"address": "usuario@dominio.com"}, "Credenciales de Telcos incompletas: falta la contraseña."),
    ],
)
def test_resolve_telcos_credentials_uniform_errors(session, expected):
    with pytest.raises(ValueError) as exc_info:
        resolve_telcos_credentials(session)

    assert str(exc_info.value) == expected
