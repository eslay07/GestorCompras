"""Diálogo para escanear correos y extraer datos de tareas."""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from zoneinfo import ZoneInfo

from gestorcompras.services import db
from gestorcompras.services.email_task_scanner import scan_inbox
from gestorcompras.ui.common import add_hover_effect

TZ = ZoneInfo("America/Guayaquil")
_DATE_FMT = "%Y-%m-%d %H:%M"


class ScanEmailDialog(tk.Toplevel):
    """Permite buscar correos IMAP por rango de fecha, remitente y números de tarea."""

    def __init__(self, master: tk.Misc, email_session: dict[str, str]):
        super().__init__(master)
        self.title("Escanear correos - Actualizar Tareas")
        self.geometry("900x560")
        self.transient(master.winfo_toplevel() if hasattr(master, "winfo_toplevel") else master)
        self.grab_set()
        self.email_session = email_session
        self.result: list[dict] = []
        self._items: list[dict] = []
        self._selected: set[int] = set()

        ahora = datetime.now(TZ)
        hace_24h = ahora - timedelta(hours=24)
        self.desde_var = tk.StringVar(value=hace_24h.strftime(_DATE_FMT))
        self.hasta_var = tk.StringVar(value=ahora.strftime(_DATE_FMT))
        self.remitente_var = tk.StringVar(value=db.get_config("ACTUA_REMITENTE", ""))
        self.asunto_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ingrese filtros y presione Buscar.")

        self._build()

    def _build(self) -> None:
        wrapper = ttk.Frame(self, padding=10)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(1, weight=1)
        wrapper.rowconfigure(4, weight=1)

        ttk.Label(wrapper, text="Desde:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(wrapper, textvariable=self.desde_var, width=22).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(wrapper, text="Hasta:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Entry(wrapper, textvariable=self.hasta_var, width=22).grid(row=0, column=3, sticky="w", padx=4)

        ttk.Label(wrapper, text="Remitente:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(wrapper, textvariable=self.remitente_var, width=40).grid(row=1, column=1, columnspan=2, sticky="ew", padx=4)

        ttk.Label(wrapper, text="Asunto contiene:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(wrapper, textvariable=self.asunto_var, width=40).grid(row=2, column=1, columnspan=2, sticky="ew", padx=4)

        ttk.Label(wrapper, text="N° tareas (1 por línea, vacío=todos):").grid(row=3, column=0, sticky="nw", pady=2)
        self.tasks_text = tk.Text(wrapper, height=3, width=30)
        self.tasks_text.grid(row=3, column=1, columnspan=2, sticky="ew", padx=4, pady=2)

        btn_buscar = ttk.Button(wrapper, text="Buscar", command=self._buscar)
        btn_buscar.grid(row=0, column=4, rowspan=2, padx=8, sticky="ns")
        add_hover_effect(btn_buscar)

        results_frame = ttk.LabelFrame(wrapper, text="Resultados", padding=6)
        results_frame.grid(row=4, column=0, columnspan=5, sticky="nsew", pady=(6, 0))
        results_frame.columnconfigure(0, weight=3)
        results_frame.columnconfigure(1, weight=1)
        results_frame.rowconfigure(0, weight=1)

        cols = ("sel", "fecha", "task_number", "proveedor", "factura", "oc", "asunto")
        self.tree = ttk.Treeview(results_frame, columns=cols, show="headings", height=10)
        for c, txt, w in (
            ("sel", "✓", 30), ("fecha", "Fecha", 110), ("task_number", "Tarea", 90),
            ("proveedor", "Proveedor", 130), ("factura", "Factura", 100),
            ("oc", "OC", 60), ("asunto", "Asunto", 250),
        ):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="center" if c == "sel" else "w")
        scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=0, sticky="nse")
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        self.preview = tk.Text(results_frame, width=30, height=10, wrap="word", state="disabled")
        self.preview.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        bottom = ttk.Frame(wrapper)
        bottom.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

        btn_all = ttk.Button(bottom, text="Seleccionar todo", command=self._select_all)
        btn_all.grid(row=0, column=1, padx=4)
        btn_none = ttk.Button(bottom, text="Ninguno", command=self._select_none)
        btn_none.grid(row=0, column=2, padx=4)
        btn_import = ttk.Button(bottom, text="Importar seleccionadas", command=self._importar)
        btn_import.grid(row=0, column=3, padx=4)
        add_hover_effect(btn_import)
        btn_cancel = ttk.Button(bottom, text="Cancelar", command=self.destroy)
        btn_cancel.grid(row=0, column=4, padx=4)

    def _buscar(self) -> None:
        try:
            desde = datetime.strptime(self.desde_var.get().strip(), _DATE_FMT).replace(tzinfo=TZ)
            hasta = datetime.strptime(self.hasta_var.get().strip(), _DATE_FMT).replace(tzinfo=TZ)
        except ValueError:
            messagebox.showerror("Error", f"Formato de fecha inválido. Use {_DATE_FMT}", parent=self)
            return

        remitente = self.remitente_var.get().strip()
        if remitente:
            db.set_config("ACTUA_REMITENTE", remitente)
        asunto = self.asunto_var.get().strip()
        raw_tasks = self.tasks_text.get("1.0", tk.END)
        task_numbers = [l.strip() for l in raw_tasks.splitlines() if l.strip()] or None

        self.status_var.set("Buscando correos...")
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        self._selected.clear()

        def _worker():
            try:
                items = scan_inbox(
                    self.email_session, desde, hasta,
                    task_numbers=task_numbers,
                    remitente=remitente,
                    asunto_contiene=asunto,
                )
                self.after(0, lambda: self._show_results(items))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_error(e))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_results(self, items: list[dict]) -> None:
        self._items = items
        self.tree.delete(*self.tree.get_children())
        self._selected.clear()
        for idx, item in enumerate(items):
            fecha = item.get("fecha")
            fecha_str = fecha.strftime("%Y-%m-%d %H:%M") if hasattr(fecha, "strftime") else str(fecha or "")
            self.tree.insert("", "end", iid=str(idx), values=(
                "☐", fecha_str, item.get("task_number", ""),
                item.get("proveedor", ""), item.get("factura", ""),
                item.get("oc", ""), item.get("asunto", ""),
            ))
        self.status_var.set(f"{len(items)} correo(s) encontrado(s).")

    def _on_error(self, exc: Exception) -> None:
        self.status_var.set("Error al buscar correos.")
        messagebox.showerror("Error", str(exc), parent=self)

    def _on_click(self, event) -> None:
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != "#1":
            return
        idx = int(item)
        if idx in self._selected:
            self._selected.discard(idx)
            mark = "☐"
        else:
            self._selected.add(idx)
            mark = "☑"
        vals = list(self.tree.item(item, "values"))
        vals[0] = mark
        self.tree.item(item, values=vals)

    def _on_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._items):
            body = self._items[idx].get("body", "")
            self.preview.configure(state="normal")
            self.preview.delete("1.0", tk.END)
            self.preview.insert("1.0", body[:3000])
            self.preview.configure(state="disabled")

    def _select_all(self) -> None:
        self._selected = set(range(len(self._items)))
        for iid in self.tree.get_children():
            vals = list(self.tree.item(iid, "values"))
            vals[0] = "☑"
            self.tree.item(iid, values=vals)

    def _select_none(self) -> None:
        self._selected.clear()
        for iid in self.tree.get_children():
            vals = list(self.tree.item(iid, "values"))
            vals[0] = "☐"
            self.tree.item(iid, values=vals)

    def _importar(self) -> None:
        if not self._selected:
            messagebox.showinfo("Escaneo", "Seleccione al menos un correo.", parent=self)
            return
        self.result = [self._items[i] for i in sorted(self._selected)]
        self.destroy()
