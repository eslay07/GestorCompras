"""Puente entre el menú y las pantallas de configuración."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from gestorcompras.core import config as core_config
from gestorcompras.gui import config_gui as bienes_config
from gestorcompras.ui.common import center_window

_SERVICIOS_FIELDS = (
    ("cadena_asunto_fija", "Cadena fija en asunto"),
    ("zona_horaria", "Zona horaria"),
    ("carpeta_correo", "Carpeta de correo"),
    ("fuente_correo", "Fuente"),
    ("imap_host", "Servidor IMAP"),
    ("imap_user", "Usuario IMAP"),
    ("imap_password", "Contraseña IMAP"),
)


class ServiciosConfig(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        self.title("Configuración de Servicios")
        self.geometry("480x420")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._vars: dict[str, tk.Variable] = {}
        self._build()
        center_window(self)

    def _build(self) -> None:
        content = ttk.Frame(self, padding=20, style="MyFrame.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        servicios_cfg = core_config.get_servicios_config()
        correo = core_config.get_user_email()

        ttk.Label(
            content,
            text=f"Usuario autenticado: {correo or 'No definido'}",
            style="MyLabel.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        for idx, (key, label) in enumerate(_SERVICIOS_FIELDS, start=1):
            ttk.Label(content, text=f"{label}:", style="MyLabel.TLabel").grid(row=idx, column=0, sticky="w", pady=5)
            if key == "fuente_correo":
                var = tk.StringVar(value=servicios_cfg.get(key, "IMAP"))
                widget = ttk.Combobox(content, textvariable=var, values=["IMAP", "OWA"], state="readonly")
                widget.configure(style="TCombobox")
            elif key == "imap_password":
                var = tk.StringVar(value=servicios_cfg.get(key, ""))
                widget = ttk.Entry(content, textvariable=var, show="*", style="MyEntry.TEntry")
            else:
                var = tk.StringVar(value=servicios_cfg.get(key, ""))
                widget = ttk.Entry(content, textvariable=var, style="MyEntry.TEntry")
            widget.grid(row=idx, column=1, sticky="ew", pady=5)
            self._vars[key] = var

        btn_frame = ttk.Frame(content, style="MyFrame.TFrame")
        btn_frame.grid(row=len(_SERVICIOS_FIELDS) + 1, column=0, columnspan=2, pady=(20, 0))

        ttk.Button(
            btn_frame,
            text="Guardar",
            style="MyButton.TButton",
            command=self._save,
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame,
            text="Cerrar",
            style="MyButton.TButton",
            command=self.destroy,
        ).pack(side="left", padx=5)

    def _save(self) -> None:
        for key, var in self._vars.items():
            core_config.set_value("servicios", key, var.get())
        messagebox.showinfo("Configuración", "Parámetros de servicios actualizados.", parent=self)


def open(master: tk.Misc, email_session: dict[str, str] | None = None, mode: str = "bienes") -> None:
    if mode == "servicios":
        ServiciosConfig(master)
    else:
        bienes_config.open_config_gui(master, email_session)
