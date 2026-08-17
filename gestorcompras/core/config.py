"""Configuración cerrada y segura para el entorno demostrativo."""

from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class DemoConfig:
    """Parámetros que mantienen la aplicación aislada por diseño."""

    demo_mode: bool = True
    profile: str = "portfolio"
    company_name: str = "Empresa Demo S.A."
    user_name: str = "Usuario Demo"
    user_email: str = "demo@example.com"
    output_path: str = r"C:\Demo\GestorCompras\pdfs"

    @classmethod
    def from_environment(cls) -> "DemoConfig":
        raw_mode = os.getenv("GESTORCOMPRAS_DEMO_MODE", "1").strip().casefold()
        if raw_mode not in {"1", "true", "yes", "on"}:
            raise RuntimeError("Esta edición solamente admite el modo demostración.")
        return cls(profile=os.getenv("GESTORCOMPRAS_DEMO_PROFILE", "portfolio"))
