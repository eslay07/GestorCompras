"""Pantallas que consumen exclusivamente servicios simulados."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from gestorcompras.core.application import DemoServices
from gestorcompras.core.config import DemoConfig
from gestorcompras.demo import fixtures
from gestorcompras.gui import theme
from gestorcompras.gui.widgets import MetricCard, card, label_pair, page_header, status_banner


class DashboardScreen(ttk.Frame):
    def __init__(self, parent: tk.Misc, services: DemoServices, config: DemoConfig) -> None:
        super().__init__(parent)
        page_header(
            self,
            "Resumen demostrativo",
            "Un recorrido seguro por un flujo genérico de compras, sin conexiones ni datos reales.",
        )

        metrics = ttk.Frame(self)
        metrics.pack(fill="x")
        for column in range(4):
            metrics.columnconfigure(column, weight=1)
        values = (
            (str(len(services.tasks.list_tasks())), "Tareas sintéticas", theme.PRIMARY),
            (str(len(services.mail.list_messages())), "Correos locales", theme.ACCENT),
            (str(len(services.storage.list_documents())), "Documentos ficticios", theme.WARNING),
            ("100%", "Entorno demostrativo", "#7C3AED"),
        )
        for index, (value, label, accent) in enumerate(values):
            item = MetricCard(metrics, value, label, accent)
            item.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 6, 0 if index == 3 else 6))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(18, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        activity = card(body)
        activity.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        tk.Label(
            activity,
            text="Actividad preparada",
            bg=theme.SURFACE,
            fg=theme.NAVY,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            activity,
            text="Elementos precargados desde fixtures del repositorio",
            bg=theme.SURFACE,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 12))

        for task in services.tasks.list_tasks():
            row = tk.Frame(activity, bg=theme.SURFACE_SOFT, padx=12, pady=10)
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text=task.task_id,
                bg=theme.SURFACE_SOFT,
                fg=theme.PRIMARY,
                font=("Segoe UI", 9, "bold"),
                width=13,
                anchor="w",
            ).pack(side="left")
            tk.Label(
                row,
                text=task.summary,
                bg=theme.SURFACE_SOFT,
                fg=theme.TEXT,
                font=("Segoe UI", 9),
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            tk.Label(
                row,
                text=task.status,
                bg=theme.ACCENT_SOFT,
                fg="#08745A",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=4,
            ).pack(side="right")

        safety = card(body)
        safety.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        tk.Label(
            safety,
            text="Privacidad por diseño",
            bg=theme.SURFACE,
            fg=theme.NAVY,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        checks = (
            "Datos incluidos y sintéticos",
            "Adaptadores locales en memoria",
            "Sin credenciales ni sesiones",
            "Sin escritura de documentos",
        )
        for item in checks:
            row = tk.Frame(safety, bg=theme.SURFACE)
            row.pack(fill="x", pady=(14, 0))
            tk.Label(
                row,
                text="✓",
                bg=theme.ACCENT_SOFT,
                fg=theme.ACCENT,
                font=("Segoe UI", 10, "bold"),
                width=2,
            ).pack(side="left")
            tk.Label(
                row,
                text=item,
                bg=theme.SURFACE,
                fg=theme.TEXT,
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(9, 0))


class ConfigurationScreen(ttk.Frame):
    def __init__(self, parent: tk.Misc, services: DemoServices, config: DemoConfig) -> None:
        super().__init__(parent)
        page_header(
            self,
            "Configuración demo",
            "Parámetros visibles y bloqueados para impedir conexiones o datos persistentes.",
        )

        grid = ttk.Frame(self)
        grid.pack(fill="both", expand=True)
        for column in range(2):
            grid.columnconfigure(column, weight=1)
        for row in range(2):
            grid.rowconfigure(row, weight=1)

        panels = (
            (
                "Perfil de ejecución",
                (("Modo", "Demostración obligatoria"), ("Empresa", config.company_name), ("Usuario", config.user_name)),
            ),
            (
                "Mensajería",
                (("Remitente", config.user_email), ("Entrega", "Vista previa local"), ("Bandeja", "Memoria temporal")),
            ),
            (
                "Documentos",
                (("Destino simulado", config.output_path), ("Escritura", "Deshabilitada"), ("Documentos", "Fixtures incluidos")),
            ),
            (
                "Controles activos",
                (("Red", "No utilizada"), ("Credenciales", "No requeridas"), ("Persistencia", "Deshabilitada")),
            ),
        )
        for index, (title, rows) in enumerate(panels):
            panel = card(grid)
            panel.grid(row=index // 2, column=index % 2, sticky="nsew", padx=(0 if index % 2 == 0 else 9, 9 if index % 2 == 0 else 0), pady=(0 if index < 2 else 9, 9 if index < 2 else 0))
            panel.columnconfigure(1, weight=1)
            tk.Label(panel, text=title, bg=theme.SURFACE, fg=theme.NAVY, font=("Segoe UI", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
            for row_index, (label, value) in enumerate(rows, start=1):
                label_pair(panel, label, value, row_index)


class EmailsScreen(ttk.Frame):
    def __init__(self, parent: tk.Misc, services: DemoServices, config: DemoConfig) -> None:
        super().__init__(parent)
        self.services = services
        self.status = tk.StringVar(value="Lista local preparada: ningún mensaje será enviado.")
        page_header(
            self,
            "Correos demostrativos",
            "Genera vistas previas con destinatarios example.com y conserva todo en memoria.",
        )
        status_banner(self, self.status).pack(fill="x", pady=(0, 14))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        table_card = card(body, padding=12)
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        columns = ("id", "recipient", "subject", "status")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        widths = {"id": 110, "recipient": 150, "subject": 240, "status": 100}
        labels = {"id": "Referencia", "recipient": "Destinatario", "subject": "Asunto", "status": "Estado"}
        for name in columns:
            self.tree.heading(name, text=labels[name])
            self.tree.column(name, width=widths[name], anchor="w")
        self.tree.pack(fill="both", expand=True)
        self._reload()

        preview = card(body)
        preview.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        tk.Label(preview, text="Nueva vista previa", bg=theme.SURFACE, fg=theme.NAVY, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(preview, text="Destinatario", bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(16, 4))
        self.recipient = ttk.Entry(preview)
        self.recipient.insert(0, "andino@example.com")
        self.recipient.pack(fill="x")
        tk.Label(preview, text="Orden sintética", bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 4))
        self.order = ttk.Combobox(preview, state="readonly", values=("OC-DEMO-001", "OC-DEMO-002", "OC-DEMO-003"))
        self.order.current(0)
        self.order.pack(fill="x")
        tk.Label(
            preview,
            text="El contenido se genera localmente.\nNo hay servidores configurados ni credenciales.",
            bg=theme.SURFACE_SOFT,
            fg=theme.MUTED,
            font=("Segoe UI", 9),
            justify="left",
            padx=12,
            pady=12,
        ).pack(fill="x", pady=18)
        ttk.Button(preview, text="Generar correo simulado", style="Primary.TButton", command=self.generate).pack(fill="x")

    def _reload(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for message in self.services.mail.list_messages():
            self.tree.insert("", "end", values=(message.message_id, message.recipient, message.subject, message.status))

    def generate(self) -> None:
        try:
            message = self.services.mail.generate(self.recipient.get().strip(), self.order.get())
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self._reload()
        self.status.set(f"{message.message_id} generado en memoria; entrega deshabilitada.")


class ReassignmentScreen(ttk.Frame):
    def __init__(self, parent: tk.Misc, services: DemoServices, config: DemoConfig) -> None:
        super().__init__(parent)
        self.services = services
        self.status = tk.StringVar(value="Selecciona una tarea y un proveedor sintético.")
        self.supplier_by_name = {item.name: item.supplier_id for item in services.tasks.list_suppliers()}
        page_header(
            self,
            "Reasignación simulada",
            "Modifica únicamente una copia volátil de las tareas incluidas en la demostración.",
        )
        status_banner(self, self.status).pack(fill="x", pady=(0, 14))

        table_card = card(self, padding=12)
        table_card.pack(fill="both", expand=True)
        columns = ("task", "order", "summary", "supplier", "owner", "status")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        labels = ("Tarea", "Orden", "Descripción", "Proveedor demo", "Responsable", "Estado")
        widths = (105, 110, 260, 170, 120, 135)
        for column, label, width in zip(columns, labels, widths, strict=True):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self._reload()

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(14, 0))
        ttk.Label(controls, text="Nuevo proveedor:", style="Subtitle.TLabel").pack(side="left")
        self.target = ttk.Combobox(controls, state="readonly", values=tuple(self.supplier_by_name), width=30)
        self.target.current(1)
        self.target.pack(side="left", padx=10)
        ttk.Button(controls, text="Reasignar en demo", style="Primary.TButton", command=self.reassign_selected).pack(side="right")

    def _reload(self) -> None:
        names = {item.supplier_id: item.name for item in self.services.tasks.list_suppliers()}
        for item in self.tree.get_children():
            self.tree.delete(item)
        for task in self.services.tasks.list_tasks():
            self.tree.insert("", "end", iid=task.task_id, values=(task.task_id, task.order_id, task.summary, names[task.supplier_id], task.owner, task.status))
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])

    def reassign_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self.status.set("Selecciona una tarea demostrativa.")
            return
        supplier_id = self.supplier_by_name[self.target.get()]
        result = self.services.tasks.reassign(selected[0], supplier_id)
        self._reload()
        self.status.set(result.message)


class DownloadsScreen(ttk.Frame):
    def __init__(self, parent: tk.Misc, services: DemoServices, config: DemoConfig) -> None:
        super().__init__(parent)
        self.services = services
        self.status = tk.StringVar(value="Los documentos son metadatos sintéticos incluidos en el código.")
        page_header(
            self,
            "Descargas simuladas",
            "Previsualiza el flujo sin navegador, unidades compartidas ni escritura en disco.",
        )
        status_banner(self, self.status).pack(fill="x", pady=(0, 14))

        path_panel = card(self, padding=12)
        path_panel.pack(fill="x", pady=(0, 14))
        tk.Label(path_panel, text="Destino lógico", bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(path_panel, text=config.output_path, bg=theme.SURFACE, fg=theme.NAVY, font=("Consolas", 10, "bold")).pack(side="left", padx=14)
        tk.Label(path_panel, text="NO SE ESCRIBE", bg=theme.WARNING_SOFT, fg=theme.WARNING, font=("Segoe UI", 8, "bold"), padx=9, pady=4).pack(side="right")

        table_card = card(self, padding=12)
        table_card.pack(fill="both", expand=True)
        columns = ("document", "order", "filename", "supplier", "status")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        labels = ("Documento", "Orden", "Archivo ficticio", "Proveedor demo", "Estado")
        widths = (130, 125, 185, 210, 180)
        for column, label, width in zip(columns, labels, widths, strict=True):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        for document in services.storage.list_documents():
            self.tree.insert("", "end", iid=document.document_id, values=(document.document_id, document.order_id, document.filename, document.supplier_name, document.status))
        self.tree.pack(fill="both", expand=True)
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
        ttk.Button(self, text="Simular descarga seleccionada", style="Primary.TButton", command=self.download_selected).pack(anchor="e", pady=(14, 0))

    def download_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self.status.set("Selecciona un documento demostrativo.")
            return
        result = self.services.storage.download(selected[0])
        self.status.set(f"{result.message} Destino lógico: {result.reference}")


class TaskUpdateScreen(ttk.Frame):
    def __init__(self, parent: tk.Misc, services: DemoServices, config: DemoConfig) -> None:
        super().__init__(parent)
        self.services = services
        self.status = tk.StringVar(value="Flujo preparado; todas las acciones se ejecutan en memoria.")
        page_header(
            self,
            "Actualizar tareas en demo",
            "Secuencia genérica y reproducible, sin selectores operativos ni sistemas externos.",
        )
        status_banner(self, self.status).pack(fill="x", pady=(0, 14))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        table_card = card(body, padding=12)
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        columns = ("task", "order", "summary", "status")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        labels = ("Tarea", "Orden", "Descripción", "Estado")
        widths = (110, 115, 260, 150)
        for column, label, width in zip(columns, labels, widths, strict=True):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self._reload()

        workflow = card(body)
        workflow.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        tk.Label(workflow, text="Flujo seguro", bg=theme.SURFACE, fg=theme.NAVY, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(workflow, text="3 pasos locales", bg=theme.SURFACE, fg=theme.MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 14))
        for index, step in enumerate(fixtures.workflow_steps(), start=1):
            row = tk.Frame(workflow, bg=theme.SURFACE_SOFT, padx=10, pady=10)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=str(index), bg=theme.PRIMARY_SOFT, fg=theme.PRIMARY, font=("Segoe UI", 9, "bold"), width=2).pack(side="left")
            tk.Label(row, text=step, bg=theme.SURFACE_SOFT, fg=theme.TEXT, font=("Segoe UI", 9), anchor="w").pack(side="left", padx=(10, 0))
        self.progress = ttk.Progressbar(workflow, mode="determinate", maximum=100, value=0)
        self.progress.pack(fill="x", pady=(22, 12))
        ttk.Button(workflow, text="Ejecutar flujo simulado", style="Primary.TButton", command=self.update_selected).pack(fill="x")

    def _reload(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for task in self.services.tasks.list_tasks():
            self.tree.insert("", "end", iid=task.task_id, values=(task.task_id, task.order_id, task.summary, task.status))
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])

    def update_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            self.status.set("Selecciona una tarea demostrativa.")
            return
        result = self.services.tasks.update(selected[0])
        self.progress.configure(value=100)
        self._reload()
        self.status.set(result.message)


SCREEN_CLASSES = {
    "inicio": DashboardScreen,
    "configuracion": ConfigurationScreen,
    "correos": EmailsScreen,
    "reasignacion": ReassignmentScreen,
    "descargas": DownloadsScreen,
    "actualizar_tareas": TaskUpdateScreen,
}
