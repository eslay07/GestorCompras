from __future__ import annotations

import logging
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Callable

from gestorcompras.services import actua_tareas_automation as auto
from gestorcompras.services import actua_tareas_repo, db, task_inbox
from gestorcompras.services.credentials import resolve_telcos_credentials
from gestorcompras.services.reassign_bridge import _create_driver
from gestorcompras.services.telcos_automation import login_telcos
from gestorcompras.ui.common import add_hover_effect

logger = logging.getLogger(__name__)

_ORIGEN_MAP = {
    "Manual": None,
    "Desde Reasignación": "reasignacion",
    "Desde Descargas OC": "descargas_oc",
    "Desde Correos Masivos": "correos_masivos",
}


# Columnas mostradas en el cuadro de tareas ejecutadas para cada módulo.
# Se definen aquí para que los módulos origen no necesiten duplicar el mapeo.
_ORIGEN_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "reasignacion": [
        ("task_number", "N° Tarea"),
        ("proveedor", "Proveedor / Taller"),
        ("mecanico", "Mecánico"),
        ("telefono", "Teléfono"),
        ("inf_vehiculo", "Vehículo"),
    ],
    "correos_masivos": [
        ("task_number", "N° Tarea"),
        ("oc", "OC"),
        ("proveedor", "Proveedor"),
        ("ruc", "RUC"),
        ("factura", "Factura"),
        ("emails", "Correos"),
    ],
    "descargas_oc": [
        ("task_number", "N° Tarea"),
        ("oc", "OC"),
        ("proveedor", "Proveedor"),
        ("fecha_orden", "Fecha"),
    ],
}

_OPEN_ACTUA_PANEL = None



def _required_keys_for_flow(pasos: list[dict]) -> set[str]:
    """Extrae las claves de contexto ({clave}) requeridas por un flujo."""
    keys: set[str] = set()
    placeholder = re.compile(r"\{(\w+)\}")
    for paso in pasos or []:
        action_id = paso.get("id")
        params = paso.get("params") or {}
        if action_id == "ingresar_numero_tarea":
            if not str(params.get("numero", "")).strip():
                keys.add("task_number")
        for value in params.values():
            for match in placeholder.findall(str(value or "")):
                keys.add(match)
    return keys


def _task_value(task: dict, key: str) -> str:
    value = task.get(key)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value)


def _normalize_task_number(task_number: str | None) -> str:
    texto = str(task_number or "").strip().upper()
    # Normaliza entradas como "12 34", "12-34" o "TAREA 1234".
    return re.sub(r"[^A-Z0-9]", "", texto)


def _has_duplicate_task_numbers(tasks: list[dict]) -> bool:
    seen: set[str] = set()
    for task in tasks:
        normalized = _normalize_task_number(task.get("task_number"))
        if not normalized:
            continue
        if normalized in seen:
            return True
        seen.add(normalized)
    return False


class ActionTooltip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            bg="#fff7d1",
            fg="#1f1f1f",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=4,
            font=("Segoe UI", 9),
        )
        lbl.pack()

    def _hide(self, _event=None):
        if self.tip_window is not None:
            self.tip_window.destroy()
            self.tip_window = None


