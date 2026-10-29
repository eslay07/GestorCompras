from __future__ import annotations

import os
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from compras_tn.domain.models import EmailTemplate, Supplier
from compras_tn.infrastructure.orders import OrderFileService, extract_task_numbers
from compras_tn.infrastructure.templates import JinjaTemplateRenderer


class Settings:
    def __init__(self, values: dict[tuple[str, str], object]):
        self.values = values

    def get(self, namespace: str, key: str, default: object = None) -> object:
        return self.values.get((namespace, key), default)


def test_template_is_strict_and_embeds_existing_signature(tmp_path: Path) -> None:
    signature = tmp_path / "firma.png"
    signature.write_bytes(b"png-data")
    renderer = JinjaTemplateRenderer()
    template = EmailTemplate(name="T", html="<p>{{ proveedor }}</p>", signature_path=str(signature))
    html = renderer.render(template, {"proveedor": "Árbol & Cía"})
    assert "Árbol &amp; Cía" in html
    assert "data:image/png;base64" in html
    with pytest.raises(UndefinedError):
        renderer.render(template, {})


def test_context_file_search_prefers_payload_then_latest_match(tmp_path: Path) -> None:
    direct = tmp_path / "directo.pdf"
    direct.write_bytes(b"direct")
    service = OrderFileService(Settings({("files", "pdf_folder"): str(tmp_path)}), object())  # type: ignore[arg-type]
    assert service.find_context_file({"pdf_path": str(direct)}) == direct.resolve()
    task_file = tmp_path / "OC_9988.pdf"
    task_file.write_bytes(b"pdf")
    assert service.find_context_file({"task_number": "9988"}) == task_file


def test_task_extraction_preserves_every_distinct_number_in_order() -> None:
    assert extract_task_numbers(
        "TAREA #19558554854 / Tarea 19558554855 / No. Tarea 19558554854"
    ) == ["19558554854", "19558554855"]


def test_order_resolver_chooses_latest_duplicate_pdf(tmp_path: Path, monkeypatch) -> None:
    older = tmp_path / "OC 373627 anterior.pdf"
    latest = tmp_path / "OC 373627 actual.pdf"
    older.write_bytes(b"older")
    latest.write_bytes(b"latest")
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(latest, ns=(2_000_000_000, 2_000_000_000))

    class Suppliers:
        @staticmethod
        def find_by_ruc(_ruc: str) -> Supplier:
            return Supplier(
                name="Proveedor",
                ruc="0999999999001",
                email_primary="proveedor@example.com",
            )

    monkeypatch.setattr(
        OrderFileService,
        "extract",
        staticmethod(
            lambda _path: {
                "ruc": "0999999999001",
                "supplier": "Proveedor",
                "task_number": "19558554854",
                "task_numbers": ["19558554854", "19558554855"],
            }
        ),
    )
    service = OrderFileService(
        Settings({("files", "pdf_folder"): str(tmp_path)}), Suppliers()  # type: ignore[arg-type]
    )

    order = service.resolve("373627")

    assert Path(order.pdf_path) == latest
    assert order.task_numbers == ["19558554854", "19558554855"]


def test_supplier_resolution_uses_older_duplicate_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    older = tmp_path / "373627 - PROVEEDOR ANTERIOR.pdf"
    latest = tmp_path / "373627.pdf"
    older.write_bytes(b"older")
    latest.write_bytes(b"latest")
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(latest, ns=(2_000_000_000, 2_000_000_000))

    class Suppliers:
        @staticmethod
        def find_by_ruc(_ruc: str):
            return None

    monkeypatch.setattr(
        OrderFileService,
        "extract",
        staticmethod(
            lambda path: {
                "ruc": "",
                "supplier": "Proveedor recuperado" if path == older else "",
                "task_numbers": [],
            }
        ),
    )
    service = OrderFileService(
        Settings({("files", "pdf_folder"): str(tmp_path)}), Suppliers()  # type: ignore[arg-type]
    )

    assert service.resolve_supplier(
        "373627",
        preferred_path=latest,
        preferred_info={"ruc": "", "supplier": ""},
    ) == "Proveedor recuperado"


def test_supplier_resolution_uses_safe_filename_but_not_parent_folder(
    tmp_path: Path, monkeypatch
) -> None:
    task_folder = tmp_path / "Septiembre" / "19558554854"
    task_folder.mkdir(parents=True)
    named = task_folder / "373627 - PROVEEDOR ARCHIVO (1).pdf"
    unnamed = task_folder / "OC 373628 actual.pdf"
    named.write_bytes(b"named")
    unnamed.write_bytes(b"unnamed")

    class Suppliers:
        @staticmethod
        def find_by_ruc(_ruc: str):
            return None

    monkeypatch.setattr(
        OrderFileService,
        "extract",
        staticmethod(lambda _path: {"ruc": "", "supplier": "", "task_numbers": []}),
    )
    service = OrderFileService(
        Settings({("files", "pdf_folder"): str(tmp_path)}), Suppliers()  # type: ignore[arg-type]
    )

    assert service.resolve("373627").supplier == "PROVEEDOR ARCHIVO"
    assert service.resolve("373628").supplier == ""
