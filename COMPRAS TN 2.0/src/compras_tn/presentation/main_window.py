from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from compras_tn.bootstrap import AppContainer
from compras_tn.domain.models import PurchaseMode, SessionCredentials
from compras_tn.presentation.jobs import JobManager
from compras_tn.presentation.operation_pages import (
    DownloadsPage,
    FollowupsPage,
    MassEmailPage,
    ReassignmentPage,
)
from compras_tn.presentation.purchase_orders_page import PurchaseOrderPreloadPage
from compras_tn.presentation.quotations_page import QuotationsPage
from compras_tn.presentation.settings_page import SettingsPage
from compras_tn.presentation.widgets import page_header
from compras_tn.presentation.workflows_page import WorkflowsPage


class LoginPage(QWidget):
    authenticated = Signal(object)

    def __init__(self, container: AppContainer, jobs: JobManager, parent: QWidget | None = None):
        super().__init__(parent)
        self.container = container
        self.jobs = jobs
        self.login_job = ""
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        card = QFrame()
        card.setObjectName("LoginCard")
        card.setMaximumWidth(460)
        layout = QVBoxLayout(card)
        title = QLabel("COMPRAS TN 2.0")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Ingrese con su cuenta corporativa. La contraseña se conserva solo durante esta sesión.")
        subtitle.setWordWrap(True)
        subtitle.setObjectName("PageSubtitle")
        self.username = QLineEdit(
            str(container.services.get_setting("session", "correo_usuario", ""))
        )
        self.username.setPlaceholderText("usuario o correo@telconet.ec")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Contraseña")
        self.submit = QPushButton("Ingresar")
        self.submit.clicked.connect(self.login)
        self.password.returnPressed.connect(self.login)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(14)
        layout.addWidget(QLabel("Usuario"))
        layout.addWidget(self.username)
        layout.addWidget(QLabel("Contraseña"))
        layout.addWidget(self.password)
        layout.addWidget(self.submit)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        jobs.job_finished.connect(self._finished)
        jobs.job_failed.connect(self._failed)

    def login(self) -> None:
        username = self.username.text().strip()
        password = self.password.text()
        if not username or not password:
            self.status.setObjectName("StatusError")
            self.status.setText("Complete usuario y contraseña.")
            return
        self.submit.setEnabled(False)
        self.status.setText("Verificando acceso al correo…")
        self.login_job = self.jobs.submit(
            "email",
            lambda _progress, _cancelled: self.container.services.login(username, password),
        )

    def _finished(self, job_id: str, result: object) -> None:
        if job_id != self.login_job:
            return
        self.submit.setEnabled(True)
        self.login_job = ""
        if isinstance(result, SessionCredentials):
            self.password.clear()
            self.status.setObjectName("StatusSuccess")
            self.status.setText("Sesión iniciada.")
            self.authenticated.emit(result)

    def _failed(self, job_id: str, message: str) -> None:
        if job_id != self.login_job:
            return
        self.submit.setEnabled(True)
        self.login_job = ""
        self.password.clear()
        self.status.setObjectName("StatusError")
        self.status.setText(f"No se pudo iniciar sesión: {message}")


