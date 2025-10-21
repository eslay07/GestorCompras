from datetime import datetime

from gestorcompras.services import reassign_reporter


def test_enviar_reporte_envia_con_filas(monkeypatch):
    capturas = {}

    def _fake_send(session, subject, template, context, **kwargs):
        capturas["session"] = session
        capturas["subject"] = subject
        capturas["context"] = context

    monkeypatch.setattr(reassign_reporter, "send_email_custom", _fake_send)

    email_session = {"address": "usuario@telconet.ec", "password": "secreto"}
    filas = [
        {
            "fecha": datetime(2024, 5, 1, 8, 30),
            "task_number": "123456",
            "taller": "Proveedor",
            "asunto": "Aviso",
        }
    ]

    resultado = reassign_reporter.enviar_reporte_servicios(email_session, "dest@telconet.ec", filas, [])

    assert resultado is True
    assert capturas["subject"] == "Reporte de tareas reasignadas"
    assert capturas["context"]["filas_ok"][0]["task_number"] == "123456"


def test_enviar_reporte_sin_datos(monkeypatch):
    enviado = reassign_reporter.enviar_reporte_servicios(
        {"address": "usuario@telconet.ec", "password": "secreto"},
        "dest@telconet.ec",
        [],
        [],
    )

    assert enviado is False
