from gestorcompras.services import reassign_bridge


def _session():
    return {"address": "usuario@telconet.ec", "password": "secreto"}


def test_reassign_ok(monkeypatch):
    capturas = {}

    def _fake_batch(session, payloads, headless):
        capturas["session"] = session
        capturas["payloads"] = payloads
        capturas["headless"] = headless
        return [
            {
                "status": "ok",
                "details": payloads[0],
                "message_id": payloads[0].get("message_id"),
            }
        ]

    monkeypatch.setattr(reassign_bridge, "_run_selenium_batch", _fake_batch)

    resultado = reassign_bridge.reassign_by_task_number(
        "123",
        "Proveedor",
        "Mecánico",
        "0999",
        "OT",
        fuente="SERVICIOS",
        department="Compras",
        employee="jdoe",
        headless=False,
        comentario_template='Taller Asignado "{proveedor}"',
        email_session=_session(),
    )

    assert resultado["status"] == "ok"
    assert capturas["payloads"][0]["task_number"] == "123"
    assert capturas["payloads"][0]["department_override"] == "Compras"
    assert capturas["headless"] is False


def test_reassign_not_found(monkeypatch):
    def _fake_batch(_session, payloads, _headless):
        return [
            {
                "status": "not_found",
                "details": payloads[0],
                "message_id": payloads[0].get("message_id"),
                "error": "No se encontraron las tareas en la plataforma Telcos.\nTarea: 999",
            }
        ]

    monkeypatch.setattr(reassign_bridge, "_run_selenium_batch", _fake_batch)

    resultado = reassign_bridge.reassign_by_task_number(
        "999",
        "Prov",
        "Mec",
        "0",
        "OT",
        email_session=_session(),
    )

    assert resultado["status"] == "not_found"


def test_reassign_error(monkeypatch):
    def _fake_batch(_session, _payloads, _headless):
        raise Exception("Fallo inesperado")

    monkeypatch.setattr(reassign_bridge, "_run_selenium_batch", _fake_batch)

    resultado = reassign_bridge.reassign_by_task_number(
        "500",
        "Prov",
        "Mec",
        "0",
        "OT",
        email_session=_session(),
    )

    assert resultado["status"] == "error"


def test_reassign_tasks_batch_error(monkeypatch):
    def _fake_batch(_session, payloads, _headless):
        raise ValueError("Sin credenciales")

    monkeypatch.setattr(reassign_bridge, "_run_selenium_batch", _fake_batch)

    registros = [
        {
            "task_number": "111",
            "proveedor": "Proveedor",
            "mecanico": "Mec",
            "telefono": "0999",
            "inf_vehiculo": "OT",
            "message_id": "mid-1",
        }
    ]

    resultados = reassign_bridge.reassign_tasks(
        registros,
        fuente="SERVICIOS",
        department="Compras",
        employee="usuario",
        comentario_template="Taller Asignado \"{proveedor}\"",
        email_session=_session(),
    )

    assert resultados[0]["status"] == "error"
    assert resultados[0]["message_id"] == "mid-1"
