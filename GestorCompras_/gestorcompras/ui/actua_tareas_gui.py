from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from gestorcompras.services import actua_tareas_automation as auto
from gestorcompras.services import actua_tareas_repo, db, task_inbox
from gestorcompras.services.reassign_bridge import _create_driver
from gestorcompras.services.telcos_automation import login_telcos
from gestorcompras.ui.common import add_hover_effect

_ORIGEN_MAP = {
    "Manual": None,
    "Desde Reasignación": "reasignacion",
    "Desde Descargas OC": "descargas_oc",
    "Desde Correos Masivos": "correos_masivos",
}


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
    def __init__(self, master: tk.Misc, email_session: dict[str, str], origin: str):
        super().__init__(master, style="MyFrame.TFrame")
        self.master = master
        self.email_session = email_session
        self.origin = origin
        self.pasos: list[dict] = []
        self.flujos: list[dict] = []
        self.aliases: dict[str, str] = {}
        self.selected_inbox_ids: set[int] = set()

        self.nombre_flujo = tk.StringVar()
        self.flujo_var = tk.StringVar()
        self.task_default_var = tk.StringVar()
        self.carpeta_base_var = tk.StringVar(value=actua_tareas_repo.get_carpeta_base(""))
        self.mostrar_nav_var = tk.BooleanVar(value=True)
        self.origen_var = tk.StringVar(value="Manual")
        self.status_var = tk.StringVar(value="Listo")
        self.action_help_var = tk.StringVar(value="Seleccione una acción para ver su descripción.")

        self._build()
        self._load_aliases()
        self._refresh_flujos()

    def _build(self):
        self.columnconfigure(1, weight=1)
        # La fila de "Flujo/Acciones" debe conservar altura visible;
        # de lo contrario el bloque de ejecución puede colapsarla.
        self.rowconfigure(2, weight=1, minsize=230)
        self.rowconfigure(3, weight=0)

        head = ttk.Frame(self, style="MyFrame.TFrame", padding=10)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(head, text="Actua. Tareas", style="Banner.TLabel").grid(row=0, column=0, sticky="w")

        self.flujo_combo = ttk.Combobox(head, textvariable=self.flujo_var, state="readonly", width=35)
        self.flujo_combo.grid(row=0, column=1, padx=8)
        self.flujo_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_selected_flujo())

        for i, (txt, cmd) in enumerate([
            ("Nuevo flujo", self._nuevo_flujo),
            ("Guardar", self._guardar_flujo),
            ("Eliminar", self._eliminar_flujo),
        ]):
            b = ttk.Button(head, text=txt, style="MyButton.TButton", command=cmd)
            b.grid(row=0, column=2 + i, padx=4)
            add_hover_effect(b)

        source_frame = ttk.LabelFrame(self, text="Origen de tareas", style="MyLabelFrame.TLabelframe", padding=8)
        source_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        ttk.Combobox(
            source_frame,
            textvariable=self.origen_var,
            values=list(_ORIGEN_MAP.keys()),
            state="readonly",
            width=28,
        ).grid(row=0, column=0, sticky="w")
        source_frame.bind("<<ComboboxSelected>>", lambda _e: self._refresh_inbox())
        self.origen_var.trace_add("write", lambda *_: self._refresh_inbox())

        btn_all = ttk.Button(source_frame, text="Seleccionar todo", command=self._inbox_select_all)
        btn_none = ttk.Button(source_frame, text="Ninguno", command=self._inbox_select_none)
        btn_clear = ttk.Button(source_frame, text="Limpiar bandeja", command=self._inbox_clear)
        btn_all.grid(row=0, column=1, padx=5)
        btn_none.grid(row=0, column=2, padx=5)
        btn_clear.grid(row=0, column=3, padx=5)

        self.inbox_tree = ttk.Treeview(source_frame, columns=("sel", "origen", "task"), show="headings", height=4)
        for col, txt, w in (("sel", "✓", 35), ("origen", "Origen", 130), ("task", "Tarea", 130)):
            self.inbox_tree.heading(col, text=txt)
            self.inbox_tree.column(col, width=w, anchor="center")
        self.inbox_tree.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        self.inbox_tree.bind("<Button-1>", self._toggle_inbox_row)

        left = ttk.LabelFrame(self, text="Acciones", style="MyLabelFrame.TLabelframe", padding=8)
        left.grid(row=2, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
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
                act_container,
                text=accion["label"],
                style="MyButton.TButton",
                command=lambda a=accion: self._agregar_paso(a),
            )
            btn.grid(row=i, column=0, sticky="ew", pady=3, padx=(0, 4))
            add_hover_effect(btn)
            descripcion = accion.get("descripcion", "")
            ActionTooltip(btn, descripcion)
            btn.bind("<Enter>", lambda _e, d=descripcion: self.action_help_var.set(d), add="+")

        ttk.Label(
            left,
            textvariable=self.action_help_var,
            style="MyLabel.TLabel",
            wraplength=360,
            justify="left",
        ).pack(fill="x", padx=4, pady=(4, 0))

        right = ttk.LabelFrame(self, text="Flujo", style="MyLabelFrame.TLabelframe", padding=8)
        right.grid(row=2, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(right, columns=("n", "accion", "params"), show="headings", height=8)
        self.tree.heading("n", text="#")
        self.tree.heading("accion", text="Acción")
        self.tree.heading("params", text="Parámetros")
        self.tree.column("n", width=40, anchor="center")
        self.tree.column("accion", width=260)
        self.tree.column("params", width=320)
        self.tree.grid(row=0, column=0, sticky="nsew")

        actions_row = ttk.Frame(right, style="MyFrame.TFrame")
        actions_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        for txt, cmd in (("↑", self._move_up), ("↓", self._move_down), ("✎", self._edit_step), ("✖", self._del_step)):
            b = ttk.Button(actions_row, text=txt, command=cmd, width=4)
            b.pack(side="left", padx=3)

        bottom = ttk.LabelFrame(self, text="Ejecución", style="MyLabelFrame.TLabelframe", padding=8)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ttk.Label(bottom, text="N° tarea manual:", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(bottom, textvariable=self.task_default_var, width=20).grid(row=0, column=1, padx=4)
        ttk.Label(bottom, text="Carpeta base:", style="MyLabel.TLabel").grid(row=0, column=2, padx=(10, 0), sticky="w")
        ttk.Entry(bottom, textvariable=self.carpeta_base_var, width=40).grid(row=0, column=3, padx=4)
        ttk.Button(bottom, text="Examinar…", command=self._pick_folder).grid(row=0, column=4)

        ttk.Checkbutton(bottom, text="Mostrar navegador al ejecutar", variable=self.mostrar_nav_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(bottom, textvariable=self.status_var, style="MyLabel.TLabel").grid(row=1, column=2, columnspan=3, sticky="w")

        self.log = ScrolledText(bottom, height=5, state="disabled")
        self.log.grid(row=2, column=0, columnspan=5, sticky="ew", pady=4)

        run_btn = ttk.Button(bottom, text="Ejecutar flujo", style="MyButton.TButton", command=self._run_flow)
        run_btn.grid(row=3, column=3, sticky="e", pady=5)
        add_hover_effect(run_btn)
        back_btn = ttk.Button(bottom, text="◀ Regresar", style="MyButton.TButton", command=self._go_back)
        back_btn.grid(row=3, column=4, sticky="e", padx=6)
        add_hover_effect(back_btn)

        alias_frame = ttk.LabelFrame(bottom, text="Alias de archivos", style="MyLabelFrame.TLabelframe", padding=6)
        alias_frame.grid(row=4, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        self.alias_name = tk.StringVar()
        self.alias_path = tk.StringVar()
        ttk.Entry(alias_frame, textvariable=self.alias_name, width=20).grid(row=0, column=0, padx=4)
        ttk.Entry(alias_frame, textvariable=self.alias_path, width=50).grid(row=0, column=1, padx=4)
        ttk.Button(alias_frame, text="...", command=self._pick_alias_folder).grid(row=0, column=2)
        ttk.Button(alias_frame, text="Guardar alias", command=self._save_alias).grid(row=0, column=3, padx=4)

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
                "Actua. Tareas",
                "Esta acción es un botón y no contiene texto.",
                parent=self,
            )
            return

        win = tk.Toplevel(self)
        win.title(f"Editar: {meta['label']}")
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
        messagebox.showinfo("Actua. Tareas", "Flujo guardado correctamente.", parent=self)

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
        elif nombres:
            self.flujo_var.set(nombres[0])
        else:
            self.flujo_var.set("")

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
        from gestorcompras.ui import router

        if self.origin == "servicios":
            router.open_servicios_menu()
        else:
            router.open_bienes_menu()

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
            messagebox.showwarning("Actua. Tareas", "Debe agregar al menos un paso.", parent=self)
            return
        self.status_var.set("Ejecutando...")

        def _worker():
            try:
                pending = task_inbox.list_pending(_ORIGEN_MAP.get(self.origen_var.get())) if _ORIGEN_MAP.get(self.origen_var.get()) else []
                if pending and self.selected_inbox_ids:
                    pending = [p for p in pending if p["id"] in self.selected_inbox_ids]
                if not pending:
                    pending = [{"id": None, "task_number": self.task_default_var.get().strip(), "payload": {}}]

                driver = _create_driver(headless=not self.mostrar_nav_var.get())
                try:
                    username = (self.email_session.get("address") or "").split("@")[0]
                    password = self.email_session.get("password") or ""
                    login_telcos(driver, username, password)

                    consumidas_ok: list[int] = []
                    for row in pending:
                        ctx = {
                            "task_number": row.get("task_number"),
                            "numero_tarea": row.get("task_number"),
                            "carpeta_base": self.carpeta_base_var.get().strip(),
                            "file_aliases": self.aliases,
                        }
                        ctx.update(row.get("payload") or {})

                        def on_step(n, action_id, params):
                            self.after(0, lambda: self._log(f"[{row.get('task_number')}] Paso {n}: {action_id} {params}"))

                        ctx["on_step"] = on_step
                        auto.ejecutar_flujo(driver, self.pasos, ctx)
                        if row.get("id"):
                            consumidas_ok.append(int(row["id"]))
                    task_inbox.mark_consumed(consumidas_ok)
                    self.after(0, lambda: self.status_var.set("Ejecución completada"))
                finally:
                    driver.quit()
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Actua. Tareas", str(exc), parent=self))
                self.after(0, lambda: self.status_var.set("Error durante la ejecución"))

        threading.Thread(target=_worker, daemon=True).start()

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


def run_flow_from_inbox(master: tk.Misc, email_session: dict[str, str], origen: str, flujo_id: int) -> None:
    flujo = actua_tareas_repo.load_flujo(flujo_id)
    if not flujo:
        messagebox.showerror("Actua. Tareas", "Flujo no encontrado", parent=master)
        return

    modal = tk.Toplevel(master)
    modal.title("Ejecutando flujo Actua. Tareas")
    txt = ScrolledText(modal, width=90, height=20)
    txt.pack(fill="both", expand=True, padx=8, pady=8)
    progress = ttk.Progressbar(modal, mode="determinate")
    progress.pack(fill="x", padx=8, pady=(0, 8))

    def log(msg: str):
        txt.after(0, lambda: (txt.insert(tk.END, msg + "\n"), txt.see(tk.END)))

    def _worker():
        pend = task_inbox.list_pending(origen)
        if not pend:
            log("No hay tareas pendientes en bandeja.")
            return
        progress.after(0, lambda: progress.configure(maximum=len(pend), value=0))
        ids_ok = []
        driver = _create_driver(headless=True)
        try:
            username = (email_session.get("address") or "").split("@")[0]
            login_telcos(driver, username, email_session.get("password") or "")
            for i, row in enumerate(pend, start=1):
                log(f"Iniciando tarea {i}/{len(pend)}: {row['task_number']}")
                ctx = {"task_number": row["task_number"]}
                ctx.update(row.get("payload") or {})
                auto.ejecutar_flujo(driver, flujo.get("pasos") or [], ctx)
                ids_ok.append(row["id"])
                progress.after(0, lambda v=i: progress.configure(value=v))
                log(f"✓ {row['task_number']}")
            task_inbox.mark_consumed(ids_ok)
            log("Finalizado")
        except Exception as exc:
            log(f"Error: {exc}")
        finally:
            driver.quit()

    threading.Thread(target=_worker, daemon=True).start()


def seleccionar_flujo_guardado(master: tk.Misc, mode: str | None = None) -> int | None:
    flujos = actua_tareas_repo.list_flujos(mode=mode)
    if not flujos:
        messagebox.showwarning("Actua. Tareas", "No existen flujos guardados.", parent=master)
        return None

    dialog = tk.Toplevel(master)
    dialog.title("Seleccionar flujo de Actua. Tareas")
    dialog.transient(master)
    dialog.grab_set()

    ttk.Label(dialog, text="Seleccione el flujo a ejecutar:", style="MyLabel.TLabel").pack(padx=10, pady=(10, 4))
    opciones = [f"{f['nombre']} (#{f['id']})" for f in flujos]
    selected = tk.StringVar(value=opciones[0])
    combo = ttk.Combobox(dialog, values=opciones, textvariable=selected, state="readonly", width=45)
    combo.pack(padx=10, pady=6)

    result: dict[str, int | None] = {"id": None}

    def _ok():
        idx = opciones.index(selected.get())
        result["id"] = int(flujos[idx]["id"])
        dialog.destroy()

    ttk.Button(dialog, text="Cancelar", command=dialog.destroy).pack(side="right", padx=10, pady=10)
    ttk.Button(dialog, text="Aceptar", command=_ok).pack(side="right", pady=10)
    master.wait_window(dialog)
    return result["id"]
