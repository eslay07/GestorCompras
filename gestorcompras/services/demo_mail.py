"""Generador de correos en memoria; nunca abre una conexión."""

from __future__ import annotations

from dataclasses import replace

from gestorcompras.core.models import DemoMessage
from gestorcompras.demo import fixtures


class DemoMailService:
    def __init__(self) -> None:
        self._messages = list(fixtures.messages())
        self._generated: list[DemoMessage] = []

    def list_messages(self) -> tuple[DemoMessage, ...]:
        return tuple(self._messages + self._generated)

    def generate(self, recipient: str, order_id: str) -> DemoMessage:
        if recipient.rpartition("@")[2].casefold() != "example.com":
            raise ValueError("El modo demo solo admite destinatarios example.com.")
        if not order_id.startswith("OC-DEMO-"):
            raise ValueError("La referencia debe pertenecer al conjunto demostrativo.")

        message = DemoMessage(
            message_id=f"MSG-DEMO-{len(self._messages) + len(self._generated) + 1:03d}",
            recipient=recipient,
            subject=f"Vista previa de {order_id}",
            preview="Mensaje generado localmente con datos sintéticos.",
            status="Simulado",
        )
        self._generated.append(replace(message))
        return message

    @property
    def generated_count(self) -> int:
        return len(self._generated)
