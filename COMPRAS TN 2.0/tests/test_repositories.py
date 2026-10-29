from __future__ import annotations

from compras_tn.domain.models import (
    Assignment,
    EmailTemplate,
    FlowStep,
    ItemStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    PurchaseMode,
    Supplier,
    TaskRecord,
    WorkflowDefinition,
)
from compras_tn.infrastructure.db import Repositories


def test_catalog_crud_and_natural_keys(repositories: Repositories) -> None:
    first = repositories.save(
        Supplier(
            name="Uno",
            nickname="Proveedor Uno",
            nickname_2="P1",
            nickname_3="Primer Proveedor",
            ruc="001",
            email_primary="uno@example.com",
        )
    )
    updated = repositories.save(
        Supplier(
            name="Uno actualizado",
            nickname="Proveedor Uno",
            nickname_2="P1",
            nickname_3="Primer Proveedor",
            ruc="001",
            email_primary="nuevo@example.com",
        )
    )
    assert updated.id == first.id
    assert repositories.find_by_ruc("001").name == "Uno actualizado"
    assert repositories.find_by_nickname("proveedor uno").ruc == "001"
    assert repositories.find_by_nickname("p1").ruc == "001"
    assert repositories.find_by_nickname("PRIMER PROVEEDOR").ruc == "001"
    assert repositories.list("nuevo@example.com")[0].ruc == "001"
    assert repositories.list("PROVEEDOR UNO")[0].ruc == "001"
    assert repositories.list("primer proveedor")[0].ruc == "001"

    repositories.save_assignment(Assignment(subdepartment="SUB", department="DEP", person="Ana"))
    assert repositories.list_assignments()[0].person == "Ana"

    template = repositories.save_template(EmailTemplate(name="Aviso", html="<p>Hola</p>"))
    assert template.id is not None
    assert repositories.list_templates()[0].html == "<p>Hola</p>"

    flow = repositories.save_workflow(
        WorkflowDefinition(
            name="Flujo",
            mode=PurchaseMode.BIENES,
            steps=[FlowStep(action_id="consultar")],
        )
    )
    assert repositories.list_workflows("bienes")[0].id == flow.id


def test_supplier_nicknames_must_be_unique_across_all_three_fields(
    repositories: Repositories,
) -> None:
    repositories.save(
        Supplier(
            name="Uno",
            nickname_2="ALIAS COMPARTIDO",
            ruc="001",
            email_primary="uno@example.com",
        )
    )

    try:
        repositories.save(
            Supplier(
                name="Dos",
                nickname_3="alias compartido",
                ruc="002",
                email_primary="dos@example.com",
            )
        )
    except ValueError as exc:
        assert "sobrenombres" in str(exc)
    else:
        raise AssertionError("Se permitió repetir un sobrenombre entre proveedores.")


def test_settings_and_task_inbox_are_typed_and_idempotent(repositories: Repositories) -> None:
    repositories.set("downloads", "options", {"enabled": True, "values": [1, 2]})
    assert repositories.get("downloads", "options")["values"] == [1, 2]
    task = TaskRecord(task_number="00123", origin="manual", purchase_mode=PurchaseMode.SERVICIOS)
    assert repositories.enqueue([task, task]) == 1
    assert repositories.list_pending()[0].task_number == "00123"
    repositories.consume(["00123"])
    assert repositories.list_pending() == []


def test_operation_audit_persists_item_results(repositories: Repositories) -> None:
    request = OperationRequest(kind="prueba", mode=PurchaseMode.BIENES, items=[{"id": 1}])
    run_id = repositories.start(request)
    repositories.finish(
        run_id,
        OperationResult.from_items(
            [OperationItem(key="1", status=ItemStatus.SUCCEEDED, message="ok")]
        ),
    )
    assert run_id > 0
