from __future__ import annotations

import ast
from dataclasses import asdict
from pathlib import Path
import socket

import pytest

from gestorcompras.core.application import build_demo_services
from gestorcompras.core.config import DemoConfig
from gestorcompras.demo import fixtures


def test_startup_and_operations_work_without_internet(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("Una operación intentó usar la red.")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    services = build_demo_services(DemoConfig())

    message = services.mail.generate("demo@example.com", "OC-DEMO-001")
    reassignment = services.tasks.reassign("DEMO-0001", "DEMO-SUP-COSTA")
    download = services.storage.download("DOC-DEMO-001")

    assert message.status == "Simulado"
    assert reassignment.ok
    assert download.ok


def test_only_synthetic_fixtures_are_loaded() -> None:
    records = (*fixtures.suppliers(), *fixtures.tasks(), *fixtures.messages(), *fixtures.documents())
    serialized = " ".join(str(asdict(record)) for record in records)

    assert all("Demo" in supplier.name for supplier in fixtures.suppliers())
    assert all(email.endswith("@example.com") for email in (item.contact_email for item in fixtures.suppliers()))
    assert all(task.task_id.startswith("DEMO-") for task in fixtures.tasks())
    assert all(document.order_id.startswith("OC-DEMO-") for document in fixtures.documents())
    assert "0000000000000" in serialized


def test_public_package_has_no_external_connector_imports() -> None:
    package_root = Path(__file__).resolve().parents[1] / "gestorcompras"
    blocked_modules = {"socket", "smtplib", "poplib", "imaplib", "requests", "selenium"}
    imported: set[str] = set()
    for source_path in package_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(blocked_modules)


def test_demo_mode_cannot_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GESTORCOMPRAS_DEMO_MODE", "0")
    with pytest.raises(RuntimeError, match="demostración"):
        DemoConfig.from_environment()
