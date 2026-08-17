"""Composición explícita de los únicos servicios permitidos."""

from __future__ import annotations

from dataclasses import dataclass

from gestorcompras.core.config import DemoConfig
from gestorcompras.services.demo_mail import DemoMailService
from gestorcompras.services.demo_storage import DemoStorageService
from gestorcompras.services.demo_tasks import DemoTaskService


@dataclass(slots=True)
class DemoServices:
    mail: DemoMailService
    tasks: DemoTaskService
    storage: DemoStorageService


def build_demo_services(config: DemoConfig | None = None) -> DemoServices:
    selected = config or DemoConfig.from_environment()
    if not selected.demo_mode:
        raise RuntimeError("Los adaptadores externos no forman parte de esta edición.")
    return DemoServices(
        mail=DemoMailService(),
        tasks=DemoTaskService(),
        storage=DemoStorageService(output_path=selected.output_path),
    )
