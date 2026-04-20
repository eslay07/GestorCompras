"""Diálogo de edición para una tarea de Actua. Tareas."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras import theme
from gestorcompras.ui.common import add_hover_effect

ALL_KNOWN_FIELDS = [
    ("task_number", "N° Tarea"),
    ("proveedor", "Proveedor"),
    ("factura", "Factura"),
    ("oc", "OC"),
    ("ingreso", "Ingreso"),
    ("ruc", "RUC"),
    ("mecanico", "Mecánico"),
    ("telefono", "Teléfono"),
    ("inf_vehiculo", "Vehículo"),
    ("fecha_orden", "Fecha Orden"),
    ("emails", "Correos (CC/TO)"),
]


class TaskEditDialog(tk.Toplevel):
    """Formulario dinámico para editar los campos de una tarea."""

    def __init__(
        self,
        master: tk.Misc,
        task: dict,
        required_keys: set[str] | None = None,
    ):
        super().__init__(master)
        self.title("Editar tarea")
        self.transient(master.winfo_toplevel() if hasattr(master, "winfo_toplevel") else master)
        self.grab_set()
        self.task = task
        self.required_keys = required_keys or set()
        self.saved = False
        self._vars: dict[str, tk.StringVar] = {}
        self._labels: dict[str, ttk.Label] = {}
        self._build()

    def _build(self) -> None:
        wrapper = ttk.Frame(self, style="MyFrame.TFrame", padding=16)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper, text="Editar Tarea", font=("Segoe UI", 13, "bold"),
                  foreground=theme.color_titulos).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Separator(wrapper, orient="horizontal").grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        ttk.Label(wrapper, text="Los campos marcados con * son requeridos por el flujo seleccionado.",
                  font=("Segoe UI", 9), foreground="#6B7280").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))

        visible_keys = {"task_number"} | self.required_keys | set(self.task.keys())
        visible_keys -= {"_email_body", "body", "_db_id", "_created_at",
                         "message_id", "raw_hash", "correo_usuario_encontrado"}

        row = 3
        for key, label in ALL_KNOWN_FIELDS:
            if key not in visible_keys:
                continue
            is_required = key in self.required_keys
            lbl_text = f"* {label}" if is_required else label
            lbl = ttk.Label(wrapper, text=lbl_text, style="MyLabel.TLabel")
            lbl.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)

            current = self.task.get(key, "")
            if isinstance(current, (list, tuple)):
                current = ", ".join(str(v) for v in current if v)
            var = tk.StringVar(value=str(current or ""))
            self._vars[key] = var

            entry = ttk.Entry(wrapper, textvariable=var, style="MyEntry.TEntry", width=50)
            entry.grid(row=row, column=1, sticky="ew", pady=5)

            if is_required and not str(current or "").strip():
                lbl.configure(foreground=theme.color_danger)
            self._labels[key] = lbl

            var.trace_add("write", lambda *_a, k=key: self._on_change(k))
            row += 1

        wrapper.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(wrapper, style="MyFrame.TFrame")
        btn_frame.grid(row=row, column=0, columnspan=2, sticky="e", pady=(12, 0))
        save_btn = ttk.Button(btn_frame, text="Guardar", style="MyButton.TButton", command=self._save)
        save_btn.pack(side="right", padx=6)
        add_hover_effect(save_btn)
        ttk.Button(btn_frame, text="Cancelar", style="MyButton.TButton",
                   command=self.destroy).pack(side="right")

    def _on_change(self, key: str) -> None:
        if key not in self.required_keys:
            return
        lbl = self._labels.get(key)
        if not lbl:
            return
        val = self._vars[key].get().strip()
        lbl.configure(foreground=theme.color_danger if not val else theme.color_texto)

    def _save(self) -> None:
        for key, var in self._vars.items():
            val = var.get().strip()
            if key == "emails":
                self.task[key] = [e.strip() for e in val.split(",") if e.strip()]
            else:
                self.task[key] = val
        self.saved = True
        self.destroy()
