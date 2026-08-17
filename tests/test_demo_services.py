from __future__ import annotations

from pathlib import Path

import pytest

from gestorcompras.services.demo_mail import DemoMailService
from gestorcompras.services.demo_storage import DemoStorageService
from gestorcompras.services.demo_tasks import DemoTaskService


def test_simulated_mail_is_generated_in_memory() -> None:
    service = DemoMailService()
    before = service.generated_count
    message = service.generate("demo@example.com", "OC-DEMO-001")

    assert service.generated_count == before + 1
    assert message.recipient == "demo@example.com"
    assert message.message_id.startswith("MSG-DEMO-")


def test_mail_rejects_non_synthetic_recipient() -> None:
    service = DemoMailService()
    domain = "invalid" + ".test"
    with pytest.raises(ValueError, match="example.com"):
        service.generate("person@" + domain, "OC-DEMO-001")


def test_reassignment_changes_only_volatile_state() -> None:
    service = DemoTaskService()
    result = service.reassign("DEMO-0001", "DEMO-SUP-COSTA")
    updated = next(item for item in service.list_tasks() if item.task_id == "DEMO-0001")

    assert result.ok
    assert updated.supplier_id == "DEMO-SUP-COSTA"
    assert updated.status == "Reasignada en demo"


def test_task_update_is_simulated() -> None:
    service = DemoTaskService()
    result = service.update("DEMO-0002")
    updated = next(item for item in service.list_tasks() if item.task_id == "DEMO-0002")

    assert result.ok
    assert updated.status == "Actualizada en demo"


def test_download_does_not_create_files(tmp_path: Path) -> None:
    service = DemoStorageService(output_path=r"C:\Demo\GestorCompras\pdfs")
    before = tuple(tmp_path.iterdir())
    result = service.download("DOC-DEMO-001")
    after = tuple(tmp_path.iterdir())

    assert result.ok
    assert before == after == ()
    assert result.reference.endswith("OC-DEMO-001.pdf")
