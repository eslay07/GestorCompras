import pytest

from gestorcompras.services import reassign_bridge


def _session():
    return {"address": "usuario@telconet.ec", "password": "secreto"}


def test_reassign_ok(monkeypatch):
    captured = {}

    def fake_run(session, payload, headless):
        captured["session"] = session
        captured["payload"] = payload
        captured["headless"] = headless
        return {"status": "ok", "details": payload}

    monkeypatch.setattr(reassign_bridge, "_run_selenium_reassign", fake_run)

    result = reassign_bridge.reassign_by_task_number(
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

    assert result["status"] == "ok"
    assert captured["payload"]["task_number"] == "123"
    assert captured["payload"]["department_override"] == "Compras"
    assert captured["headless"] is False


def test_reassign_not_found(monkeypatch):
    def fake_run(session, payload, headless):
        raise Exception("No se encontraron las tareas en la plataforma Telcos.\nTarea: 999")

    monkeypatch.setattr(reassign_bridge, "_run_selenium_reassign", fake_run)

    result = reassign_bridge.reassign_by_task_number(
        "999",
        "Prov",
        "Mec",
        "0",
        "OT",
        email_session=_session(),
    )

    assert result["status"] == "not_found"


def test_reassign_error(monkeypatch):
    def fake_run(session, payload, headless):
        raise Exception("Fallo inesperado")

    monkeypatch.setattr(reassign_bridge, "_run_selenium_reassign", fake_run)

    result = reassign_bridge.reassign_by_task_number(
        "500",
        "Prov",
        "Mec",
        "0",
        "OT",
        email_session=_session(),
    )

    assert result["status"] == "error"
