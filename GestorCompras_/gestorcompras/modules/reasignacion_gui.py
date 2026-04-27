"""Punto de entrada unificado para la reasignación de tareas."""
from __future__ import annotations

import email
import hashlib
import html
import imaplib
import logging
import re
import unicodedata
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import tkinter as tk
from tkinter import ttk, messagebox

from gestorcompras import theme
from gestorcompras.core import config as core_config
from gestorcompras.core.mail_parse import parse_body, parse_subject
from gestorcompras.data import reasignaciones_repo
from gestorcompras.services import reassign_bridge, db
from gestorcompras.ui.common import add_hover_effect, center_window
from gestorcompras.gui import reasignacion_gui as legacy_gui

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "servicios_reasignacion.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("servicios_reasignacion")
if not logger.handlers:
    handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


SERVICIOS_REMITENTE_KEY = "SERVICIOS_REMITENTE"


class ServiciosReasignacion(tk.Toplevel):
    columns = (
        "seleccion",
        "fecha",
        "numero_tarea",
        "taller",
        "asunto",
    )

    def __init__(self, master: tk.Misc | None, email_session: dict[str, str]):
        super().__init__(master)
        self.title("Reasignación de tareas - Servicios")
        self.geometry("1100x720")
        self.transient(master)
        self.grab_set()
        self.email_session = email_session
        self.records: dict[str, dict[str, object]] = {}
        self._correo_usuario = core_config.get_user_email() or email_session.get("address", "")
        self.servicios_cfg = core_config.get_servicios_config()
        self.departamento_var = tk.StringVar(value=db.get_config("SERVICIOS_DEPARTAMENTO", ""))
        self.usuario_var = tk.StringVar(value=db.get_config("SERVICIOS_USUARIO", ""))
        self.headless_var = tk.BooleanVar(value=db.get_config("SERVICIOS_HEADLESS", "1") != "0")
        self.headless_var.trace_add("write", self._persist_headless)
        remitente_default = db.get_config(
            SERVICIOS_REMITENTE_KEY,
            self.servicios_cfg.get("remitente_correo", ""),
        )
        self.remitente_var = tk.StringVar(value=remitente_default)
        self._build_ui()
        center_window(self)

    # UI helpers
    def _build_ui(self) -> None:
        main = ttk.Frame(self, style="MyFrame.TFrame", padding=10)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(3, weight=1)

        # -- Row 0: Professional header --
        header_frame = ttk.Frame(main, style="MyFrame.TFrame")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        ttk.Label(
            header_frame,
            text="Reasignacion de Tareas",
            font=("Segoe UI", 16, "bold"),
            foreground=theme.color_titulos,
            style="MyLabel.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header_frame,
            text="Busque correos de servicio y reasigne tareas a otro usuario.",
            font=("Segoe UI", 10),
            foreground="#6B7280",
            style="MyLabel.TLabel",
        ).pack(anchor="w")
        ttk.Separator(header_frame, orient="horizontal").pack(fill="x", pady=(5, 0))

        # -- Row 1: Filtros --
        filtros = ttk.LabelFrame(main, text="Busqueda de correos", style="MyLabelFrame.TLabelframe", padding=10)
        filtros.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        for col in (1, 3):
            filtros.columnconfigure(col, weight=1)
        filtros.columnconfigure(4, weight=0)

        ttk.Label(filtros, text="Desde (YYYY-MM-DD HH:MM):", style="MyLabel.TLabel").grid(row=0, column=0, sticky="w")
        self.desde_var = tk.StringVar()
        self.hasta_var = tk.StringVar()
        tz = ZoneInfo(self.servicios_cfg.get("zona_horaria", "America/Guayaquil"))
        ahora = datetime.now(tz)
        self.desde_var.set((ahora - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M"))
        self.hasta_var.set(ahora.strftime("%Y-%m-%d %H:%M"))

        ttk.Entry(filtros, textvariable=self.desde_var, style="MyEntry.TEntry", width=22).grid(row=0, column=1, padx=5, sticky="ew")

        ttk.Label(filtros, text="Hasta (YYYY-MM-DD HH:MM):", style="MyLabel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Entry(filtros, textvariable=self.hasta_var, style="MyEntry.TEntry", width=22).grid(row=0, column=3, padx=5, sticky="ew")

        buscar_btn = ttk.Button(filtros, text="Buscar correos", style="MyButton.TButton", command=self._buscar)
        buscar_btn.grid(row=0, column=4, padx=10, rowspan=3, sticky="n")
        add_hover_effect(buscar_btn)

        ttk.Label(filtros, text="Remitente:", style="MyLabel.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(
            filtros,
            textvariable=self.remitente_var,
            style="MyEntry.TEntry",
        ).grid(row=1, column=1, columnspan=3, padx=5, sticky="ew", pady=(8, 0))

        ttk.Label(
            filtros,
            text="Formato: AAAA-MM-DD HH:MM",
            font=("Segoe UI", 9),
            foreground="#6B7280",
            style="MyLabel.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))

        # -- Row 2: Asignacion --
        asignacion = ttk.LabelFrame(
            main,
            text="Datos de reasignacion",
            style="MyLabelFrame.TLabelframe",
            padding=10,
        )
        asignacion.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        asignacion.columnconfigure(1, weight=1)
        asignacion.columnconfigure(3, weight=1)

        ttk.Label(asignacion, text="Departamento Telcos:", style="MyLabel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(asignacion, textvariable=self.departamento_var, style="MyEntry.TEntry", width=28).grid(
            row=0, column=1, padx=5, sticky="ew"
        )

        ttk.Label(asignacion, text="Usuario a reasignar:", style="MyLabel.TLabel").grid(
            row=0, column=2, sticky="w"
        )
        ttk.Entry(asignacion, textvariable=self.usuario_var, style="MyEntry.TEntry", width=28).grid(
            row=0, column=3, padx=5, sticky="ew"
        )

        ttk.Checkbutton(
            asignacion,
            text="Mostrar navegador durante la ejecucion",
            style="MyCheckbutton.TCheckbutton",
            variable=self.headless_var,
            onvalue=False,
            offvalue=True,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        ttk.Label(
            asignacion,
            text="Si esta activado, podra ver el navegador mientras se ejecuta la reasignacion.",
            font=("Segoe UI", 9),
            foreground="#6B7280",
            style="MyLabel.TLabel",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(2, 0))

        # -- Row 3: Table wrapped in LabelFrame --
        tabla_lf = ttk.LabelFrame(main, text="Correos encontrados", style="MyLabelFrame.TLabelframe", padding=5)
        tabla_lf.grid(row=3, column=0, sticky="nsew")
        tabla_lf.rowconfigure(0, weight=1)
        tabla_lf.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tabla_lf,
            columns=self.columns,
            show="headings",
            style="MyTreeview.Treeview",
            selectmode="browse",
        )
        headings = {
            "seleccion": "",
            "fecha": "Fecha",
            "numero_tarea": "Numero de tarea",
            "taller": "Taller",
            "asunto": "Asunto",
        }
        for col, label in headings.items():
            self.tree.heading(col, text=label)
        self.tree.column("seleccion", width=40, anchor="center")
        self.tree.column("fecha", width=150, anchor="center")
        self.tree.column("numero_tarea", width=140, anchor="center")
        self.tree.column("taller", width=220, anchor="w")
        self.tree.column("asunto", width=320, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._on_tree_click, add=True)

        scrollbar = ttk.Scrollbar(tabla_lf, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # -- Row 4: Actions --
        acciones = ttk.Frame(main, style="MyFrame.TFrame", padding=5)
        acciones.grid(row=4, column=0, sticky="ew", pady=5)

        self.select_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            acciones,
            text="Seleccionar todos",
            style="MyCheckbutton.TCheckbutton",
            variable=self.select_all_var,
            command=self._toggle_all,
        ).pack(side="left")

        self.estado_label = ttk.Label(acciones, text="", style="MyLabel.TLabel")
        self.estado_label.pack(side="left", padx=(10, 0))

        self.progress = ttk.Progressbar(acciones, mode="indeterminate", length=120)
        self.progress.pack(side="right", padx=(5, 0))
        self.progress.grid_remove() if self.progress.winfo_manager() == "grid" else self.progress.pack_forget()

        reasignar_btn = ttk.Button(acciones, text="Reasignar tareas", style="MyButton.TButton", command=self._reasignar)
        reasignar_btn.pack(side="right", padx=5)
        add_hover_effect(reasignar_btn)

        # -- Preview (column 1, spanning table + actions rows) --
        preview_frame = ttk.LabelFrame(main, text="Vista previa del correo", style="MyLabelFrame.TLabelframe", padding=10)
        preview_frame.grid(row=3, column=1, rowspan=2, sticky="nsew", padx=(10, 0))
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self.preview = tk.Text(preview_frame, wrap="word", state="disabled")
        self.preview.grid(row=0, column=0, sticky="nsew")

        # -- Row 5: Status bar --
        self.status_var = tk.StringVar(value="Listo para buscar.")
        ttk.Label(
            main,
            textvariable=self.status_var,
            style="MyLabel.TLabel",
            font=("Segoe UI", 9),
            foreground="#6B7280",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(5, 0))

    @staticmethod
    def _checkbox_symbol(checked: bool) -> str:
        return "☑" if checked else "☐"

    def _toggle_all(self) -> None:
        new_state = self.select_all_var.get()
        for message_id, record in self.records.items():
            record["checked"] = new_state
            self.tree.set(message_id, "seleccion", self._checkbox_symbol(new_state))

    def _sync_master_check(self) -> None:
        if not self.records:
            self.select_all_var.set(False)
            return
        all_checked = all(record.get("checked") for record in self.records.values())
        if self.select_all_var.get() != all_checked:
            self.select_all_var.set(all_checked)

    def _on_tree_click(self, event) -> str | None:
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return None
        column = self.tree.identify_column(event.x)
        if column != "#1":
            return None
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return "break"
        record = self.records.get(item_id)
        if not record:
            return "break"
        nuevo_estado = not record.get("checked", False)
        record["checked"] = nuevo_estado
        self.tree.set(item_id, "seleccion", self._checkbox_symbol(nuevo_estado))
        self._sync_master_check()
        return "break"

    # Helpers
    def _persist_headless(self, *_args) -> None:
        db.set_config("SERVICIOS_HEADLESS", "1" if self.headless_var.get() else "0")

    def _parse_datetime(self, value: str) -> datetime:
        cfg = core_config.get_servicios_config()
        tz = ZoneInfo(cfg.get("zona_horaria", "America/Guayaquil"))
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=tz)

    @staticmethod
    def _decode_header_value(raw: str) -> str:
        from gestorcompras.services.email_task_scanner import decode_header_value
        return decode_header_value(raw)

    @classmethod
    def _decode_subject(cls, msg: Message) -> str:
        from gestorcompras.services.email_task_scanner import decode_subject
        return decode_subject(msg)

    @staticmethod
    def _clean_html(text: str) -> str:
        from gestorcompras.services.email_task_scanner import clean_html
        return clean_html(text)

    @classmethod
    def _extract_text(cls, msg: Message) -> str:
        from gestorcompras.services.email_task_scanner import extract_text
        return extract_text(msg)

    @staticmethod
    def _parse_header_date(msg: Message, tz: ZoneInfo) -> datetime | None:
        from gestorcompras.services.email_task_scanner import parse_header_date
        return parse_header_date(msg, tz)

    def _buscar_correos(
        self,
        usuario: str,
        password: str,
        cadena_asunto: str,
        dt_desde: datetime,
        dt_hasta: datetime,
        remitente: str = "",
    ) -> list[dict[str, object]]:
        tz = dt_desde.tzinfo or ZoneInfo("America/Guayaquil")
        cadena_normalizada = self._normalize_for_search(cadena_asunto)
        host = "pop.telconet.ec"
        puerto = 993
        remitente_busqueda = remitente.strip()
        remitente_normalizado = remitente_busqueda.lower()

        conexion = imaplib.IMAP4_SSL(host, puerto)
        try:
            conexion.login(usuario, password)
            conexion.select("INBOX")
            since = dt_desde.strftime("%d-%b-%Y")
            criterios: list[str] = ["SINCE", since]
            if remitente_busqueda:
                criterios.extend(["FROM", remitente_busqueda])
            status, data = conexion.search(None, *criterios)
            if status != "OK":
                raise RuntimeError("No se pudo obtener el listado de correos")
            ids = data[0].split()
            resultados: list[dict[str, object]] = []
            for msg_id in reversed(ids):
                status, fetch_data = conexion.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                for response in fetch_data:
                    if not isinstance(response, tuple):
                        continue
                    msg = email.message_from_bytes(response[1])
                    subject = self._decode_subject(msg)
                    subject_normalized = self._normalize_for_search(subject)
                    if cadena_normalizada not in subject_normalized:
                        continue
                    from_header = self._decode_header_value(msg.get("From", ""))
                    if remitente_normalizado and remitente_normalizado not in from_header.lower():
                        continue
                    fecha = self._parse_header_date(msg, tz)
                    if not fecha or not (dt_desde <= fecha <= dt_hasta):
                        continue
                    cuerpo = self._extract_text(msg)
                    parsed = parse_body(cuerpo, usuario)
                    if not parsed.get("correo_usuario_encontrado"):
                        mensaje_id = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                        logger.info(
                            "Correo ignorado por no contener al usuario: id=%s",
                            mensaje_id,
                        )
                        continue
                    info_tarea = parse_subject(subject)
                    mensaje_id = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                    registros = {
                        "message_id": mensaje_id,
                        "date": fecha,
                        "subject": subject,
                        "from": from_header,
                        "task_number": info_tarea.get("task_number", "N/D"),
                        "body": cuerpo,
                        "proveedor": parsed.get("proveedor", "N/D"),
                        "mecanico_nombre": parsed.get("mecanico_nombre", "N/D"),
                        "mecanico_telefono": parsed.get("mecanico_telefono", "N/D"),
                        "inf_vehiculo": parsed.get("inf_vehiculo", "N/D"),
                    }
                    resultados.append(registros)
                    logger.info(
                        "Correo válido encontrado: id=%s tarea=%s remitente=%s",
                        registros["message_id"],
                        registros["task_number"],
                        from_header or "(sin remitente)",
                    )
            return resultados
        finally:
            try:
                conexion.logout()
            except Exception:
                pass

    @staticmethod
    def _normalize_for_search(value: str | None) -> str:
        from gestorcompras.services.email_task_scanner import normalize_for_search
        return normalize_for_search(value)

    @staticmethod
    def _normalize_email(address: str | None) -> str:
        value = (address or "").strip()
        if value and "@" not in value:
            return f"{value}@telconet.ec"
        return value

    def _buscar(self) -> None:
        cfg = core_config.get_servicios_config()
        correo_usuario = self._correo_usuario or self.email_session.get("address", "")
        password = self.email_session.get("password", "")
        if not correo_usuario or not password:
            messagebox.showerror(
                "Sesión",
                "Debe iniciar sesión en el sistema para consultar el correo.",
                parent=self,
            )
            return
        self._correo_usuario = correo_usuario

        cadena = cfg.get("cadena_asunto_fija", "NOTIFICACION A PROVEEDOR:")
        remitente = self.remitente_var.get().strip()
        try:
            dt_desde = self._parse_datetime(self.desde_var.get())
            dt_hasta = self._parse_datetime(self.hasta_var.get())
        except ValueError:
            messagebox.showerror("Formato incorrecto", "Ingrese fechas en formato YYYY-MM-DD HH:MM", parent=self)
            return

        if dt_desde > dt_hasta:
            messagebox.showerror("Rango inválido", "La fecha inicial no puede ser mayor a la final.", parent=self)
            return

        logger.info(
            "Buscando correos: usuario=%s asunto~%s rango=%s-%s",
            correo_usuario,
            cadena,
            dt_desde,
            dt_hasta,
        )

        try:
            registros = self._buscar_correos(
            correo_usuario,
            password,
            cadena,
            dt_desde,
            dt_hasta,
            remitente,
        )
        except Exception as exc:
            logger.exception("Error durante la lectura de correos")
            messagebox.showerror("Correo", f"No se pudo realizar la búsqueda: {exc}", parent=self)
            return

        self.tree.delete(*self.tree.get_children())
        self.records.clear()
        self.select_all_var.set(False)
        db.set_config(SERVICIOS_REMITENTE_KEY, remitente)
        for item in registros:
            message_id = item["message_id"]
            estado = "Listo"
            raw_hash = hashlib.sha256(item["body"].encode("utf-8", "ignore")).hexdigest()
            registro = {
                "message_id": message_id,
                "fecha": item["date"],
                "asunto": item["subject"],
                "task_number": item.get("task_number", "N/D"),
                "taller": item.get("proveedor", "N/D"),
                "proveedor": item.get("proveedor", "N/D"),
                "mecanico": item.get("mecanico_nombre", "N/D"),
                "telefono": item.get("mecanico_telefono", "N/D"),
                "inf_vehiculo": item.get("inf_vehiculo", "N/D"),
                "correo_usuario": correo_usuario,
                "raw_hash": raw_hash,
                "body": item["body"],
                "estado": estado,
                "checked": False,
                "error": "",
            }
            self.records[message_id] = registro
            reasignaciones_repo.upsert({
                key: registro.get(key)
                for key in (
                    "message_id",
                    "fecha",
                    "asunto",
                    "task_number",
                    "proveedor",
                    "mecanico",
                    "telefono",
                    "inf_vehiculo",
                    "correo_usuario",
                    "raw_hash",
                )
            })
            self.tree.insert(
                "",
                "end",
                iid=message_id,
                values=(
                    self._checkbox_symbol(False),
                    item["date"].strftime("%Y-%m-%d %H:%M"),
                    registro["task_number"],
                    registro["taller"],
                    item["subject"],
                ),
            )
            logger.info(
                "Correo procesado: id=%s task=%s taller=%s", message_id, registro["task_number"], registro["taller"]
            )
        if not registros:
            messagebox.showinfo("Sin resultados", "No se encontraron correos en el rango especificado.", parent=self)

    def _selected_record(self) -> dict[str, object] | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Selección", "Seleccione un registro.", parent=self)
            return None
        return self.records.get(sel[0])

    def _on_select(self, _event) -> None:
        record = self._selected_record()
        if not record:
            return
        self.preview.config(state="normal")
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, record.get("body", ""))
        self.preview.config(state="disabled")
        self.estado_label.configure(text=f"Estado seleccionado: {record.get('estado', 'N/D')}")

    def _reasignar(self) -> None:
        objetivos = [r for r in self.records.values() if r.get("checked")]
        if not objetivos:
            messagebox.showwarning("Reasignación", "Marque al menos un correo para procesar.", parent=self)
            return
        department = self.departamento_var.get().strip()
        employee = self.usuario_var.get().strip()
        if not department or not employee:
            messagebox.showwarning(
                "Reasignación",
                "Debe ingresar el departamento y el usuario a quien reasignar.",
                parent=self,
            )
            return
        comentario_template = db.get_config("SERVICIOS_REASIGNACION_MSG", 'Taller Asignado "{proveedor}"')
        exitos = 0
        fallas = 0
        no_encontradas = 0
        pendientes: list[dict[str, object]] = []
        for record in objetivos:
            task = record.get("task_number")
            if not task or task == "N/D":
                fallas += 1
                record["estado"] = "Número inválido"
                record["error"] = "Número de tarea no disponible"
                self.tree.set(record["message_id"], "seleccion", self._checkbox_symbol(False))
                record["checked"] = False
                continue
            pendientes.append(record)

        resultados = []
        if pendientes:
            resultados = reassign_bridge.reassign_tasks(
                pendientes,
                fuente="SERVICIOS",
                department=department,
                employee=employee,
                headless=self.headless_var.get(),
                comentario_template=comentario_template,
                email_session=self.email_session,
            )
        resultado_por_id = {item.get("message_id"): item for item in resultados}

        for record in objetivos:
            resultado = resultado_por_id.get(record.get("message_id"))
            if resultado:
                estado = resultado.get("status", "error")
                record["estado"] = estado.capitalize()
                record["error"] = resultado.get("error", "")
            record["checked"] = False
            self.tree.set(record["message_id"], "seleccion", self._checkbox_symbol(False))

            estado_actual = record.get("estado", "")
            estado_lower = estado_actual.lower()
            if estado_lower == "ok" or estado_lower == "reasignada":
                exitos += 1
            elif estado_lower == "not_found":
                no_encontradas += 1
            elif estado_lower in {"número inválido", "numero inválido", "numero invalido", "número invalido"}:
                fallas += 1
            elif estado_lower == "error":
                fallas += 1
            else:
                fallas += 1

        db.set_config("SERVICIOS_DEPARTAMENTO", department)
        db.set_config("SERVICIOS_USUARIO", employee)
        self._sync_master_check()

        resumen = []
        if exitos:
            resumen.append(f"{exitos} reasignadas")
        if no_encontradas:
            resumen.append(f"{no_encontradas} no encontradas")
        if fallas:
            resumen.append(f"{fallas} con error")
        resumen_texto = ", ".join(resumen) if resumen else "Sin cambios"
        self.estado_label.configure(text=f"Último resultado: {resumen_texto}")

        if exitos and not fallas and not no_encontradas:
            messagebox.showinfo("Reasignación", "Tareas reasignadas correctamente.", parent=self)
        elif exitos or no_encontradas:
            messagebox.showwarning("Reasignación", resumen_texto.capitalize(), parent=self)
        else:
            messagebox.showerror("Reasignación", "No se pudo reasignar ninguna tarea.", parent=self)

        exitosos: list[dict[str, object]] = []
        fallidos: list[dict[str, object]] = []
        for record in objetivos:
            fila_base = {
                "fecha": record.get("fecha"),
                "task_number": record.get("task_number", "N/D"),
                "taller": record.get("taller", "N/D"),
                "asunto": record.get("asunto", ""),
            }
            estado = str(record.get("estado", "")).lower()
            if estado in {"ok", "reasignada"}:
                exitosos.append(fila_base)
            else:
                error_texto = record.get("error") or record.get("estado", "Error")
                fila_fallo = dict(fila_base)
                fila_fallo["error"] = error_texto
                fallidos.append(fila_fallo)

        try:
            from gestorcompras.services.reassign_reporter import enviar_reporte_servicios

            destinatario_reporte = self.email_session.get("address", "") or self._correo_usuario
            destinatario_reporte = self._normalize_email(destinatario_reporte)
            logger.info("Destinatario final de reporte de reasignación: %s", destinatario_reporte or "(vacío)")

            enviar_reporte_servicios(
                self.email_session,
                destinatario_reporte,
                exitosos,
                fallidos,
            )
        except Exception:
            logger.exception("No se pudo enviar el reporte de reasignación")

        try:
            from gestorcompras.ui.actua_tareas_gui import abrir_panel_tareas

            tareas_ok = []
            for record in objetivos:
                estado = str(record.get("estado", "")).lower()
                if estado not in {"ok", "reasignada"}:
                    continue
                tareas_ok.append(
                    {
                        "task_number": str(record.get("task_number", "")),
                        "proveedor": record.get("taller", ""),
                        "mecanico": record.get("mecanico", ""),
                        "telefono": record.get("telefono", ""),
                        "inf_vehiculo": record.get("inf_vehiculo", ""),
                        "taller": record.get("taller", ""),
                        "asunto": record.get("asunto", ""),
                    }
                )
            if tareas_ok and messagebox.askyesno(
                "Actualizar Tareas",
                "¿Desea abrir el panel de Actualizar Tareas para estas tareas reasignadas?",
                parent=self,
            ):
                abrir_panel_tareas(
                    self,
                    self.email_session,
                    "reasignacion",
                    tareas_ok,
                    mode="servicios",
                )
        except Exception:
            logger.exception("Hook Actualizar Tareas (reasignación) falló sin afectar el flujo principal.")


def open(master: tk.Misc, email_session: dict[str, str], mode: str = "bienes") -> None:
    """Abre la ventana correspondiente según el flujo seleccionado."""

    mode_normalized = (mode or "bienes").strip().lower()
    if mode_normalized == "servicios":
        ServiciosReasignacion(master, email_session)
    elif mode_normalized == "bienes":
        legacy_gui.open_reasignacion(master, email_session)
    else:
        messagebox.showerror(
            "Reasignación",
            f"Modo desconocido '{mode}'. Seleccione entre 'bienes' o 'servicios'.",
            parent=master,
        )


def open_servicios(master: tk.Misc, email_session: dict[str, str]) -> None:
    """Alias explícito para abrir la reasignación de Servicios."""

    open(master, email_session, mode="servicios")


def open_bienes(master: tk.Misc, email_session: dict[str, str]) -> None:
    """Alias explícito para abrir la reasignación de Bienes."""

    open(master, email_session, mode="bienes")


__all__ = ["open", "open_servicios", "open_bienes", "ServiciosReasignacion"]