class DashboardPage(QWidget):
    def __init__(self, container: AppContainer, parent: QWidget | None = None):
        super().__init__(parent)
        self.container = container
        layout = QVBoxLayout(self)
        layout.addWidget(
            page_header(
                "Inicio",
                "Centro operativo de Bienes y Servicios. Todas las herramientas trabajan dentro de esta ventana.",
            )
        )
        cards = QGridLayout()
        descriptions = (
            ("Correos masivos", "Valida OC, proveedor, PDF y destinatarios antes del envío."),
            ("Reasignación", "Busca correos, elimina duplicados y reutiliza una sesión Telcos."),
            ("Descargas OC", "Incluye operación normal, abastecimiento y escaneo programado."),
            ("Orquestador Telcos", "Editor visual, bandeja multiorigen y diagnóstico por paso."),
        )
        for index, (title, text) in enumerate(descriptions):
            card = QFrame()
            card.setObjectName("InfoCard")
            card_layout = QVBoxLayout(card)
            heading = QLabel(title)
            font = heading.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            heading.setFont(font)
            description = QLabel(text)
            description.setWordWrap(True)
            card_layout.addWidget(heading)
            card_layout.addWidget(description)
            cards.addWidget(card, index // 2, index % 2)
        layout.addLayout(cards)
        storage = QLabel(f"Datos activos: {container.paths.root}")
        storage.setTextInteractionFlags(Qt.TextSelectableByMouse)
        storage.setObjectName("PageSubtitle")
        layout.addWidget(storage)
        layout.addStretch(1)




class MainWindow(QMainWindow):
    def __init__(self, container: AppContainer, parent: QWidget | None = None):
        super().__init__(parent)
        self.container = container
        self.jobs = JobManager(self)
        self._closing = False
        self._database_closed = False
        self.setWindowTitle("COMPRAS TN 2.0")
        available = self.screen().availableGeometry()
        self.resize(min(1380, int(available.width() * .95)), min(860, int(available.height() * .95)))
        self.root_stack = QStackedWidget()
        self.root_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setCentralWidget(self.root_stack)
        self.login = LoginPage(container, self.jobs)
        self.login.authenticated.connect(self._authenticated)
        self.root_stack.addWidget(self.login)
        self.shell = self._build_shell()
        self.root_stack.addWidget(self.shell)
        self.root_stack.setCurrentWidget(self.login)

    def _build_shell(self) -> QWidget:
        shell = QWidget()
        outer = QHBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        brand = QLabel("COMPRAS TN 2.0")
        brand.setObjectName("Brand")
        self.user_label = QLabel("Sesión cerrada")
        self.user_label.setObjectName("UserLabel")
        side.addWidget(brand)
        side.addWidget(self.user_label)
        nav_scroll = QScrollArea()
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_body = QWidget()
        nav_body.setObjectName("Sidebar")
        self.nav = QVBoxLayout(nav_body)
        self.nav.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget()
        self.nav_buttons: list[QPushButton] = []
        self._add_nav("GENERAL", "Inicio", DashboardPage(self.container))
        self._add_nav("BIENES", "Correos masivos", MassEmailPage(self.container.services, self.jobs, PurchaseMode.BIENES))
        self._add_nav("", "Organizador de archivos", QuotationsPage(self.container.services, self.jobs))
        self._add_nav("", "Carga de OC automática", PurchaseOrderPreloadPage(self.container.services, self.jobs))
        self._add_nav("", "Seguimientos", FollowupsPage(self.container.services, self.jobs))
        self._add_nav("", "Reasignación", ReassignmentPage(self.container.services, self.jobs, PurchaseMode.BIENES))
        self._add_nav("", "Descargas OC", DownloadsPage(self.container.services, self.jobs, PurchaseMode.BIENES))
        self._add_nav("", "Orquestador Telcos", WorkflowsPage(self.container.services, self.jobs, PurchaseMode.BIENES))
        self._add_nav("SERVICIOS", "Correos masivos", MassEmailPage(self.container.services, self.jobs, PurchaseMode.SERVICIOS))
        self._add_nav("", "Reasignación", ReassignmentPage(self.container.services, self.jobs, PurchaseMode.SERVICIOS))
        self._add_nav("", "Descargas OC", DownloadsPage(self.container.services, self.jobs, PurchaseMode.SERVICIOS))
        self._add_nav("", "Orquestador Telcos", WorkflowsPage(self.container.services, self.jobs, PurchaseMode.SERVICIOS))
        self._add_nav(
            "SISTEMA",
            "Configuración",
            SettingsPage(
                self.container.services,
                self.jobs,
            ),
        )
        self.nav.addStretch(1)
        nav_scroll.setWidget(nav_body)
        side.addWidget(nav_scroll, 1)
        logout = QPushButton("Cerrar sesión")
        logout.setObjectName("NavButton")
        logout.clicked.connect(self._logout)
        side.addWidget(logout)
        outer.addWidget(sidebar)
        outer.addWidget(self.pages, 1)
        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)
        return shell

    def _add_nav(self, section: str, label: str, page: QWidget) -> None:
        if section:
            section_label = QLabel(section)
            section_label.setObjectName("SectionLabel")
            self.nav.addWidget(section_label)
        if isinstance(page, DownloadsPage):
            # Descargas OC remains unchanged, including its presentation.
            target = page
        else:
            target = QScrollArea()
            target.setWidgetResizable(True)
            target.setFrameShape(QFrame.NoFrame)
            target.setMinimumSize(0, 0)
            target.setWidget(page)
        self.pages.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        index = self.pages.addWidget(target)
        button = QPushButton(label)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, i=index, b=button: self._navigate(i, b))
        self.nav.addWidget(button)
        self.nav_buttons.append(button)

    def _navigate(self, index: int, active: QPushButton) -> None:
        self.pages.setCurrentIndex(index)
        for button in self.nav_buttons:
            button.setChecked(button is active)

    def _authenticated(self, credentials: SessionCredentials) -> None:
        self.user_label.setText(credentials.email)
        self.root_stack.setCurrentWidget(self.shell)

    def _logout(self) -> None:
        if self.jobs.has_running_jobs():
            QMessageBox.warning(self, "Sesión", "Cancele o espere los procesos activos antes de cerrar sesión.")
            return
        self._stop_schedulers()
        self.container.services.logout()
        self.user_label.setText("Sesión cerrada")
        self.root_stack.setCurrentWidget(self.login)


    def closeEvent(self, event: QCloseEvent) -> None:
        if self._database_closed:
            event.accept()
            return
        if self._closing:
            if self.jobs.has_running_jobs():
                event.ignore()
                QTimer.singleShot(100, self._continue_close)
                return
            self._close_database()
            event.accept()
            return
        if not self.jobs.has_running_jobs():
            self._stop_schedulers()
            self._close_database()
            event.accept()
            return
        answer = QMessageBox.question(
            self,
            "Procesos activos",
            "Hay procesos en ejecución. ¿Solicitar su cancelación y cerrar?",
        )
        if answer == QMessageBox.Yes:
            self._closing = True
            self._stop_schedulers()
            self.jobs.cancel_all()
            self.setEnabled(False)
            self.statusBar().showMessage("Finalizando procesos de forma segura…")
            event.ignore()
            QTimer.singleShot(100, self._continue_close)
        else:
            event.ignore()

    def _continue_close(self) -> None:
        if not self._closing:
            return
        if self.jobs.has_running_jobs():
            QTimer.singleShot(100, self._continue_close)
            return
        self.close()

    def _stop_schedulers(self) -> None:
        for page in self.findChildren(DownloadsPage):
            page.stop_schedule()

    def _close_database(self) -> None:
        if self._database_closed:
            return
        self.container.services.logout()
        self.container.database.close()
        self._database_closed = True
