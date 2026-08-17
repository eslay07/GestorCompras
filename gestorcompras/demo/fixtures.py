"""Datos pequeños, deterministas y totalmente sintéticos."""

from __future__ import annotations

from gestorcompras.core.models import DemoDocument, DemoMessage, PurchaseTask, Supplier

DEMO_OUTPUT_PATH = r"C:\Demo\GestorCompras\pdfs"


def suppliers() -> tuple[Supplier, ...]:
    return (
        Supplier(
            supplier_id="DEMO-SUP-ANDINO",
            name="Proveedor Andino Demo",
            contact_email="andino@example.com",
        ),
        Supplier(
            supplier_id="DEMO-SUP-COSTA",
            name="Proveedor Costa Demo",
            contact_email="costa@example.com",
        ),
    )


def tasks() -> tuple[PurchaseTask, ...]:
    return (
        PurchaseTask(
            task_id="DEMO-0001",
            order_id="OC-DEMO-001",
            summary="Validar solicitud demostrativa",
            supplier_id="DEMO-SUP-ANDINO",
            owner="Usuario Demo",
            status="Lista para demo",
        ),
        PurchaseTask(
            task_id="DEMO-0002",
            order_id="OC-DEMO-002",
            summary="Preparar confirmación sintética",
            supplier_id="DEMO-SUP-COSTA",
            owner="Usuario Demo",
            status="Pendiente en demo",
        ),
        PurchaseTask(
            task_id="DEMO-0003",
            order_id="OC-DEMO-003",
            summary="Revisar documento ficticio",
            supplier_id="DEMO-SUP-ANDINO",
            owner="Usuario Demo",
            status="Lista para demo",
        ),
    )


def messages() -> tuple[DemoMessage, ...]:
    return (
        DemoMessage(
            message_id="MSG-DEMO-001",
            recipient="andino@example.com",
            subject="Vista previa de OC-DEMO-001",
            preview="Confirmación sintética para una orden demostrativa.",
            status="Borrador local",
        ),
        DemoMessage(
            message_id="MSG-DEMO-002",
            recipient="costa@example.com",
            subject="Vista previa de OC-DEMO-002",
            preview="Notificación creada únicamente para la demostración.",
            status="Simulado",
        ),
    )


def documents() -> tuple[DemoDocument, ...]:
    return (
        DemoDocument(
            document_id="DOC-DEMO-001",
            order_id="OC-DEMO-001",
            filename="OC-DEMO-001.pdf",
            supplier_name="Proveedor Andino Demo",
            status="Disponible en memoria",
        ),
        DemoDocument(
            document_id="DOC-DEMO-002",
            order_id="OC-DEMO-002",
            filename="OC-DEMO-002.pdf",
            supplier_name="Proveedor Costa Demo",
            status="Disponible en memoria",
        ),
        DemoDocument(
            document_id="DOC-DEMO-003",
            order_id="OC-DEMO-003",
            filename="OC-DEMO-003.pdf",
            supplier_name="Proveedor Andino Demo",
            status="Disponible en memoria",
        ),
    )


def workflow_steps() -> tuple[str, ...]:
    return (
        "Validar los datos sintéticos",
        "Preparar una vista previa local",
        "Registrar el resultado en memoria",
    )
