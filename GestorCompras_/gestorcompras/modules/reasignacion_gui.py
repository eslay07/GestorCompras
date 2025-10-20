"""Punto de entrada unificado para la reasignación de tareas."""
from __future__ import annotations

import email
import hashlib
import html
import imaplib
import logging
import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import tkinter as tk
from tkinter import ttk, messagebox

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
        "asunto",
        "numero_tarea",
        "taller",
    )

    def __init__(self, master: tk.Misc | None, email_session: dict[str, str]):
        super().__init__(master)
        self.title("Reasignación de tareas - Servicios")
        self.geometry("1080x640")
        self.transient(master)
        self.grab_set()
        self.email_session = email_session
        self.records: dict[str, dict[str, object]] = {}
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
        main.rowconfigure(2, weight=1)

        filtros = ttk.LabelFrame(main, text="Filtros", style="MyLabelFrame.TLabelframe", padding=10)
        filtros.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
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

        buscar_btn = ttk.Button(filtros, text="Buscar", style="MyButton.TButton", command=self._buscar)
        buscar_btn.grid(row=0, column=4, padx=10, rowspan=2, sticky="n")
        add_hover_effect(buscar_btn)

        ttk.Button(
            filtros,
            text="Cerrar",
            style="MyButton.TButton",
            command=self.destroy,
        ).grid(row=0, column=5, rowspan=2, sticky="ne")

        ttk.Label(filtros, text="Remitente:", style="MyLabel.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(
            filtros,
            textvariable=self.remitente_var,
            style="MyEntry.TEntry",
        ).grid(row=1, column=1, columnspan=3, padx=5, sticky="ew", pady=(8, 0))

        asignacion = ttk.LabelFrame(
            main,
            text="Datos de reasignación",
            style="MyLabelFrame.TLabelframe",
            padding=10,
        )
        asignacion.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
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
            text="Ejecutar navegador en modo oculto (headless)",
            style="MyCheckbutton.TCheckbutton",
            variable=self.headless_var,
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        tabla_frame = ttk.Frame(main, style="MyFrame.TFrame")
        tabla_frame.grid(row=2, column=0, sticky="nsew")
        tabla_frame.rowconfigure(0, weight=1)
        tabla_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            tabla_frame,
            columns=self.columns,
            show="headings",
            style="MyTreeview.Treeview",
            selectmode="browse",
        )
        headings = {
            "seleccion": "",
            "fecha": "Fecha",
            "asunto": "Asunto",
            "numero_tarea": "Número de tarea",
            "taller": "Taller",
        }
        for col, label in headings.items():
            self.tree.heading(col, text=label)
        self.tree.column("seleccion", width=40, anchor="center")
        self.tree.column("fecha", width=150, anchor="center")
        self.tree.column("asunto", width=320, anchor="w")
        self.tree.column("numero_tarea", width=140, anchor="center")
        self.tree.column("taller", width=220, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-1>", self._on_tree_click, add=True)

        scrollbar = ttk.Scrollbar(tabla_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        acciones = ttk.Frame(main, style="MyFrame.TFrame", padding=5)
        acciones.grid(row=3, column=0, sticky="ew", pady=5)

        self.select_all_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            acciones,
            text="Marcar todos",
            style="MyCheckbutton.TCheckbutton",
            variable=self.select_all_var,
            command=self._toggle_all,
        ).pack(side="left")

        self.estado_label = ttk.Label(acciones, text="", style="MyLabel.TLabel")
        self.estado_label.pack(side="left", padx=(10, 0))

        reasignar_btn = ttk.Button(acciones, text="Reasignar", style="MyButton.TButton", command=self._reasignar)
        reasignar_btn.pack(side="right", padx=5)
        add_hover_effect(reasignar_btn)

        reprocesar_btn = ttk.Button(acciones, text="Reprocesar este correo", style="MyButton.TButton", command=self._reprocesar)
        reprocesar_btn.pack(side="right", padx=5)
        add_hover_effect(reprocesar_btn)

        preview_frame = ttk.LabelFrame(main, text="Vista previa", style="MyLabelFrame.TLabelframe", padding=10)
        preview_frame.grid(row=2, column=1, rowspan=2, sticky="nsew", padx=(10, 0))
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self.preview = tk.Text(preview_frame, wrap="word", state="disabled")
        self.preview.grid(row=0, column=0, sticky="nsew")

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
        try:
            return str(make_header(decode_header(raw)))
        except Exception:  # pragma: no cover - caso defensivo
            partes: list[str] = []
            for value, encoding in decode_header(raw):
                if isinstance(value, bytes):
                    codec = encoding or "utf-8"
                    try:
                        partes.append(value.decode(codec, errors="ignore"))
                    except Exception:
                        partes.append(value.decode("utf-8", errors="ignore"))
                else:
                    partes.append(value)
            return "".join(partes)

    @classmethod
    def _decode_subject(cls, msg: Message) -> str:
        return cls._decode_header_value(msg.get("Subject", ""))

    @staticmethod
    def _clean_html(text: str) -> str:
        cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", text)
        cleaned = re.sub(r"(?is)<br\\s*/?>", "\n", cleaned)
        cleaned = re.sub(r"(?is)</p>", "\n", cleaned)
        cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _extract_text(cls, msg: Message) -> str:
        partes: list[str] = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == "attachment":
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                try:
                    texto = payload.decode(charset, errors="ignore")
                except Exception:
                    texto = payload.decode("utf-8", errors="ignore")
                if part.get_content_type() == "text/html":
                    texto = cls._clean_html(texto)
                partes.append(texto)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    texto = payload.decode(charset, errors="ignore")
                except Exception:
                    texto = payload.decode("utf-8", errors="ignore")
                if msg.get_content_type() == "text/html":
                    texto = cls._clean_html(texto)
                partes.append(texto)
        return "\n".join(filter(None, partes)).strip()

    @staticmethod
    def _parse_header_date(msg: Message, tz: ZoneInfo) -> datetime | None:
        header = msg.get("Date")
        if not header:
            return None
        try:
            dt = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            return None
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(tz)

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
        cadena_normalizada = cadena_asunto.strip().upper()
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
                    if cadena_normalizada not in subject.upper():
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

    def _buscar(self) -> None:
        cfg = core_config.get_servicios_config()
        correo_usuario = core_config.get_user_email() or self.email_session.get("address", "")
        password = self.email_session.get("password", "")
        if not correo_usuario or not password:
            messagebox.showerror(
                "Sesión",
                "Debe iniciar sesión en el sistema para consultar el correo.",
                parent=self,
            )
            return

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
                    item["subject"],
                    registro["task_number"],
                    registro["taller"],
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
        for record in objetivos:
            task = record.get("task_number")
            if not task or task == "N/D":
                fallas += 1
                record["estado"] = "Número inválido"
                continue
            resultado = reassign_bridge.reassign_by_task_number(
                task,
                record.get("proveedor", ""),
                record.get("mecanico", ""),
                record.get("telefono", ""),
                record.get("inf_vehiculo", ""),
                fuente="SERVICIOS",
                department=department,
                employee=employee,
                headless=self.headless_var.get(),
                comentario_template=comentario_template,
                email_session=self.email_session,
            )
            estado = resultado.get("status", "error")
            record["estado"] = estado.capitalize()
            if estado == "ok":
                exitos += 1
            elif estado == "not_found":
                no_encontradas += 1
            else:
                fallas += 1
            record["checked"] = False
            self.tree.set(record["message_id"], "seleccion", self._checkbox_symbol(False))
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
        if not resumen:
            resumen_texto = "Sin cambios"
        else:
            resumen_texto = ", ".join(resumen)
        self.estado_label.configure(text=f"Último resultado: {resumen_texto}")
        if exitos and not fallas and not no_encontradas:
            messagebox.showinfo("Reasignación", "Correos procesados correctamente.", parent=self)
        elif exitos or no_encontradas:
            messagebox.showwarning("Reasignación", resumen_texto.capitalize(), parent=self)
        else:
            messagebox.showerror("Reasignación", "No se pudo procesar ningún correo.", parent=self)

    def _reprocesar(self) -> None:
        record = self._selected_record()
        if not record:
            return
        correo_usuario = core_config.get_user_email() or self.email_session.get("address", "")
        parsed = parse_body(record.get("body", ""), correo_usuario)
        record.update(
            {
                "proveedor": parsed.get("proveedor", "N/D"),
                "taller": parsed.get("proveedor", "N/D"),
                "mecanico": parsed.get("mecanico_nombre", "N/D"),
                "telefono": parsed.get("mecanico_telefono", "N/D"),
                "inf_vehiculo": parsed.get("inf_vehiculo", "N/D"),
            }
        )
        self.tree.set(record["message_id"], "taller", record["taller"])
        messagebox.showinfo("Reprocesado", "Los datos fueron actualizados con la nueva lectura.", parent=self)


def open(master: tk.Misc, email_session: dict[str, str], mode: str = "bienes") -> None:
    if mode == "servicios":
        ServiciosReasignacion(master, email_session)
    else:
        legacy_gui.open_reasignacion(master, email_session)