class ActuaTareasScreen(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        email_session: dict[str, str],
        origin: str,
        on_close: Callable[[], None] | None = None,
    ):
        super().__init__(master, style="MyFrame.TFrame")
        self.master = master
        self.email_session = email_session
        self.origin = origin
        self.on_close = on_close
        self.pasos: list[dict] = []
        self.flujos: list[dict] = []
        self.aliases: dict[str, str] = {}
        self.selected_inbox_ids: set[int] = set()

        self.nombre_flujo = tk.StringVar()
        self.flujo_var = tk.StringVar()
        self.carpeta_base_var = tk.StringVar(value=actua_tareas_repo.get_carpeta_base(""))
        self.mostrar_nav_var = tk.BooleanVar(value=True)
        self.report_var = tk.BooleanVar(value=db.get_config("ACTUA_REPORT_EMAIL", "1") != "0")
        self.origen_var = tk.StringVar(value="Manual")
        self.status_var = tk.StringVar(value="Listo")
        self.action_help_var = tk.StringVar(value="Seleccione una acción para ver su descripción.")

        self._build()
        self._load_aliases()
        self._refresh_flujos()

    def _build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1, minsize=230)
        self.rowconfigure(4, weight=0)

        head = ttk.Frame(self, style="MyFrame.TFrame", padding=(10, 10, 10, 4))
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        head.columnconfigure(1, weight=1)

        ttk.Label(head, text="Actualizar Tareas",
                  font=("Segoe UI", 16, "bold"), foreground="#111827").grid(row=0, column=0, sticky="w")
        ttk.Label(head, text="Cree y ejecute flujos de automatizacion sobre tareas en Telcos.",
                  font=("Segoe UI", 10), foreground="#6B7280").grid(row=0, column=1, sticky="w", padx=(16, 0))
        btn_back_top = ttk.Button(
            head,
            text="Regresar al menú",
            style="MyButton.TButton",
            command=self._go_back,
        )
        btn_back_top.grid(row=0, column=2, sticky="e", padx=(8, 0))
        add_hover_effect(btn_back_top)

        ttk.Separator(self, orient="horizontal").grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)

        flujo_frame = ttk.LabelFrame(self, text="Flujo guardado", style="MyLabelFrame.TLabelframe", padding=10)
        flujo_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 6))
        flujo_frame.columnconfigure(1, weight=1)

        ttk.Label(flujo_frame, text="Flujo:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
        self.flujo_combo = ttk.Combobox(flujo_frame, textvariable=self.flujo_var, state="readonly", width=35)
        self.flujo_combo.grid(row=0, column=1, padx=8, sticky="w")
        self.flujo_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_selected_flujo())

        for i, (txt, cmd) in enumerate([
            ("Nuevo flujo", self._nuevo_flujo),
            ("Guardar flujo", self._guardar_flujo),
            ("Eliminar flujo", self._eliminar_flujo),
        ]):
            b = ttk.Button(flujo_frame, text=txt, style="MyButton.TButton", command=cmd)
            b.grid(row=0, column=2 + i, padx=4)
            add_hover_effect(b)

        ttk.Label(flujo_frame, text="Seleccione un flujo existente o cree uno nuevo con las acciones disponibles.",
                  font=("Segoe UI", 9), foreground="#6B7280").grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(4, 0))

        left = ttk.LabelFrame(self, text="Acciones disponibles", style="MyLabelFrame.TLabelframe", padding=8)
        left.grid(row=3, column=0, sticky="nsew", padx=(10, 5), pady=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        act_canvas = tk.Canvas(left, highlightthickness=0)
        act_scroll = ttk.Scrollbar(left, orient="vertical", command=act_canvas.yview)
        act_container = ttk.Frame(act_canvas, style="MyFrame.TFrame")
        act_canvas.configure(yscrollcommand=act_scroll.set)
        act_canvas.pack(side="left", fill="both", expand=True)
        act_scroll.pack(side="right", fill="y")
        act_window = act_canvas.create_window((0, 0), window=act_container, anchor="nw")

        def _sync_actions_canvas(_event=None):
            act_canvas.configure(scrollregion=act_canvas.bbox("all"))
            act_canvas.itemconfigure(act_window, width=act_canvas.winfo_width())

        act_container.bind("<Configure>", _sync_actions_canvas)
        act_canvas.bind("<Configure>", _sync_actions_canvas)

        for i, accion in enumerate(auto.ACCIONES):
            btn = ttk.Button(
                act_container, text=accion["label"],
                style="MyButton.TButton",
                command=lambda a=accion: self._agregar_paso(a),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=3, padx=(0, 4))
            add_hover_effect(btn)
            descripcion = accion.get("descripcion", "")
            ActionTooltip(btn, descripcion)
            btn.bind("<Enter>", lambda _e, d=descripcion: self.action_help_var.set(d), add="+")

        ttk.Label(left, textvariable=self.action_help_var, style="MyLabel.TLabel",
                  wraplength=360, justify="left").pack(fill="x", padx=4, pady=(4, 0))

        right = ttk.LabelFrame(self, text="Pasos del flujo", style="MyLabelFrame.TLabelframe", padding=8)
        right.grid(row=3, column=1, sticky="nsew", padx=(5, 10), pady=(0, 8))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(right, columns=("n", "accion", "params"),
                                 show="headings", style="MyTreeview.Treeview", height=8)
        self.tree.heading("n", text="#")
        self.tree.heading("accion", text="Accion")
        self.tree.heading("params", text="Parametros")
        self.tree.column("n", width=40, anchor="center")
        self.tree.column("accion", width=260)
        self.tree.column("params", width=320)
        self.tree.grid(row=0, column=0, sticky="nsew")

        actions_row = ttk.Frame(right, style="MyFrame.TFrame")
        actions_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for txt, cmd in (("Subir", self._move_up), ("Bajar", self._move_down),
                         ("Editar", self._edit_step), ("Quitar", self._del_step)):
            b = ttk.Button(actions_row, text=txt, style="MyButton.TButton", command=cmd, width=7)
            b.pack(side="left", padx=3)

        bottom = ttk.LabelFrame(self, text="Ejecucion", style="MyLabelFrame.TLabelframe", padding=10)
        bottom.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        bottom.columnconfigure(3, weight=1)

        ttk.Label(bottom, text="Carpeta base:", style="MyLabel.TLabel").grid(
            row=0, column=0, padx=(0, 4), sticky="w")
        ttk.Entry(bottom, textvariable=self.carpeta_base_var, style="MyEntry.TEntry",
                  width=52).grid(row=0, column=1, columnspan=3, padx=4, sticky="ew")
        ttk.Button(bottom, text="Examinar...", style="MyButton.TButton",
                   command=self._pick_folder).grid(row=0, column=4, padx=(4, 0))

        ttk.Label(bottom, text="Tareas manuales (1 por linea):", style="MyLabel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(6, 0))
        self.manual_tasks_text = tk.Text(bottom, height=3, width=36, relief="solid",
                                          borderwidth=1, font=("Segoe UI", 10))
        self.manual_tasks_text.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(6, 0))
        self.manual_tasks_text.bind("<Control-Return>", lambda _e: self._run_flow())

        source_frame = ttk.LabelFrame(bottom, text="Origen de tareas", style="MyLabelFrame.TLabelframe", padding=6)
        source_frame.grid(row=1, column=3, columnspan=2, sticky="ew", padx=(8, 0), pady=(6, 0))
        ttk.Combobox(source_frame, textvariable=self.origen_var,
                     values=list(_ORIGEN_MAP.keys()), state="readonly", width=24).grid(
            row=0, column=0, sticky="w")
        self.origen_var.trace_add("write", lambda *_: self._refresh_inbox())

        btn_all = ttk.Button(source_frame, text="Todos", command=self._inbox_select_all)
        btn_none = ttk.Button(source_frame, text="Ninguno", command=self._inbox_select_none)
        btn_clear = ttk.Button(source_frame, text="Limpiar", command=self._inbox_clear)
        btn_manual_run = ttk.Button(source_frame, text="Ejecutar manual", command=self._run_flow)
        btn_all.grid(row=0, column=1, padx=3)
        btn_none.grid(row=0, column=2, padx=3)
        btn_clear.grid(row=0, column=3, padx=3)
        btn_manual_run.grid(row=0, column=4, padx=3)
        add_hover_effect(btn_manual_run)

        self.inbox_tree = ttk.Treeview(source_frame, columns=("sel", "origen", "task"),
                                       show="headings", style="MyTreeview.Treeview", height=2)
        for col, txt, w in (("sel", "✓", 30), ("origen", "Origen", 110), ("task", "Tarea", 110)):
            self.inbox_tree.heading(col, text=txt)
            self.inbox_tree.column(col, width=w, anchor="center")
        self.inbox_tree.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        self.inbox_tree.bind("<Button-1>", self._toggle_inbox_row)

        checks = ttk.Frame(bottom, style="MyFrame.TFrame")
        checks.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(
            checks,
            text="Mostrar navegador al ejecutar",
            style="MyCheckbutton.TCheckbutton",
            variable=self.mostrar_nav_var,
        ).pack(side="left")
        ttk.Checkbutton(
            checks,
            text="Enviarme reporte",
            style="MyCheckbutton.TCheckbutton",
            variable=self.report_var,
        ).pack(side="left", padx=(10, 0))
        ttk.Label(bottom, textvariable=self.status_var, style="MyLabel.TLabel",
                  font=("Segoe UI", 9), foreground="#6B7280").grid(
            row=2, column=3, columnspan=2, sticky="w", pady=(8, 0))

        self.log = ScrolledText(bottom, height=5, state="disabled", font=("Segoe UI", 9))
        self.log.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(6, 4))

        btn_row = ttk.Frame(bottom, style="MyFrame.TFrame")
        btn_row.grid(row=4, column=0, columnspan=5, sticky="ew")
        btn_row.columnconfigure(0, weight=1)

        alias_frame = ttk.LabelFrame(btn_row, text="Alias de archivos",
                                     style="MyLabelFrame.TLabelframe", padding=6)
        alias_frame.grid(row=0, column=0, sticky="w")
        self.alias_name = tk.StringVar()
        self.alias_path = tk.StringVar()
        ttk.Entry(alias_frame, textvariable=self.alias_name, style="MyEntry.TEntry",
                  width=16).grid(row=0, column=0, padx=4)
        ttk.Entry(alias_frame, textvariable=self.alias_path, style="MyEntry.TEntry",
                  width=36).grid(row=0, column=1, padx=4)
        ttk.Button(alias_frame, text="...", command=self._pick_alias_folder).grid(row=0, column=2)
        ttk.Button(alias_frame, text="Guardar alias", style="MyButton.TButton",
                   command=self._save_alias).grid(row=0, column=3, padx=4)

        run_btn = ttk.Button(btn_row, text="Ejecutar flujo", style="MyButton.TButton",
                             command=self._run_flow)
        run_btn.grid(row=0, column=1, padx=4, sticky="e")
        add_hover_effect(run_btn)
        back_btn = ttk.Button(btn_row, text="Regresar", style="MyButton.TButton",
                              command=self._go_back)
        back_btn.grid(row=0, column=2, padx=(0, 4), sticky="e")
        add_hover_effect(back_btn)

    def _log(self, txt: str):
        self.log.configure(state="normal")
        self.log.insert(tk.END, txt + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def _agregar_paso(self, accion_meta: dict):
        self.pasos.append({"id": accion_meta["id"], "params": {}})
        self._refresh_tree()

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        meta_by_id = {a["id"]: a for a in auto.ACCIONES}
        for i, paso in enumerate(self.pasos, start=1):
            meta = meta_by_id.get(paso["id"], {})
            params = ", ".join(f"{k}={v}" for k, v in (paso.get("params") or {}).items())
            self.tree.insert("", tk.END, iid=str(i - 1), values=(i, meta.get("label", paso["id"]), params))

    def _move_up(self):
        idx = self._selected_index()
        if idx is None or idx == 0:
            return
        self.pasos[idx - 1], self.pasos[idx] = self.pasos[idx], self.pasos[idx - 1]
        self._refresh_tree()

    def _move_down(self):
        idx = self._selected_index()
        if idx is None or idx >= len(self.pasos) - 1:
            return
        self.pasos[idx + 1], self.pasos[idx] = self.pasos[idx], self.pasos[idx + 1]
        self._refresh_tree()

    def _edit_step(self):
        idx = self._selected_index()
        if idx is None:
            return
        paso = self.pasos[idx]
        meta = next((a for a in auto.ACCIONES if a["id"] == paso["id"]), None)
        if not meta:
            return
        editable_params = [
            p for p in meta.get("params", [])
            if p.get("tipo") in {"texto", "select"}
        ]
        if not editable_params:
            messagebox.showinfo(
                "Actualizar Tareas",
                "Esta acción es un botón y no contiene texto.",
                parent=self,
            )
            return

        win = tk.Toplevel(self)
        win.title(f"Editar: {meta['label']}")
        win.transient(self.winfo_toplevel())
        win.grab_set()
        values: dict[str, tk.StringVar] = {}
        for i, prm in enumerate(editable_params):
            ttk.Label(win, text=prm["label"]).grid(row=i, column=0, sticky="w", padx=6, pady=4)
            v = tk.StringVar(value=str((paso.get("params") or {}).get(prm["name"], "")))
            values[prm["name"]] = v
            if prm.get("tipo") == "select":
                ttk.Combobox(
                    win,
                    textvariable=v,
                    values=prm.get("opciones", []),
                    state="readonly",
                    width=42,
                ).grid(row=i, column=1, padx=6, pady=4)
            else:
                ttk.Entry(win, textvariable=v, width=42).grid(row=i, column=1, padx=6, pady=4)

        def _save():
            paso["params"] = {k: v.get() for k, v in values.items()}
            self._refresh_tree()
            win.destroy()

        ttk.Button(win, text="Guardar", command=_save).grid(row=99, column=1, sticky="e", padx=6, pady=8)

    def _del_step(self):
        idx = self._selected_index()
        if idx is None:
            return
        self.pasos.pop(idx)
        self._refresh_tree()

    def _selected_index(self):
        selected = self.tree.selection()
        if not selected:
            return None
        return int(selected[0])

    def _nuevo_flujo(self):
        self.pasos = []
        self.nombre_flujo.set("")
        self.flujo_var.set("")
        self._refresh_tree()

    def _guardar_flujo(self):
        nombre = self.flujo_var.get().strip() or self._ask_text("Nombre del flujo")
        if not nombre:
            return
        mode = self.origin or "general"
        actua_tareas_repo.save_flujo(nombre, mode, self.pasos)
        actua_tareas_repo.set_carpeta_base(self.carpeta_base_var.get().strip())
        self._refresh_flujos(selected_name=nombre)
        messagebox.showinfo("Actualizar Tareas", "Flujo guardado correctamente.", parent=self)

    def _eliminar_flujo(self):
        flujo = next((f for f in self.flujos if f["nombre"] == self.flujo_var.get()), None)
        if not flujo:
            return
        if not messagebox.askyesno("Eliminar", f"¿Eliminar '{flujo['nombre']}'?", parent=self):
            return
        actua_tareas_repo.delete_flujo(int(flujo["id"]))
        self._refresh_flujos()
        self.pasos = []
        self._refresh_tree()

    def _load_selected_flujo(self):
        flujo = next((f for f in self.flujos if f["nombre"] == self.flujo_var.get()), None)
        if not flujo:
            return
        self.pasos = flujo.get("pasos") or []
        self._refresh_tree()

    def _refresh_flujos(self, selected_name: str | None = None):
        mode = self.origin or "general"
        self.flujos = actua_tareas_repo.list_flujos(mode=mode)
        nombres = [f["nombre"] for f in self.flujos]
        self.flujo_combo.configure(values=nombres)
        if selected_name and selected_name in nombres:
            self.flujo_var.set(selected_name)
            self._load_selected_flujo()
        elif nombres:
            self.flujo_var.set(nombres[0])
            self._load_selected_flujo()
        else:
            self.flujo_var.set("")
            self.pasos = []
            self._refresh_tree()

    def _pick_folder(self):
        p = filedialog.askdirectory(parent=self)
        if p:
            self.carpeta_base_var.set(p)

    def _pick_alias_folder(self):
        p = filedialog.askdirectory(parent=self)
        if p:
            self.alias_path.set(p)

    def _save_alias(self):
        alias = self.alias_name.get().strip()
        ruta = self.alias_path.get().strip()
        if not alias or not ruta:
            return
        db.set_config(f"ACTUA_FILE_ALIAS::{alias}", ruta)
        self.aliases[alias] = ruta
        self.alias_name.set("")
        self.alias_path.set("")

    def _load_aliases(self):
        conn = db.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM app_config WHERE key LIKE 'ACTUA_FILE_ALIAS::%'")
            rows = cur.fetchall()
        finally:
            conn.close()
        self.aliases = {row[0].split("::", 1)[1]: row[1] for row in rows}

    def _go_back(self):
        if callable(self.on_close):
            self.on_close()
            return
        from gestorcompras.ui import router
        router.open_home()

    def _refresh_inbox(self):
        for item in self.inbox_tree.get_children():
            self.inbox_tree.delete(item)
        self.selected_inbox_ids.clear()
        origen = _ORIGEN_MAP.get(self.origen_var.get())
        if not origen:
            return
        for row in task_inbox.list_pending(origen):
            iid = str(row["id"])
            self.inbox_tree.insert("", tk.END, iid=iid, values=("☐", row["origen"], row["task_number"]))

    def _toggle_inbox_row(self, event):
        item = self.inbox_tree.identify_row(event.y)
        col = self.inbox_tree.identify_column(event.x)
        if not item or col != "#1":
            return
        row_id = int(item)
        if row_id in self.selected_inbox_ids:
            self.selected_inbox_ids.remove(row_id)
            mark = "☐"
        else:
            self.selected_inbox_ids.add(row_id)
            mark = "☑"
        vals = list(self.inbox_tree.item(item, "values"))
        vals[0] = mark
        self.inbox_tree.item(item, values=vals)

    def _inbox_select_all(self):
        self.selected_inbox_ids = {int(iid) for iid in self.inbox_tree.get_children()}
        for iid in self.inbox_tree.get_children():
            vals = list(self.inbox_tree.item(iid, "values"))
            vals[0] = "☑"
            self.inbox_tree.item(iid, values=vals)

    def _inbox_select_none(self):
        self.selected_inbox_ids.clear()
        for iid in self.inbox_tree.get_children():
            vals = list(self.inbox_tree.item(iid, "values"))
            vals[0] = "☐"
            self.inbox_tree.item(iid, values=vals)

    def _inbox_clear(self):
        origen = _ORIGEN_MAP.get(self.origen_var.get())
        if not origen:
            return
        task_inbox.clear(origen)
        self._refresh_inbox()

    def _run_flow(self):
        if not self.pasos:
            messagebox.showwarning("Actualizar Tareas", "Debe agregar al menos un paso.", parent=self)
            return

        origen_valor = _ORIGEN_MAP.get(self.origen_var.get())
        pending = task_inbox.list_pending(origen_valor) if origen_valor else []
        if pending and self.selected_inbox_ids:
            pending = [p for p in pending if p["id"] in self.selected_inbox_ids]
        manual_tasks = self._manual_tasks()
        manual_pending = [{"id": None, "task_number": num, "payload": {}} for num in manual_tasks]
        if _has_duplicate_task_numbers(pending + manual_pending):
            if not messagebox.askyesno(
                "Actualizar Tareas",
                "Existen tareas duplicadas, ¿desea continuar de todas formas?",
                parent=self,
            ):
                return

        self.status_var.set("Ejecutando...")
        pending_snapshot = [dict(p) for p in pending]
        manual_snapshot = [dict(m) for m in manual_pending]

        def _worker():
            driver = None
            try:
                pendientes = list(pending_snapshot)
                if not pendientes:
                    pendientes = list(manual_snapshot)
                if not pendientes:
                    raise ValueError("Debe ingresar al menos una tarea manual o seleccionar tareas de bandeja.")

                driver = _create_driver(headless=not self.mostrar_nav_var.get())
                username, password = resolve_telcos_credentials(self.email_session)
                ultimo_error = None
                for _intento in range(1, 3):
                    try:
                        login_telcos(driver, username, password)
                        ultimo_error = None
                        break
                    except Exception as exc:
                        ultimo_error = exc
                if ultimo_error is not None:
                    raise ultimo_error

                consumidas_ok: list[int] = []
                report_rows: list[dict] = []
                for row in pendientes:
                    task_number = row.get("task_number")
                    ctx = {
                        "task_number": task_number,
                        "numero_tarea": task_number,
                        "carpeta_base": self.carpeta_base_var.get().strip(),
                        "file_aliases": self.aliases,
                    }
                    ctx.update(row.get("payload") or {})

                    def on_step(n, action_id, params, _task=task_number):
                        self.after(0, lambda: self._log(f"[{_task}] Paso {n}: {action_id} {params}"))

                    ctx["on_step"] = on_step
                    try:
                        auto.ejecutar_flujo(driver, self.pasos, ctx)
                        if row.get("id"):
                            consumidas_ok.append(int(row["id"]))
                        report_rows.append({"numero_tarea": task_number, "estado": "OK", "detalle": "Completada"})
                        self.after(0, lambda t=task_number: self._log(f"✓ Tarea {t} completada"))
                    except Exception as exc:
                        report_rows.append({"numero_tarea": task_number, "estado": "ERROR", "detalle": str(exc)})
                        self.after(0, lambda t=task_number, e=exc: self._log(f"✗ Tarea {t}: {e}"))
                task_inbox.mark_consumed(consumidas_ok)
                db.set_config("ACTUA_REPORT_EMAIL", "1" if self.report_var.get() else "0")
                if self.report_var.get() and self.email_session:
                    try:
                        from gestorcompras.services.actua_reporter import send_actua_report
                        send_actua_report(
                            email_session=self.email_session,
                            origen=origen_valor or "manual",
                            flujo_nombre=self.flujo_var.get().strip() or "Flujo manual",
                            resumen=report_rows,
                        )
                        self.after(0, lambda: self._log("Reporte enviado por correo."))
                    except Exception as exc:
                        self.after(0, lambda e=exc: self._log(f"No se pudo enviar reporte: {e}"))
                self.after(0, lambda: self.status_var.set("Ejecución completada"))
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror("Actualizar Tareas", str(e), parent=self))
                self.after(0, lambda: self.status_var.set("Error durante la ejecución"))
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

        threading.Thread(target=_worker, daemon=True).start()

    def _manual_tasks(self) -> list[str]:
        raw = self.manual_tasks_text.get("1.0", tk.END)
        values = [line.strip() for line in raw.splitlines() if line.strip()]
        return values

    def _ask_text(self, title: str) -> str:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        result = tk.StringVar()
        ttk.Entry(dialog, textvariable=result, width=35).pack(padx=10, pady=8)
        ttk.Button(dialog, text="Aceptar", command=dialog.destroy).pack(pady=6)
        dialog.transient(self)
        dialog.grab_set()
        self.wait_window(dialog)
        return result.get().strip()


