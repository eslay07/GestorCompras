"""Descargas simuladas sin acceso al disco ni a unidades externas."""

from __future__ import annotations

from gestorcompras.core.models import DemoDocument, OperationResult
from gestorcompras.demo import fixtures


class DemoStorageService:
    def __init__(self, output_path: str = fixtures.DEMO_OUTPUT_PATH) -> None:
        self.output_path = output_path
        self._documents = {item.document_id: item for item in fixtures.documents()}
        self._downloads: list[str] = []

    def list_documents(self) -> tuple[DemoDocument, ...]:
        return tuple(self._documents.values())

    def download(self, document_id: str) -> OperationResult:
        document = self._documents.get(document_id)
        if document is None:
            raise KeyError("Documento demostrativo desconocido.")
        virtual_path = f"{self.output_path}\\{document.filename}"
        self._downloads.append(virtual_path)
        return OperationResult(
            ok=True,
            message="Descarga simulada; no se escribió ningún archivo.",
            reference=virtual_path,
        )

    @property
    def downloads(self) -> tuple[str, ...]:
        return tuple(self._downloads)
