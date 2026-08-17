"""Ventana principal, navegación y acceso demostrativo."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras.core.application import DemoServices, build_demo_services
from gestorcompras.core.config import DemoConfig
from gestorcompras.gui import theme
from gestorcompras.gui.screens import SCREEN_CLASSES


NAVIGATION = (
    ("inicio", "Inicio"),
    ("configuracion", "Configuración"),
    ("correos", "Correos demo"),
    ("reasignacion", "Reasignación"),
    ("descargas", "Descargas"),
    ("actualizar_tareas", "Actualizar tareas"),
)


class DemoApplication(tk.Tk):
    def __init__(self, config: DemoConfig | None = None, services: DemoServices | None = None) -> None:
        super().__init__()
        self.config_data = config or DemoConfig.from_environment()
        self.services = services or build_demo_services(self.config_data)
        self.title("GestorCompras · Demostración")
        self.geometry("1280x760+40+40")
        self.minsize(1100, 680)
        theme.configure_styles(self)
        self.active_screen = "login"
        self._nav_buttons: dict[str, tk.Button] = {}
        self._content: ttk.Frame | None = None
        self.show_login()

    def _clear_root(self) -> None:
        for child in self.winfo_children():
            child.destroy()

    def show_login(self) -> None:
        self._clear_root()
        self.active_screen = "login"
        outer = tk.Frame(self, bg=theme.BACKGROUND)
        outer.pack(fill="both", expand=True)

        brand = tk.Frame(outer, bg=theme.BACKGROUND)
        brand.place(x=46, y=34)
        tk.Label(brand, text="GC", bg=theme.NAVY, fg="#FFFFFF", font=("Segoe UI", 13, "bold"), padx=11, pady=8).pack(side="left")
        tk.Label(brand, text="GestorCompras", bg=theme.BACKGROUND, fg=theme.NAVY, font=("Segoe UI", 16, "bold")).pack(side="left", padx=12)

        card = tk.Frame(outer, bg=theme.SURFACE, highlightbackground=theme.BORDER, highlightthickness=1, padx=48, pady=38)
        card.place(relx=0.5, rely=0.51, anchor="center", width=510, height=510)
        tk.Label(card, text="ENTORNO DE PORTAFOLIO", bg=theme.PRIMARY_SOFT, fg=theme.PRIMARY, font=("Segoe UI", 8, "bold"), padx=10, pady=5).pack()
        tk.Label(card, text="Explora el flujo demo", bg=theme.SURFACE, fg=theme.NAVY, font=("Segoe UI", 24, "bold")).pack(pady=(18, 7))
        tk.Label(
            card,
            text="Una experiencia autónoma con datos sintéticos\ny operaciones simuladas.",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=("Segoe UI", 10),
            justify="center",
        ).pack()

        identity = tk.Frame(card, bg=theme.SURFACE_SOFT, padx=18, pady=15)
        identity.pack(fill="x", pady=(25, 18))
        tk.Label(identity, text="UD", bg=theme.ACCENT_SOFT, fg=theme.ACCENT, font=("Segoe UI", 11, "bold"), width=4, height=2).pack(side="left")
        identity_text = tk.Frame(identity, bg=theme.SURFACE_SOFT)
        identity_text.pack(side="left", padx=12)
        tk.Label(identity_text, text=self.config_data.user_name, bg=theme.SURFACE_SOFT, fg=theme.TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(identity_text, text=self.config_data.user_email, bg=theme.SURFACE_SOFT, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(identity, text="LISTO", bg=theme.ACCENT_SOFT, fg=theme.ACCENT, font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side="right")

        ttk.Button(card, text="Ingresar a la demostración", style="Primary.TButton", command=self.enter_demo).pack(fill="x", pady=(3, 15))
        tk.Label(
            card,
            text="No se solicitan credenciales · No se utiliza Internet",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=("Segoe UI", 8),
        ).pack()
        tk.Label(
            outer,
            text="Empresa Demo S.A.  •  Datos incluidos y sintéticos",
            bg=theme.BACKGROUND,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
        ).place(relx=0.5, rely=0.94, anchor="center")

    def enter_demo(self) -> None:
        self._clear_root()
        shell = tk.Frame(self, bg=theme.BACKGROUND)
        shell.pack(fill="both", expand=True)
        self._build_sidebar(shell)

        main = tk.Frame(shell, bg=theme.BACKGROUND)
        main.pack(side="left", fill="both", expand=True)
        self._build_topbar(main)
        self._content = ttk.Frame(main, padding=(28, 22, 28, 20))
        self._content.pack(fill="both", expand=True)
        self.show_screen("inicio")

    def _build_sidebar(self, parent: tk.Misc) -> None:
        sidebar = tk.Frame(parent, bg=theme.NAVY, width=242)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        header = tk.Frame(sidebar, bg=theme.NAVY)
        header.pack(fill="x", padx=20, pady=(24, 22))
        tk.Label(header, text="GC", bg=theme.PRIMARY, fg="#FFFFFF", font=("Segoe UI", 12, "bold"), padx=9, pady=7).pack(side="left")
        tk.Label(header, text="GestorCompras", bg=theme.NAVY, fg="#FFFFFF", font=("Segoe UI", 14, "bold")).pack(side="left", padx=10)

        tk.Label(sidebar, text="NAVEGACIÓN", bg=theme.NAVY, fg="#93A8BC", font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", padx=22, pady=(4, 7))
        self._nav_buttons.clear()
        for key, label in NAVIGATION:
            button = tk.Button(
                sidebar,
                text=label,
                command=lambda screen=key: self.show_screen(screen),
                bg=theme.NAVY,
                fg="#D9E2EC",
                activebackground=theme.NAVY_SOFT,
                activeforeground="#FFFFFF",
                relief="flat",
                bd=0,
                cursor="hand2",
                anchor="w",
                padx=22,
                pady=11,
                font=("Segoe UI", 10),
            )
            button.pack(fill="x", padx=8, pady=1)
            self._nav_buttons[key] = button

        spacer = tk.Frame(sidebar, bg=theme.NAVY)
        spacer.pack(fill="both", expand=True)
        guard = tk.Frame(sidebar, bg=theme.NAVY_SOFT, padx=14, pady=12)
        guard.pack(fill="x", padx=14, pady=(0, 13))
        tk.Label(guard, text="MODO DEMO", bg=theme.NAVY_SOFT, fg="#7DD3FC", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(guard, text="Sin conexiones externas", bg=theme.NAVY_SOFT, fg="#D9E2EC", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        profile = tk.Frame(sidebar, bg="#0B2239", padx=17, pady=14)
        profile.pack(fill="x")
        tk.Label(profile, text="UD", bg=theme.ACCENT, fg="#FFFFFF", font=("Segoe UI", 9, "bold"), width=3, height=2).pack(side="left")
        details = tk.Frame(profile, bg="#0B2239")
        details.pack(side="left", padx=10)
        tk.Label(details, text=self.config_data.user_name, bg="#0B2239", fg="#FFFFFF", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(details, text=self.config_data.user_email, bg="#0B2239", fg="#9FB3C8", font=("Segoe UI", 8)).pack(anchor="w")

    def _build_topbar(self, parent: tk.Misc) -> None:
        topbar = tk.Frame(parent, bg=theme.SURFACE, height=64, highlightbackground=theme.BORDER, highlightthickness=1)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text=self.config_data.company_name, bg=theme.SURFACE, fg=theme.NAVY, font=("Segoe UI", 11, "bold")).pack(side="left", padx=28)
        tk.Label(topbar, text="DATOS SINTÉTICOS", bg=theme.ACCENT_SOFT, fg=theme.ACCENT, font=("Segoe UI", 8, "bold"), padx=10, pady=5).pack(side="right", padx=(8, 26))
        tk.Label(topbar, text="● Sin conexión", bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="right")

    def show_screen(self, screen: str) -> None:
        if self._content is None:
            raise RuntimeError("La demostración todavía no se ha iniciado.")
        screen_class = SCREEN_CLASSES.get(screen)
        if screen_class is None:
            raise KeyError(f"Pantalla desconocida: {screen}")
        for child in self._content.winfo_children():
            child.destroy()
        self.active_screen = screen
        for key, button in self._nav_buttons.items():
            if key == screen:
                button.configure(bg=theme.PRIMARY, fg="#FFFFFF", font=("Segoe UI", 10, "bold"))
            else:
                button.configure(bg=theme.NAVY, fg="#D9E2EC", font=("Segoe UI", 10))
        screen_class(self._content, self.services, self.config_data).pack(fill="both", expand=True)


def create_app() -> DemoApplication:
    return DemoApplication()


def main() -> None:
    app = create_app()
    app.mainloop()


if __name__ == "__main__":
    main()