class ActuaExecutionPanel(tk.Toplevel):
    """Panel que muestra tareas, permite escaneo de correos, edición inline,
    eliminación, validación reactiva por flujo y ejecución con reporte."""

    def __init__(
        self,
        master: tk.Misc,
        email_session: dict[str, str],
        origen: str,
        tareas: list[dict],
        mode: str | None = None,
    ):
        super().__init__(master)
        self.title("Actualizar Tareas - Ejecutar flujo")
        self.geometry("1060x680")
        self.minsize(940, 620)
        self.transient(master.winfo_toplevel() if hasattr(master, "winfo_toplevel") else master)
        self.grab_set()
        self.email_session = email_session or {}
        self.origen = origen
        self.mode = mode
        self.tareas: list[dict] = [dict(t) for t in (tareas or [])]
        self.flujos = actua_tareas_repo.list_flujos(mode=mode)
        self.flujo_var = tk.StringVar()
        self.headless_var = tk.BooleanVar(
            value=db.get_config("ACTUA_HEADLESS", "1") != "0"
        )
        self.report_var = tk.BooleanVar(
            value=db.get_config("ACTUA_REPORT_EMAIL", "1") != "0"
        )
        self.status_var = tk.StringVar(value="Listo")
        self.validation_var = tk.StringVar(value="Seleccione un flujo para validar los datos.")
        self._running = False
        self._driver = None
        self._required: set[str] = set()
        self._columnas: list[tuple[str, str]] = []

        self._build()
        self._rebuild_columns()
        self._populate_tareas()
        self._populate_flujos()

    def _build(self) -> None:
        wrapper = ttk.Frame(self, style="MyFrame.TFrame", padding=12)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(3, weight=1)
        wrapper.rowconfigure(6, weight=1)

        header = ttk.Frame(wrapper, style="MyFrame.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Actualizar Tareas - Ejecutar flujo",
                  font=("Segoe UI", 14, "bold"), foreground="#111827").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"Origen: {self.origen}",
                  font=("Segoe UI", 10), foreground="#6B7280").grid(row=0, column=1, sticky="e")
        ttk.Separator(wrapper, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(4, 6))

        toolbar = ttk.Frame(wrapper, style="MyFrame.TFrame")
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        for txt, cmd in (
            ("Escanear correos", self._scan_emails),
            ("Agregar manual", self._add_manual),
            ("Ejecutar flujo", self._ejecutar),
            ("Editar", self._edit_task),
            ("Eliminar", self._delete_tasks),
            ("Seleccionar todo", self._select_all),
            ("Ninguno", self._select_none),
        ):
            b = ttk.Button(toolbar, text=txt, style="MyButton.TButton", command=cmd)
            b.pack(side="left", padx=3)
            add_hover_effect(b)

        tabla_frame = ttk.LabelFrame(wrapper, text="Detalle de tareas",
                                     style="MyLabelFrame.TLabelframe", padding=8)
        tabla_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 6))
        tabla_frame.columnconfigure(0, weight=3)
        tabla_frame.columnconfigure(1, weight=1)
        tabla_frame.rowconfigure(0, weight=1)

        self._tree_container = tabla_frame
        self.tree = ttk.Treeview(tabla_frame, columns=("sel",), show="headings",
                                 style="MyTreeview.Treeview")
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=0, column=0, sticky="nse")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", lambda _e: self._edit_task())
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.tag_configure("missing", foreground="#DC2626")

        self.preview = tk.Text(tabla_frame, width=30, height=8, wrap="word",
                               state="disabled", font=("Segoe UI", 9))
        self.preview.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        flow_frame = ttk.LabelFrame(wrapper, text="Flujo y opciones",
                                    style="MyLabelFrame.TLabelframe", padding=10)
        flow_frame.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        flow_frame.columnconfigure(1, weight=1)
        ttk.Label(flow_frame, text="Flujo:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
        self.flujo_combo = ttk.Combobox(flow_frame, textvariable=self.flujo_var,
                                        state="readonly", width=50)
        self.flujo_combo.grid(row=0, column=1, sticky="ew", padx=8)
        self.flujo_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_flujo_changed())

        opts = ttk.Frame(flow_frame, style="MyFrame.TFrame")
        # Mantener checks críticos visibles aunque el ancho de ventana sea reducido.
        opts.grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Checkbutton(opts, text="Mostrar navegador",
                        style="MyCheckbutton.TCheckbutton",
                        variable=self.headless_var, onvalue=False, offvalue=True).pack(side="left")
        ttk.Checkbutton(opts, text="Enviarme reporte",
                        style="MyCheckbutton.TCheckbutton",
                        variable=self.report_var).pack(side="left", padx=(8, 0))

        ttk.Label(flow_frame, textvariable=self.validation_var, style="MyLabel.TLabel",
                  wraplength=900, justify="left", foreground="#6B7280").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self.progress = ttk.Progressbar(wrapper, mode="determinate")
        self.progress.grid(row=5, column=0, sticky="ew")

        log_frame = ttk.LabelFrame(wrapper, text="Progreso",
                                   style="MyLabelFrame.TLabelframe", padding=6)
        log_frame.grid(row=6, column=0, sticky="nsew", pady=(4, 6))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = ScrolledText(log_frame, height=7, state="disabled", font=("Segoe UI", 9))
        self.log.grid(row=0, column=0, sticky="nsew")

        buttons = ttk.Frame(wrapper, style="MyFrame.TFrame")
        buttons.grid(row=7, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        ttk.Label(buttons, textvariable=self.status_var, style="MyLabel.TLabel",
                  font=("Segoe UI", 9), foreground="#6B7280").grid(row=0, column=0, sticky="w")
        self.btn_validar = ttk.Button(buttons, text="Validar datos", style="MyButton.TButton",
                                      command=self._validar)
        self.btn_validar.grid(row=0, column=1, padx=4)
        add_hover_effect(self.btn_validar)
        self.btn_ejecutar = ttk.Button(buttons, text="Ejecutar flujo", style="MyButton.TButton",
                                       command=self._ejecutar)
        self.btn_ejecutar.grid(row=0, column=2, padx=4)
        add_hover_effect(self.btn_ejecutar)
        self.btn_cerrar = ttk.Button(buttons, text="Cerrar", style="MyButton.TButton",
                                     command=self._on_close)
        self.btn_cerrar.grid(row=0, column=3, padx=4)
        add_hover_effect(self.btn_cerrar)
        self.btn_regresar_menu = ttk.Button(
            buttons,
            text="Regresar al menú",
            style="MyButton.TButton",
            command=self._close_and_return_menu,
        )
        self.btn_regresar_menu.grid(row=0, column=4, padx=4)
        add_hover_effect(self.btn_regresar_menu)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _rebuild_columns(self) -> None:
        base = [("sel", "✓", 30), ("task_number", "N° Tarea", 100)]
        extra_from_flow = [(k, k.replace("_", " ").title(), 110) for k in sorted(self._required) if k != "task_number"]
        origin_cols = _ORIGEN_COLUMNS.get(self.origen) or []
        seen = {"sel", "task_number"} | {k for k, _, _ in extra_from_flow}
        for key, label in origin_cols:
            if key not in seen:
                extra_from_flow.append((key, label, 110))
                seen.add(key)
        all_cols = base + extra_from_flow + [("estado", "Estado", 90)]
        self._columnas = [(k, lbl) for k, lbl, _ in all_cols]
        col_ids = [k for k, _, _ in all_cols]

        self.tree.configure(columns=col_ids)
        for key, lbl, w in all_cols:
            self.tree.heading(key, text=lbl)
            self.tree.column(key, width=w, anchor="center" if key in ("sel", "estado") else "w")

    def _populate_tareas(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for idx, task in enumerate(self.tareas):
            vals = self._task_row_values(task, "Pendiente")
            tags = self._missing_tag(task)
            self.tree.insert("", "end", iid=str(idx), values=vals, tags=tags)

    def _task_row_values(self, task: dict, estado: str) -> list[str]:
        return ["☐"] + [_task_value(task, k) for k, _ in self._columnas if k not in ("sel", "estado")] + [estado]

    def _missing_tag(self, task: dict) -> tuple[str, ...]:
        if not self._required:
            return ()
        for k in self._required:
            if not _task_value(task, k).strip():
                return ("missing",)
        return ()

    def _set_estado(self, idx: int, estado: str) -> None:
        iid = str(idx)
        def _apply():
            if not self.tree.exists(iid):
                return
            vals = list(self.tree.item(iid, "values"))
            vals[-1] = estado
            self.tree.item(iid, values=vals)
        try:
            self.after(0, _apply)
        except tk.TclError:
            pass

    def _log_msg(self, msg: str) -> None:
        def _append():
            self.log.configure(state="normal")
            self.log.insert(tk.END, msg + "\n")
            self.log.see(tk.END)
            self.log.configure(state="disabled")
        try:
            self.after(0, _append)
        except tk.TclError:
            pass

    def _on_tree_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != "#1":
            return
        vals = list(self.tree.item(item, "values"))
        vals[0] = "☑" if vals[0] == "☐" else "☐"
        self.tree.item(item, values=vals)

    def _on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self.tareas):
            task = self.tareas[idx]
            body = task.get("_email_body") or task.get("body", "")
            if not body:
                body = "\n".join(f"{k}: {v}" for k, v in task.items()
                                 if k not in ("_email_body", "body", "_db_id", "_created_at"))
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.insert("1.0", body[:3000])
            self.preview.configure(state="disabled")

    def _select_all(self) -> None:
        for iid in self.tree.get_children():
            vals = list(self.tree.item(iid, "values"))
            vals[0] = "☑"
            self.tree.item(iid, values=vals)

    def _select_none(self) -> None:
        for iid in self.tree.get_children():
            vals = list(self.tree.item(iid, "values"))
            vals[0] = "☐"
            self.tree.item(iid, values=vals)

    def _selected_indices(self) -> list[int]:
        return [int(iid) for iid in self.tree.get_children()
                if self.tree.item(iid, "values")[0] == "☑"]

    def _scan_emails(self) -> None:
        from gestorcompras.ui.actua_scan_dialog import ScanEmailDialog
        dialog = ScanEmailDialog(self, self.email_session)
        self.wait_window(dialog)
        if dialog.result:
            for item in dialog.result:
                task = dict(item)
                task["_email_body"] = item.get("body", "")
                self.tareas.append(task)
            self._rebuild_columns()
            self._populate_tareas()
            self._validar(silent=True)

    def _add_manual(self) -> None:
        from gestorcompras.ui.actua_task_editor import TaskEditDialog
        task: dict = {}
        dialog = TaskEditDialog(self, task, required_keys=self._required)
        self.wait_window(dialog)
        if dialog.saved and task.get("task_number"):
            self.tareas.append(task)
            self._rebuild_columns()
            self._populate_tareas()
            self._validar(silent=True)

    def _edit_task(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.tareas):
            return
        from gestorcompras.ui.actua_task_editor import TaskEditDialog
        task = self.tareas[idx]
        dialog = TaskEditDialog(self, task, required_keys=self._required)
        self.wait_window(dialog)
        if dialog.saved:
            self._rebuild_columns()
            self._populate_tareas()
            self._validar(silent=True)

    def _delete_tasks(self) -> None:
        indices = self._selected_indices()
        if not indices:
            messagebox.showinfo("Actualizar Tareas", "Seleccione tareas para eliminar.", parent=self)
            return
        if not messagebox.askyesno("Confirmar", f"¿Eliminar {len(indices)} tarea(s)?", parent=self):
            return
        for idx in sorted(indices, reverse=True):
            if idx < len(self.tareas):
                self.tareas.pop(idx)
        self._populate_tareas()
        self._validar(silent=True)

    def _populate_flujos(self) -> None:
        nombres = [f"{f['nombre']} (#{f['id']})" for f in self.flujos]
        self.flujo_combo.configure(values=nombres)
        if nombres:
            self.flujo_var.set(nombres[0])
            self._on_flujo_changed()
        else:
            self.validation_var.set("No hay flujos guardados. Cree uno desde 'Actualizar Tareas'.")
            self.btn_ejecutar.configure(state="disabled")
            self.btn_validar.configure(state="disabled")

    def _current_flujo(self) -> dict | None:
        valor = self.flujo_var.get()
        if not valor:
            return None
        try:
            idx = [f"{f['nombre']} (#{f['id']})" for f in self.flujos].index(valor)
        except ValueError:
            return None
        return self.flujos[idx]

    def _on_flujo_changed(self) -> None:
        flujo = self._current_flujo()
        if flujo:
            pasos = flujo.get("pasos") or []
            self._required = _required_keys_for_flow(pasos)
        else:
            self._required = set()
        self._rebuild_columns()
        self._populate_tareas()
        self._validar(silent=True)

    def _validar(self, silent: bool = False) -> bool:
        flujo = self._current_flujo()
        if not flujo:
            self.validation_var.set("Seleccione un flujo válido.")
            return False
        pasos = flujo.get("pasos") or []
        required = _required_keys_for_flow(pasos)
        if not required:
            self.validation_var.set(f"Flujo '{flujo['nombre']}' listo. No requiere datos adicionales.")
            return True

        n_missing = 0
        faltantes_por_tarea: list[str] = []
        for task in self.tareas:
            missing = [k for k in required if not _task_value(task, k).strip()]
            if missing:
                n_missing += 1
                task_num = task.get("task_number") or "?"
                faltantes_por_tarea.append(f"Tarea {task_num}: faltan {', '.join(missing)}")

        if faltantes_por_tarea:
            resumen = (
                f"Flujo '{flujo['nombre']}' requiere: {', '.join(sorted(required))}.\n"
                + "\n".join(faltantes_por_tarea[:6])
            )
            if len(faltantes_por_tarea) > 6:
                resumen += f"\n...y {len(faltantes_por_tarea) - 6} tareas mas."
            self.validation_var.set(resumen)
            if not silent:
                messagebox.showwarning("Validacion", f"{n_missing} tarea(s) con campos faltantes.", parent=self)
            return False

        self.validation_var.set(f"Flujo '{flujo['nombre']}' validado. Requiere: {', '.join(sorted(required))}.")
        return True

    def _ejecutar(self) -> None:
        if self._running:
            return
        if not self.tareas:
            messagebox.showwarning("Actualizar Tareas", "No hay tareas para ejecutar.", parent=self)
            return
        flujo = self._current_flujo()
        if not flujo:
            messagebox.showwarning("Actualizar Tareas", "Seleccione un flujo.", parent=self)
            return
        if not self._validar(silent=True):
            n_missing = sum(1 for t in self.tareas
                           if any(not _task_value(t, k).strip() for k in self._required))
            if not messagebox.askyesno(
                "Validacion",
                f"Hay {n_missing} tarea(s) con campos faltantes. ¿Continuar?",
                parent=self,
            ):
                return
        if _has_duplicate_task_numbers(self.tareas):
            if not messagebox.askyesno(
                "Actualizar Tareas",
                "Existen tareas duplicadas, ¿desea continuar de todas formas?",
                parent=self,
            ):
                return

        db.set_config("ACTUA_HEADLESS", "1" if self.headless_var.get() else "0")
        db.set_config("ACTUA_REPORT_EMAIL", "1" if self.report_var.get() else "0")

        self._running = True
        self.btn_ejecutar.configure(state="disabled")
        self.btn_validar.configure(state="disabled")
        self.flujo_combo.configure(state="disabled")
        self.status_var.set("Ejecutando...")
        self.progress.configure(maximum=len(self.tareas), value=0)

        pasos = flujo.get("pasos") or []
        flujo_nombre = flujo.get("nombre", "?")
        headless = bool(self.headless_var.get())
        send_report = self.report_var.get()
        tareas_snapshot = [dict(t) for t in self.tareas]

        thread = threading.Thread(
            target=self._worker,
            args=(pasos, tareas_snapshot, headless, flujo_nombre, send_report),
            daemon=True,
        )
        thread.start()

    def _worker(
        self,
        pasos: list[dict],
        tareas: list[dict],
        headless: bool,
        flujo_nombre: str,
        send_report: bool,
    ) -> None:
        exitos = 0
        fallos = 0
        resultados: list[dict] = []
        try:
            try:
                self._driver = _create_driver(headless=headless)
            except Exception as exc:
                self._log_msg(f"No se pudo iniciar el navegador: {exc}")
                self.after(0, lambda: self.status_var.set("Error iniciando navegador"))
                return

            try:
                username, password = resolve_telcos_credentials(self.email_session)
                self._log_msg(f"Iniciando sesion en Telcos como {username}...")
                ultimo_error = None
                for intento in range(1, 3):
                    try:
                        login_telcos(self._driver, username, password)
                        ultimo_error = None
                        break
                    except Exception as exc:
                        ultimo_error = exc
                        self._log_msg(
                            f"Intento {intento}/2 de inicio de sesion falló: {exc}"
                        )
                if ultimo_error is not None:
                    raise ultimo_error
            except Exception as exc:
                self._log_msg(f"Fallo inicio de sesion: {exc}")
                self.after(0, lambda: self.status_var.set("Error autenticando"))
                return

            for idx, task in enumerate(tareas):
                task_number = str(task.get("task_number") or "")
                self._set_estado(idx, "En ejecucion")
                self._log_msg(f"-> Tarea {task_number or '(sin numero)'} ({idx + 1}/{len(tareas)})")
                ctx = {
                    "task_number": task_number,
                    "numero_tarea": task_number,
                    "carpeta_base": actua_tareas_repo.get_carpeta_base(""),
                    "file_aliases": {},
                }
                for k, v in task.items():
                    if k in ("task_number", "_email_body", "body", "_db_id", "_created_at"):
                        continue
                    if isinstance(v, (list, tuple)):
                        ctx[k] = ", ".join(str(x) for x in v if x)
                    elif v is not None:
                        ctx[k] = v

                def on_step(n, action_id, params, _t=task_number):
                    self._log_msg(f"   [{_t}] Paso {n}: {action_id} {params}")

                ctx["on_step"] = on_step
                try:
                    auto.ejecutar_flujo(self._driver, pasos, ctx)
                    exitos += 1
                    self._set_estado(idx, "OK")
                    self._log_msg(f"OK Tarea {task_number} completada")
                    resultados.append({"task_number": task_number, "status": "ok", "mensaje": "Completada", "campos": {k: v for k, v in ctx.items() if k not in ("on_step", "file_aliases", "carpeta_base")}})
                except Exception as exc:
                    fallos += 1
                    self._set_estado(idx, f"Error: {exc}")
                    self._log_msg(f"ERROR Tarea {task_number}: {exc}")
                    resultados.append({"task_number": task_number, "status": "error", "mensaje": str(exc), "campos": {}})
                self.after(0, lambda v=idx + 1: self.progress.configure(value=v))

            resumen = f"Finalizado. {exitos} exitosas / {fallos} con error."
            self.after(0, lambda: self.status_var.set(resumen))
            self._log_msg(resumen)

            if send_report and self.email_session:
                try:
                    from gestorcompras.services.actua_reporter import send_actua_report
                    sent = send_actua_report(
                        self.email_session, flujo_nombre, resultados, headless
                    )
                    if sent:
                        self._log_msg("Reporte enviado por correo.")
                    else:
                        self._log_msg("No se pudo enviar el reporte por correo.")
                except Exception as exc:
                    logger.exception("Error enviando reporte")
                    self._log_msg(f"Error al enviar reporte: {exc}")
        finally:
            if self._driver is not None:
                try:
                    self._driver.quit()
                except Exception:
                    pass
                self._driver = None
            self._running = False
            self.after(0, lambda: self.btn_ejecutar.configure(state="normal"))
            self.after(0, lambda: self.btn_validar.configure(state="normal"))
            self.after(0, lambda: self.flujo_combo.configure(state="readonly"))

    def _on_close(self) -> None:
        if self._running:
            if not messagebox.askyesno("Actualizar Tareas", "Hay ejecucion en curso. ¿Cerrar?", parent=self):
                return
        try:
            self.grab_release()
        except Exception:
            pass
        global _OPEN_ACTUA_PANEL
        _OPEN_ACTUA_PANEL = None
        self.destroy()

    def _close_and_return_menu(self) -> None:
        self._on_close()
        try:
            from gestorcompras.ui import router

            router.open_home()
        except Exception:
            logger.exception("No se pudo regresar al menú tras cerrar Actualizar Tareas.")


def abrir_panel_tareas(
    master: tk.Misc,
    email_session: dict[str, str],
    origen: str,
    tareas: list[dict],
    mode: str | None = None,
) -> ActuaExecutionPanel | None:
    """Abre el panel unificado de Actua. Tareas. Si ``tareas`` viene vacío el
    usuario puede escanear correos o agregar manualmente desde el panel."""
    global _OPEN_ACTUA_PANEL
    if _OPEN_ACTUA_PANEL is not None and _OPEN_ACTUA_PANEL.winfo_exists():
        try:
            _OPEN_ACTUA_PANEL.lift()
            _OPEN_ACTUA_PANEL.focus_force()
        except Exception:
            pass
        return _OPEN_ACTUA_PANEL

    panel = ActuaExecutionPanel(master, email_session, origen, tareas or [], mode=mode)
    _OPEN_ACTUA_PANEL = panel
    return panel


def open_actua_tareas_window(
    master: tk.Misc,
    email_session: dict[str, str],
    origin: str = "bienes",
) -> tk.Toplevel:
    """Abre Actualizar Tareas como ventana independiente (consistente con otros módulos)."""
    from gestorcompras.ui import router

    win = tk.Toplevel(master)
    win.title("Actualizar Tareas")
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    width = min(1120, max(980, screen_w - 80))
    height = min(760, max(620, screen_h - 120))
    pos_x = max(0, (screen_w - width) // 2)
    pos_y = max(0, (screen_h - height) // 2)
    win.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
    win.minsize(940, 620)
    win.transient(master.winfo_toplevel() if hasattr(master, "winfo_toplevel") else master)

    def _cerrar() -> None:
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()
        try:
            router.open_home()
        except Exception:
            logger.exception("No se pudo volver al menú al cerrar Actualizar Tareas.")

    win.protocol("WM_DELETE_WINDOW", _cerrar)
    screen = ActuaTareasScreen(win, email_session, origin=origin, on_close=_cerrar)
    screen.pack(fill="both", expand=True)
    win.grab_set()
    win.focus_force()
    return win


def ejecutar_flujo_desde_modulo(
    master: tk.Misc,
    email_session: dict[str, str],
    origen: str,
    tareas: list[dict],
    mode: str | None = None,
) -> None:
    """Compatibilidad hacia atrás: delega en ``abrir_panel_tareas``."""
    abrir_panel_tareas(master, email_session, origen, tareas, mode=mode)


def run_flow_from_inbox(
    master: tk.Misc,
    email_session: dict[str, str],
    origen: str,
    flujo_id: int,
    headless: bool = True,
) -> None:
    """Ejecuta el flujo ``flujo_id`` sobre las tareas pendientes en bandeja
    sin requerir interacción del usuario. Es un atajo pensado para flujos
    automatizados: honra los parámetros ``flujo_id`` y ``headless`` y no abre
    el selector interactivo."""
    flujo = actua_tareas_repo.load_flujo(flujo_id)
    if not flujo:
        messagebox.showerror("Actualizar Tareas", "Flujo no encontrado", parent=master)
        return
    pend = task_inbox.list_pending(origen)
    if not pend:
        messagebox.showinfo(
            "Actualizar Tareas", "No hay tareas pendientes en bandeja.", parent=master
        )
        return

    modal = tk.Toplevel(master)
    modal.title(f"Ejecutando flujo Actualizar Tareas ({flujo.get('nombre', flujo_id)})")
    txt = ScrolledText(modal, width=90, height=18, state="disabled")
    txt.pack(fill="both", expand=True, padx=8, pady=8)
    progress = ttk.Progressbar(modal, mode="determinate", maximum=len(pend))
    progress.pack(fill="x", padx=8, pady=(0, 8))

    def log(msg: str) -> None:
        def _append():
            txt.configure(state="normal")
            txt.insert(tk.END, msg + "\n")
            txt.see(tk.END)
            txt.configure(state="disabled")

        try:
            modal.after(0, _append)
        except tk.TclError:
            pass

    def _worker():
        driver = None
        ids_ok: list[int] = []
        pasos = flujo.get("pasos") or []
        try:
            try:
                driver = _create_driver(headless=headless)
            except Exception as exc:
                log(f"No se pudo iniciar el navegador: {exc}")
                return

            try:
                username, password = resolve_telcos_credentials(email_session)
                log(f"Iniciando sesión en Telcos como {username}…")
                login_telcos(driver, username, password)
            except Exception as exc:
                log(f"Fallo en el inicio de sesión: {exc}")
                return

            for i, row in enumerate(pend, start=1):
                task_number = row.get("task_number")
                log(f"[{i}/{len(pend)}] Tarea {task_number}")
                ctx = {"task_number": task_number, "numero_tarea": task_number}
                ctx.update(row.get("payload") or {})
                try:
                    auto.ejecutar_flujo(driver, pasos, ctx)
                    if row.get("id") is not None:
                        ids_ok.append(int(row["id"]))
                    log(f"✓ Tarea {task_number} completada")
                except Exception as exc:
                    log(f"✗ Tarea {task_number}: {exc}")
                try:
                    modal.after(0, lambda v=i: progress.configure(value=v))
                except tk.TclError:
                    pass

            if ids_ok:
                task_inbox.mark_consumed(ids_ok)
            log(f"Finalizado. {len(ids_ok)} tarea(s) marcada(s) como consumida(s).")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    threading.Thread(target=_worker, daemon=True).start()
