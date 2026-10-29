from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from compras_tn.application.services import ApplicationFacade
from compras_tn.domain.models import Assignment, EmailTemplate, Supplier
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.rich_template import RichTemplateEditor
from compras_tn.presentation.widgets import OperationPanel, page_header


def _message(parent: QWidget, title: str, callback: Callable[[], Any]) -> Any:
    try:
        return callback()
    except Exception as exc:
        QMessageBox.critical(parent, title, str(exc))
        return None


class SupplierDialog(QDialog):
    def __init__(self, supplier: Supplier | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Proveedor")
        self.supplier_id = supplier.id if supplier else None
        form = QFormLayout(self)
        self.name = QLineEdit(supplier.name if supplier else "")
        self.nickname = QLineEdit(supplier.nickname if supplier else "")
        self.nickname_2 = QLineEdit(supplier.nickname_2 if supplier else "")
        self.nickname_3 = QLineEdit(supplier.nickname_3 if supplier else "")
        self.ruc = QLineEdit(supplier.ruc if supplier else "")
        self.email_primary = QLineEdit(supplier.email_primary if supplier else "")
        self.email_secondary = QLineEdit(supplier.email_secondary if supplier else "")
        form.addRow("Razón social", self.name)
        form.addRow("Sobrenombre 1 (columna E)", self.nickname)
        form.addRow("Sobrenombre 2 (columna E)", self.nickname_2)
        form.addRow("Sobrenombre 3 (columna E)", self.nickname_3)
        form.addRow("RUC", self.ruc)
        form.addRow("Correo principal", self.email_primary)
        form.addRow("Correo alterno", self.email_secondary)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> Supplier:
        return Supplier(
            id=self.supplier_id,
            name=self.name.text(),
            nickname=self.nickname.text(),
            nickname_2=self.nickname_2.text(),
            nickname_3=self.nickname_3.text(),
            ruc=self.ruc.text(),
            email_primary=self.email_primary.text(),
            email_secondary=self.email_secondary.text(),
        )


class AssignmentDialog(QDialog):
    def __init__(self, item: Assignment | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Asignación")
        form = QFormLayout(self)
        self.subdepartment = QLineEdit(item.subdepartment if item else "")
        self.department = QLineEdit(item.department if item else "")
        self.person = QLineEdit(item.person if item else "")
        if item:
            self.subdepartment.setReadOnly(True)
        form.addRow("Subdepartamento", self.subdepartment)
        form.addRow("Departamento", self.department)
        form.addRow("Responsable", self.person)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def value(self) -> Assignment:
        return Assignment(
            subdepartment=self.subdepartment.text(),
            department=self.department.text(),
            person=self.person.text(),
        )


class TemplateDialog(QDialog):
    def __init__(self, item: EmailTemplate | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Plantilla HTML")
        self.resize(1000, 700)
        self.template_id = item.id if item else None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(item.name if item else "")
        self.signature = QLineEdit(item.signature_path if item else "")
        browse = QPushButton("Elegir…")
        browse.setProperty("secondary", True)
        browse.clicked.connect(self._browse)
        signature_row = QHBoxLayout()
        signature_row.addWidget(self.signature, 1)
        signature_row.addWidget(browse)
        form.addRow("Nombre", self.name)
        form.addRow("Firma / imagen", signature_row)
        layout.addLayout(form)
        layout.addWidget(QLabel("HTML (variables disponibles: {orden}, {ordenes}, {tarea}, {proveedor}, {ruc})"))
        self.html = RichTemplateEditor(item.html if item else "")
        layout.addWidget(self.html, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Elegir firma")
        if path:
            self.signature.setText(path)

    def value(self) -> EmailTemplate:
        return EmailTemplate(
            id=self.template_id,
            name=self.name.text(),
            html=self.html.toPlainText(),
            signature_path=self.signature.text(),
        )


class CatalogTab(QWidget):
    def __init__(
        self,
        columns: list[str],
        loader: Callable[..., list[Any]],
        row_values: Callable[[Any], list[str]],
        editor: Callable[[Any | None], QDialog],
        saver: Callable[[Any], Any],
        deleter: Callable[[Any], None],
        key: Callable[[Any], Any],
        search_placeholder: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.loader = loader
        self.row_values = row_values
        self.editor = editor
        self.saver = saver
        self.deleter = deleter
        self.key = key
        self.rows: list[Any] = []
        layout = QVBoxLayout(self)
        self.search: QLineEdit | None = None
        if search_placeholder:
            self.search = QLineEdit()
            self.search.setPlaceholderText(search_placeholder)
            self.search.setClearButtonEnabled(True)
            self.search.textChanged.connect(lambda _text: self.refresh())
            layout.addWidget(self.search)
        actions = QHBoxLayout()
        add = QPushButton("Nuevo")
        edit = QPushButton("Editar")
        delete = QPushButton("Eliminar")
        refresh = QPushButton("Actualizar")
        edit.setProperty("secondary", True)
        refresh.setProperty("secondary", True)
        delete.setProperty("danger", True)
        add.clicked.connect(lambda: self._edit(None))
        edit.clicked.connect(lambda: self._edit(self._selected()))
        delete.clicked.connect(self._delete)
        refresh.clicked.connect(self.refresh)
        actions.addWidget(add)
        actions.addWidget(edit)
        actions.addWidget(delete)
        actions.addStretch(1)
        actions.addWidget(refresh)
        layout.addLayout(actions)
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _index: self._edit(self._selected()))
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        self.rows = self.loader(self.search.text()) if self.search is not None else self.loader()
        self.table.setRowCount(len(self.rows))
        for row, item in enumerate(self.rows):
            for column, value in enumerate(self.row_values(item)):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _selected(self) -> Any | None:
        row = self.table.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def _edit(self, item: Any | None) -> None:
        dialog = self.editor(item)
        if dialog.exec() != QDialog.Accepted:
            return
        if _message(self, "No se pudo guardar", lambda: self.saver(dialog.value())) is not None:
            self.refresh()

    def _delete(self) -> None:
        item = self._selected()
        if item is None:
            return
        if QMessageBox.question(self, "Eliminar", "¿Eliminar el registro seleccionado?") != QMessageBox.Yes:
            return
        _message(self, "No se pudo eliminar", lambda: self.deleter(self.key(item)))
        self.refresh()


@dataclass(frozen=True, slots=True)
class SettingSpec:
    namespace: str
    key: str
    label: str
    kind: str = "text"
    default: Any = ""


SETTINGS = (
    SettingSpec("quotations", "server_search", "Buscar primero en el servidor (IMAP; respaldo POP)", "bool", True),
    SettingSpec("email", "smtp_server", "Servidor SMTP", default="smtp.telconet.ec"),
    SettingSpec("email", "smtp_port", "Puerto SMTP", "number", 587),
    SettingSpec("email", "imap_server", "Servidor IMAP", default="pop.telconet.ec"),
    SettingSpec("email", "imap_port", "Puerto IMAP", "number", 993),
    SettingSpec("email", "email_cc_despacho", "CC despachos"),
    SettingSpec("email", "email_cc_seguimiento", "CC seguimientos"),
    SettingSpec("quotations", "root", "Carpeta del organizador de archivos", "folder", r"E:\Seadrive\jotoapan_1\My Libraries\Mi Biblioteca\BD_TN"),
    SettingSpec("files", "pdf_folder", "Carpeta de PDF", "folder"),
    SettingSpec("google", "google_creds", "Credenciales Google (JSON obligatorio para carga OC; cuenta con permiso de editor)", "file"),
    SettingSpec("google", "google_sheet_id", "ID de Google Sheet", default=""),
    SettingSpec("google", "google_sheet_name", "Pestaña", default="Hoja 1"),
    SettingSpec("google", "google_oc_sheet_name", "Pestaña GENERAL (OC y archivos)", default="GENERAL"),
    SettingSpec("servicios", "cadena_asunto_fija", "Texto del asunto", default="NOTIFICACION A PROVEEDOR:"),
    SettingSpec("servicios", "zona_horaria", "Zona horaria", default="America/Guayaquil"),
    SettingSpec("servicios", "remitente_correo", "Remitente esperado"),
    SettingSpec("servicios", "servicios_departamento", "Departamento predeterminado"),
    SettingSpec("servicios", "servicios_usuario", "Empleado predeterminado"),
    SettingSpec("servicios", "servicios_reasignacion_msg", "Comentario de reasignación"),
    SettingSpec("downloads", "pop_server", "Servidor POP", default="pop.telconet.ec"),
    SettingSpec("downloads", "pop_port", "Puerto POP", "number", 995),
    SettingSpec("downloads", "carpeta_destino_local", "Carpeta de descargas", "folder"),
    SettingSpec("downloads", "carpeta_analizar", "Carpeta para organizar", "folder"),
    SettingSpec("downloads", "correo_reporte", "Correo de reporte"),
    SettingSpec("downloads", "remitente_adicional", "Remitente adicional"),
    SettingSpec("downloads", "seafile_url", "URL de Seafile", default="https://telcodrive.telconet.net"),
    SettingSpec("downloads", "seafile_repo_id", "Repositorio Seafile (UUID)", default=""),
    SettingSpec("downloads", "seafile_parent_dir", "Raíz de carpetas mensuales", default="/BD_TN"),
    SettingSpec("downloads", "scan_interval", "Intervalo de escaneo (segundos)", "number", 900),
    SettingSpec("downloads", "element_timeout", "Espera de controles del portal (segundos)", "number", 45),
    SettingSpec("downloads", "login_timeout", "Espera de inicio y menú (segundos)", "number", 100),
    SettingSpec("downloads", "query_timeout", "Espera de resultados OC (segundos)", "number", 75),
    SettingSpec("downloads", "download_timeout", "Espera del PDF (segundos)", "number", 120),
    SettingSpec("downloads", "login_retries", "Intentos de ingreso NAF", "number", 3),
    SettingSpec("downloads", "item_retries", "Intentos por OC", "number", 3),
    SettingSpec("downloads", "headless", "Navegador oculto", "bool", True),
    SettingSpec("downloads", "abastecimiento_headless", "Abastecimiento oculto", "bool", True),
    SettingSpec("downloads", "abastecimiento_mover_archivos", "Organizar abastecimiento", "bool", True),
    SettingSpec("downloads", "abastecimiento_carpeta_descarga", "Carpeta abastecimiento", "folder"),
    SettingSpec("downloads", "abastecimiento_correo_reporte", "Reporte abastecimiento"),
    SettingSpec("downloads", "abastecimiento_solicitantes", "Solicitantes (uno por línea)", "lines"),
    SettingSpec("downloads", "abastecimiento_autorizadores", "Autorizadores (uno por línea)", "lines"),
    SettingSpec("automation", "actua_headless", "Orquestador Telcos en oculto", "bool", True),
    SettingSpec("automation", "actua_retries", "Intentos por tarea", "number", 2),
    SettingSpec("automation", "actua_timeout", "Espera de controles Telcos (segundos)", "number", 20),
    SettingSpec("automation", "actua_long_timeout", "Espera de pantallas Telcos (segundos)", "number", 60),
    SettingSpec("automation", "actua_query_timeout", "Espera de resultados de tarea (segundos)", "number", 75),
    SettingSpec("automation", "actua_send_report", "Enviar reporte al terminar", "bool", True),
    SettingSpec("automation", "actua_report_email", "Correo de reportes (vacío = usuario actual)"),
    SettingSpec("automation", "actua_tareas_carpeta_base", "Carpeta base de tareas", "folder"),
    SettingSpec("automation", "oc_element_timeout", "OC: espera de controles NAF (segundos)", "number", 45),
    SettingSpec("automation", "oc_login_timeout", "OC: espera de ingreso NAF (segundos)", "number", 100),
    SettingSpec("automation", "oc_login_retries", "OC: intentos de ingreso NAF", "number", 3),
    SettingSpec("automation", "oc_save_timeout", "OC: espera de confirmación al guardar (segundos)", "number", 75),
    SettingSpec("automation", "oc_browser_visible", "OC: navegador visible", "bool", True),
)


def setting_group(spec: SettingSpec) -> str:
    if spec.namespace == "quotations":
        return "Organizador de archivos"
    if spec.namespace == "automation":
        return "Carga de OC automática" if spec.key.startswith("oc_") else "Orquestador Telcos"
    if spec.namespace == "servicios":
        return "General" if spec.key in {"cadena_asunto_fija", "zona_horaria", "remitente_correo"} else "Reasignación"
    if spec.namespace == "files":
        return "Correos masivos"
    if spec.namespace == "downloads":
        if spec.key.startswith("abastecimiento_"):
            return "Abastecimiento"
        if spec.key in {"pop_server", "pop_port", "seafile_url", "seafile_repo_id", "seafile_parent_dir"}:
            return "General"
        return "Descargas OC"
    if spec.namespace == "email" and spec.key == "email_cc_seguimiento":
        return "Seguimientos"
    if spec.namespace == "email" and spec.key == "email_cc_despacho":
        return "Correos masivos"
    return "General"


class PreferencesTab(QWidget):
    def __init__(self, services: ApplicationFacade, jobs: JobManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.jobs = jobs
        self.inputs: dict[tuple[str, str], QWidget] = {}
        outer = QVBoxLayout(self)
        sections = QTabWidget()
        outer.addWidget(sections, 1)
        forms = {}
        for group in dict.fromkeys(["General"] + [setting_group(spec) for spec in SETTINGS]):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            body = QWidget()
            forms[group] = QFormLayout(body)
            scroll.setWidget(body)
            sections.addTab(scroll, group)
        for spec in SETTINGS:
            form = forms[setting_group(spec)]
            value = services.get_setting(spec.namespace, spec.key, spec.default)
            widget: QWidget
            if spec.kind == "bool":
                control = QCheckBox()
                control.setChecked(
                    value if isinstance(value, bool) else str(value).strip().casefold() in {"1", "true", "sí", "si", "yes"}
                )
                widget = control
            elif spec.kind == "number":
                control = QSpinBox()
                control.setRange(1, 999999)
                try:
                    number = int(value or spec.default or 1)
                except (TypeError, ValueError):
                    number = int(spec.default or 1)
                control.setValue(max(control.minimum(), min(control.maximum(), number)))
                widget = control
            elif spec.kind == "lines":
                control = QPlainTextEdit()
                control.setMaximumHeight(85)
                control.setPlainText("\n".join(value) if isinstance(value, list) else str(value or ""))
                widget = control
            else:
                control = QLineEdit(str(value or ""))
                if spec.kind in {"file", "folder"}:
                    browse = QPushButton("Elegir…")
                    browse.setProperty("secondary", True)
                    browse.clicked.connect(lambda _checked=False, c=control, k=spec.kind: self._browse(c, k))
                    row = QWidget()
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.addWidget(control, 1)
                    row_layout.addWidget(browse)
                    widget = row
                    self.inputs[(spec.namespace, spec.key)] = control
                    form.addRow(spec.label, row)
                    continue
                widget = control
            self.inputs[(spec.namespace, spec.key)] = widget
            form.addRow(spec.label, widget)
        actions = QHBoxLayout()
        save = QPushButton("Guardar preferencias")
        mail = QPushButton("Probar correo")
        google = QPushButton("Probar Google Sheets")
        seafile = QPushButton("Probar Seafile")
        telcos = QPushButton("Probar Telcos")
        mail.setProperty("secondary", True)
        google.setProperty("secondary", True)
        seafile.setProperty("secondary", True)
        telcos.setProperty("secondary", True)
        save.clicked.connect(self.save)
        mail.clicked.connect(lambda: self._test("email", self.services.test_mail_connection))
        google.clicked.connect(lambda: self._test("default", self.services.test_google_connection))
        seafile.clicked.connect(lambda: self._test("default", self.services.test_seafile_connection))
        telcos.clicked.connect(lambda: self._test("selenium", self.services.test_telcos_connection))
        actions.addWidget(save)
        actions.addWidget(mail)
        actions.addWidget(google)
        actions.addWidget(seafile)
        actions.addWidget(telcos)
        actions.addStretch(1)
        outer.addLayout(actions)
        self.panel = OperationPanel(jobs)
        self.panel.setMaximumHeight(210)
        outer.addWidget(self.panel)

    def _browse(self, field: QLineEdit, kind: str) -> None:
        if kind == "folder":
            path = QFileDialog.getExistingDirectory(self, "Elegir carpeta", field.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Elegir archivo", field.text())
        if path:
            field.setText(path)

    def save(self) -> None:
        def persist() -> None:
            values: dict[tuple[str, str], Any] = {}
            for spec in SETTINGS:
                widget = self.inputs[(spec.namespace, spec.key)]
                if isinstance(widget, QCheckBox):
                    value: Any = widget.isChecked()
                elif isinstance(widget, QSpinBox):
                    value = widget.value()
                elif isinstance(widget, QPlainTextEdit):
                    value = [line.strip() for line in widget.toPlainText().splitlines() if line.strip()]
                else:
                    value = widget.text()  # type: ignore[attr-defined]
                values[(spec.namespace, spec.key)] = value
            self.services.save_settings(values)

        try:
            persist()
        except Exception as exc:
            QMessageBox.critical(self, "Preferencias", str(exc))
        else:
            QMessageBox.information(self, "Preferencias", "Preferencias guardadas. Las contraseñas no se almacenan.")

    def _test(self, kind: str, callback: Callable[[], str]) -> None:
        job_id = self.jobs.submit(kind, lambda _progress, _cancelled: callback())
        self.panel.begin(
            job_id,
            "Probando conexión…",
            completion_popup=True,
            completion_title="Prueba de conexión",
        )




class SettingsPage(QWidget):
    def __init__(
        self,
        services: ApplicationFacade,
        jobs: JobManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(page_header("Configuración", "Catálogos, integraciones y rutas de trabajo."))
        tabs = QTabWidget()
        tabs.addTab(
            CatalogTab(
                [
                    "ID",
                    "Proveedor",
                    "Sobrenombre 1",
                    "Sobrenombre 2",
                    "Sobrenombre 3",
                    "RUC",
                    "Correo",
                    "Correo alterno",
                ],
                services.list_suppliers,
                lambda item: [
                    str(item.id or ""),
                    item.name,
                    item.nickname,
                    item.nickname_2,
                    item.nickname_3,
                    item.ruc,
                    item.email_primary,
                    item.email_secondary,
                ],
                lambda item: SupplierDialog(item, self),
                services.save_supplier,
                services.delete_supplier,
                lambda item: item.id,
                "Buscar por proveedor, sobrenombres, RUC o correo…",
            ),
            "Proveedores",
        )
        tabs.addTab(
            CatalogTab(
                ["Subdepartamento", "Departamento", "Responsable"],
                services.list_assignments,
                lambda item: [item.subdepartment, item.department, item.person],
                lambda item: AssignmentDialog(item, self),
                services.save_assignment,
                services.delete_assignment,
                lambda item: item.subdepartment,
            ),
            "Asignaciones",
        )
        tabs.addTab(
            CatalogTab(
                ["ID", "Nombre", "Firma"],
                services.list_templates,
                lambda item: [str(item.id or ""), item.name, item.signature_path],
                lambda item: TemplateDialog(item, self),
                services.save_template,
                services.delete_template,
                lambda item: item.id,
            ),
            "Plantillas",
        )
        tabs.addTab(PreferencesTab(services, jobs), "Opciones por módulo")
        layout.addWidget(tabs, 1)
