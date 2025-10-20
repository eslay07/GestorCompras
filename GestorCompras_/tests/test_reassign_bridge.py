import pytest

from gestorcompras.services import reassign_bridge


def test_reassign_ok(monkeypatch):
    monkeypatch.setattr(reassign_bridge.db, "get_tasks_temp", lambda: [{"task_number": "123", "reasignacion": "Compras"}])
    result = reassign_bridge.reassign_by_task_number("123", "Proveedor", "Mecánico", "0999", "OT", "SERVICIOS")
    assert result["status"] == "ok"
    assert result["details"]["task_number"] == "123"


def test_reassign_not_found(monkeypatch):
    monkeypatch.setattr(reassign_bridge.db, "get_tasks_temp", lambda: [])
    result = reassign_bridge.reassign_by_task_number("999", "Prov", "Mec", "0", "OT", "SERVICIOS")
    assert result["status"] == "not_found"


def test_reassign_error(monkeypatch):
    monkeypatch.setattr(reassign_bridge, "_find_legacy_task", lambda task: object())
    result = reassign_bridge.reassign_by_task_number("500", "Prov", "Mec", "0", "OT", "SERVICIOS")
    assert result["status"] == "error"
