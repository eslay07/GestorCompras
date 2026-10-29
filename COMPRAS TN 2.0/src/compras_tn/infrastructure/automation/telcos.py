from __future__ import annotations

import re
import time
import threading
import hashlib
import base64
import json
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit
from html.parser import HTMLParser

import requests

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSelectorException,
    InvalidSessionIdException,
    JavascriptException,
    NoSuchElementException,
    NoSuchWindowException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.common.exceptions import (
    TimeoutException as SeleniumTimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from compras_tn.application.ports import SettingsRepository
from compras_tn.application.workflows import (
    IRREVERSIBLE_ACTIONS,
    PAUSE_REASONS,
    WorkflowActionExecutor,
    WorkflowEngine,
    WorkflowExecutionError,
    resolve_value,
)
from compras_tn.domain.models import (
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationResult,
    PurchaseMode,
    SessionCredentials,
    TaskRecord,
    WorkflowDefinition,
    utc_now,
)
from compras_tn.infrastructure.automation.browser import create_corporate_browser
from compras_tn.infrastructure.document_files import DocumentFileResolver
from compras_tn.infrastructure.orders import OrderFileService
from compras_tn.paths import AppPaths
from compras_tn.security import sanitize_data, sanitize_text

Locator = tuple[str, str]
DEFAULT_TIMEOUT = 20
LONG_TIMEOUT = 60
QUERY_TIMEOUT = 75
EMPTY_STABILITY_SECONDS = 5.0


class OperationCancelled(RuntimeError):
    """Interrumpe una espera Selenium sin clasificar el elemento como fallido."""


class AuthenticationError(PermissionError):
    """La sesión Telcos no pudo autenticarse o expiró."""


class TaskResultMismatchError(LookupError):
    """La consulta terminó, pero la tabla no corresponde a la tarea solicitada."""


def normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in text if not unicodedata.combining(char)).upper().split()
    )


class DriverFactory:
    def create(self, headless: bool) -> webdriver.Chrome:
        return create_corporate_browser(Path.cwd(), headless)

class TelcosPage:
    BLOCKING_OVERLAYS = (
        (By.CSS_SELECTOR, ".blockUI.blockOverlay"),
        (By.CSS_SELECTOR, "[aria-busy='true']"),
        (By.CSS_SELECTOR, ".dataTables_processing"),
        (By.CSS_SELECTOR, ".loading:not([style*='display: none'])"),
        (By.CSS_SELECTOR, ".spinner:not([style*='display: none'])"),
    )

    def __init__(
        self,
        driver: webdriver.Chrome,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        long_timeout: int = LONG_TIMEOUT,
        query_timeout: int = QUERY_TIMEOUT,
        cancelled: Callable[[], bool] | None = None,
    ):
        self.driver = driver
        self.timeout = timeout
        self.long_timeout = long_timeout
        self.query_timeout = query_timeout
        self.cancelled = cancelled

    def _check_cancelled(self) -> None:
        if self.cancelled and self.cancelled():
            raise OperationCancelled("Operación cancelada por el usuario.")

    def wait(
        self,
        predicate: Callable[[webdriver.Chrome], Any],
        description: str,
        timeout: int | None = None,
    ) -> Any:
        timeout = self.timeout if timeout is None else timeout

        def guarded(driver: webdriver.Chrome) -> Any:
            self._check_cancelled()
            return predicate(driver)

        try:
            return WebDriverWait(
                self.driver,
                timeout,
                poll_frequency=0.2,
                ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
            ).until(guarded)
        except SeleniumTimeoutException as exc:
            raise TimeoutError(f"Tiempo agotado esperando {description} ({timeout}s).") from exc

    @staticmethod
    def visible(element: Any) -> bool:
        try:
            return bool(element.is_displayed())
        except (NoSuchElementException, StaleElementReferenceException):
            return False

    @staticmethod
    def enabled(element: Any) -> bool:
        try:
            return bool(element.is_enabled())
        except (NoSuchElementException, StaleElementReferenceException):
            return False

    def find_now(
        self,
        locators: Iterable[Locator],
        *,
        visible: bool = True,
        enabled: bool = False,
    ) -> Any:
        for locator in locators:
            try:
                elements = self.driver.find_elements(*locator)
            except (NoSuchElementException, StaleElementReferenceException):
                continue
            for element in elements:
                if visible and not self.visible(element):
                    continue
                if enabled and not self.enabled(element):
                    continue
                return element
        return False

    def find(
        self,
        locators: Iterable[Locator],
        description: str,
        *,
        timeout: int | None = None,
        visible: bool = True,
        enabled: bool = False,
    ) -> Any:
        locators = tuple(locators)
        return self.wait(
            lambda _driver: self.find_now(locators, visible=visible, enabled=enabled),
            description,
            timeout,
        )

    def blocking(self) -> bool:
        return bool(self.find_now(self.BLOCKING_OVERLAYS))

    def wait_idle(self, description: str = "que Telcos termine de procesar", timeout: int | None = None) -> None:
        self.wait(lambda _driver: not self.blocking(), description, timeout)

    def _click_target(self, element: Any) -> Any:
        try:
            return self.driver.execute_script(
                "return arguments[0].closest('button,a,[role=button]') || arguments[0];",
                element,
            ) or element
        except (JavascriptException, StaleElementReferenceException):
            return element

    def click_resolved(
        self,
        resolver: Callable[[webdriver.Chrome], Any],
        description: str,
        *,
        timeout: int | None = None,
    ) -> Any:
        timeout = self.timeout if timeout is None else timeout
        last_error: Exception | None = None
        deadline = time.monotonic() + timeout
        for _attempt in range(3):
            self._check_cancelled()
            try:
                element = self.wait(
                    lambda driver: False if self.blocking() else resolver(driver),
                    description,
                    max(0.1, deadline - time.monotonic()),
                )
                element = self._click_target(element)
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center',inline:'nearest'});",
                    element,
                )
                try:
                    element.click()
                except ElementNotInteractableException:
                    self.driver.execute_script("arguments[0].click();", element)
                return element
            except (ElementClickInterceptedException, StaleElementReferenceException) as exc:
                last_error = exc
                try:
                    self.wait_idle(timeout=min(timeout, 10))
                except TimeoutError:
                    pass
            except WebDriverException as exc:
                detail = str(exc).casefold()
                if not any(
                    marker in detail
                    for marker in ("stale", "intercept", "not clickable", "detached")
                ):
                    raise
                last_error = exc
        raise RuntimeError(f"No se pudo activar {description}: {last_error}") from last_error

    def click(
        self,
        locators: Iterable[Locator],
        description: str,
        *,
        timeout: int | None = None,
    ) -> Any:
        locators = tuple(locators)
        return self.click_resolved(
            lambda _driver: self.find_now(locators, enabled=True),
            description,
            timeout=timeout,
        )

    def set_text(
        self,
        locators: Iterable[Locator],
        value: Any,
        description: str,
        *,
        timeout: int | None = None,
    ) -> Any:
        locators = tuple(locators)
        text = "" if value is None else str(value)
        timeout = self.timeout if timeout is None else timeout
        last_error: Exception | None = None
        for attempt in range(3):
            self._check_cancelled()
            element = self.find(locators, description, timeout=timeout, enabled=True)
            try:
                self.wait_idle(timeout=min(timeout, 10))
                try:
                    element.click()
                except ElementNotInteractableException:
                    self.driver.execute_script("arguments[0].focus();", element)
                try:
                    element.clear()
                except (ElementNotInteractableException, WebDriverException):
                    element.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                if str(element.get_attribute("value") or ""):
                    element.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                element.send_keys(text)
                original_id = getattr(element, "id", None)

                def written(_driver: webdriver.Chrome, original_id=original_id) -> Any:
                    current = self.find_now(locators, enabled=True)
                    if not current:
                        return False
                    actual = str(current.get_attribute("value") or "")
                    current_id = getattr(current, "id", None)
                    if (
                        original_id
                        and current_id
                        and current_id != original_id
                        and actual.strip() != text.strip()
                    ):
                        raise ElementNotInteractableException(
                            f"{description} fue reemplazado mientras se escribía."
                        )
                    return current if actual.strip() == text.strip() else False

                return self.wait(written, f"que {description} reciba el valor", min(timeout, 10))
            except (StaleElementReferenceException, ElementNotInteractableException) as exc:
                last_error = exc
                continue
            except TimeoutError as exc:
                last_error = exc
                if attempt < 2:
                    continue
        raise RuntimeError(f"No se pudo escribir en {description}: {last_error}") from last_error

    def wait_hidden(
        self,
        locators: Iterable[Locator],
        description: str,
        timeout: int | None = None,
    ) -> None:
        locators = tuple(locators)
        self.wait(lambda _driver: not self.find_now(locators), description, timeout)

    def busy(self) -> bool:
        if self.blocking():
            return True
        try:
            return bool(
                self.driver.execute_script("return !!(window.jQuery && window.jQuery.active > 0);")
            )
        except JavascriptException:
            return False

    def wait_document(self, timeout: int | None = None) -> None:
        self.wait(
            lambda driver: driver.execute_script("return document.readyState")
            in {"interactive", "complete"},
            "que la página termine de cargar",
            timeout,
        )

    def safe_url(self) -> str:
        try:
            parsed = urlsplit(str(self.driver.current_url or ""))
            return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        except (ValueError, WebDriverException):
            return ""

    def safe_title(self) -> str:
        try:
            return str(self.driver.title or "")
        except WebDriverException:
            return ""


class LoginPage(TelcosPage):
    URL = (
        "https://telcos.telconet.ec/inicio/?josso_back_to=http://telcos.telconet.ec/check"
        "&josso_partnerapp_host=telcos.telconet.ec"
    )

    USER = ((By.NAME, "josso_username"), (By.ID, "josso_username"))
    PASSWORD = ((By.NAME, "josso_password"), (By.ID, "josso_password"))
    MENU = ((By.ID, "spanTareasPersonales"),)
    ERRORS = (
        (By.CSS_SELECTOR, ".alert-danger"),
        (By.CSS_SELECTOR, ".login-error"),
        (By.CSS_SELECTOR, "[role='alert']"),
    )

    def login(self, credentials: SessionCredentials, *, navigate: bool = True) -> None:
        if navigate:
            for attempt in range(2):
                self._check_cancelled()
                try:
                    self.driver.get(self.URL)
                    break
                except SeleniumTimeoutException:
                    self.driver.execute_script("window.stop();")
                    if self.find_now(self.USER) or self.find_now(self.MENU):
                        break
                    if attempt:
                        raise ConnectionError("Telcos no pudo cargar el acceso corporativo tras dos intentos; no se modificó ninguna tarea.") from None
                except WebDriverException as exc:
                    if not any(code in str(exc) for code in ("ERR_CONNECTION_TIMED_OUT", "ERR_CONNECTION_RESET", "ERR_NAME_NOT_RESOLVED")):
                        raise
                    if attempt:
                        raise ConnectionError("No hay respuesta del acceso JOSSO de Telcos. Verifique la conexión corporativa antes de reintentar.") from exc
        self.wait_document(self.long_timeout)
        if self.find_now(self.MENU):
            return
        username = credentials.username.split("@", 1)[0].strip().upper()
        if not username:
            raise AuthenticationError("No existe un usuario corporativo para ingresar a Telcos.")
        self.set_text(self.USER, username, "el usuario Telcos")
        self.set_text(self.PASSWORD, credentials.password, "la contraseña Telcos")
        password = self.find(self.PASSWORD, "la contraseña Telcos", enabled=True)
        try:
            password.send_keys(Keys.RETURN)
        except SeleniumTimeoutException:
            # The login was submitted. Inspect its result without submitting twice.
            self.driver.execute_script("window.stop();")

        def authenticated(_driver: webdriver.Chrome) -> Any:
            menu = self.find_now(self.MENU)
            if menu:
                return menu
            error = self.find_now(self.ERRORS)
            if error:
                detail = str(getattr(error, "text", "") or "").strip()
                raise AuthenticationError(
                    f"Telcos rechazó el inicio de sesión{': ' + detail if detail else '.'}"
                )
            return False

        self.wait(authenticated, "el menú principal de Telcos", self.long_timeout)


class TasksPage(TelcosPage):
    CONFIRMATIONS = (
        (By.ID, "btnSmsCustomOk"),
        (By.ID, "btnMensajeFinTarea"),
        (By.CSS_SELECTOR, ".bootbox.modal.in button[data-bb-handler='ok']"),
    )

    MENU = ((By.ID, "spanTareasPersonales"),)
    SEARCH = ((By.ID, "txtActividad"),)
    GRID = ((By.CSS_SELECTOR, "#gridTareas"),)
    CONSULT = (
        (By.ID, "btnConsultar"),
        (By.XPATH, "//button[contains(., 'Consultar') or contains(@onclick, 'buscar()')]"),
    )

    def __init__(self, driver: webdriver.Chrome, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.current_task = ""

    def ready(self) -> bool:
        return bool(self.find_now(self.SEARCH) and self.find_now(self.GRID))

    def open_personal(self) -> None:
        menu = self.find_now(self.MENU, enabled=True)
        if menu:
            self.click(self.MENU, "Tareas personales", timeout=self.long_timeout)
        elif not self.ready():
            raise AuthenticationError(
                "La sesión Telcos expiró o no se encuentra el menú de tareas."
            )
        self.find(self.SEARCH, "el campo de número de tarea", timeout=self.long_timeout)
        self.find(self.GRID, "la tabla de tareas", timeout=self.long_timeout)
        self.find(self.CONSULT, "el botón Consultar", timeout=self.long_timeout, enabled=True)
        self.current_task = ""

    def enter_task(self, number: str, context: dict[str, Any]) -> None:
        if not str(number).strip():
            raise ValueError("Debe indicar un número de tarea.")
        self.set_text(self.SEARCH, number, "el número de tarea", timeout=self.long_timeout)
        context["numero_tarea_consultada"] = str(number).strip()

    def table_snapshot(self) -> tuple[list[Any], tuple[str, ...], Any]:
        rows: list[Any] = []
        texts: list[str] = []
        for row in self.driver.find_elements(By.CSS_SELECTOR, "#gridTareas tbody tr"):
            try:
                if self.visible(row):
                    text = normalize(getattr(row, "text", ""))
                    rows.append(row)
                    texts.append(text)
            except StaleElementReferenceException:
                continue
        empty = self.find_now(((By.CSS_SELECTOR, "#gridTareas .dataTables_empty"),))
        return rows, tuple(texts), empty

    def row_number(self, row: Any) -> str:
        """Read the task column, never a number mentioned in another field."""
        return self.row_value(row, {"NO TAREA", "N° TAREA", "NUMERO TAREA"})

    def row_value(self, row, names):
        headers = self.driver.find_elements(By.CSS_SELECTOR, "#gridTareas thead tr:last-child th")
        def key(value):
            return re.sub(r"[^A-Z0-9]", "", normalize(value))
        wanted = {key(name) for name in names}
        index = next((i for i, h in enumerate(headers)
                      if key((h.get_attribute("textContent") or h.text)
                             if hasattr(h, "get_attribute") else h.text) in wanted), None)
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        if index is None or index >= len(cells):
            return ""
        return str(cells[index].text).strip()

    @staticmethod
    def _contains_task(row_text: str, task_number: str) -> bool:
        if not task_number:
            return True
        return bool(
            re.search(
                rf"(?<![A-Z0-9]){re.escape(task_number)}(?![A-Z0-9])",
                row_text,
            )
        )

    def _start_table_watch(self, expected: str) -> None:
        try:
            self.driver.execute_script(
                """
                const expected = String(arguments[0] || '').toUpperCase();
                const previous = window.__comprasTNQuery;
                if (previous && previous.observer) previous.observer.disconnect();
                const state = {
                    expected, mutations: 0, draws: 0,
                    requestsStarted: 0, requestsCompleted: 0,
                    observer: null
                };
                const grid = document.querySelector('#gridTareas');
                if (grid && window.MutationObserver) {
                    state.observer = new MutationObserver((records) => {
                        state.mutations += records.length;
                    });
                    state.observer.observe(grid, {
                        childList: true, subtree: true, characterData: true
                    });
                }
                if (window.jQuery) {
                    const $doc = window.jQuery(document);
                    $doc.off('.comprasTN20');
                    $doc.on('preXhr.dt.comprasTN20', function(_event, settings) {
                        if (!settings || !settings.nTable || settings.nTable.id === 'gridTareas') {
                            state.requestsStarted += 1;
                        }
                    });
                    $doc.on('xhr.dt.comprasTN20', function(_event, settings) {
                        if (!settings || !settings.nTable || settings.nTable.id === 'gridTareas') {
                            state.requestsCompleted += 1;
                        }
                    });
                    $doc.on('draw.dt.comprasTN20', function(_event, settings) {
                        if (!settings || !settings.nTable || settings.nTable.id === 'gridTareas') {
                            state.draws += 1;
                        }
                    });
                }
                window.__comprasTNQuery = state;
                """,
                expected,
            )
        except JavascriptException:
            pass

    def _watch_state(self) -> dict[str, int]:
        try:
            value = self.driver.execute_script(
                """
                const s = window.__comprasTNQuery;
                return s ? {
                    mutations: s.mutations || 0,
                    draws: s.draws || 0,
                    requestsStarted: s.requestsStarted || 0,
                    requestsCompleted: s.requestsCompleted || 0
                } : null;
                """
            )
        except JavascriptException:
            value = None
        return value if isinstance(value, dict) else {}

    def _await_table_result(
        self,
        expected: str,
        initial_texts: tuple[str, ...],
        initial_empty: bool,
        description: str,
        *,
        substring: bool = False,
    ) -> Any:
        state: dict[str, Any] = {
            "activity": False,
            "empty_since": None,
            "empty": False,
            "texts": (),
        }

        def result(_driver: webdriver.Chrome) -> Any:
            watch = self._watch_state()
            generation = int(watch.get("mutations", 0)) + int(watch.get("draws", 0))
            if generation:
                state["activity"] = True
            # Solo los bloqueos visuales y la solicitud de esta tabla impiden
            # continuar. Un AJAX ajeno (por ejemplo, una notificación) no debe
            # congelar la búsqueda de tareas.
            if self.blocking():
                state["activity"] = True
                state["empty_since"] = None
                return False
            rows, texts, empty = self.table_snapshot()
            state["texts"] = texts
            state["empty"] = bool(empty)
            if (texts, bool(empty)) != (initial_texts, initial_empty):
                state["activity"] = True
            if not state["activity"]:
                return False
            request_pending = int(watch.get("requestsStarted", 0)) > int(
                watch.get("requestsCompleted", 0)
            )
            if request_pending:
                return False
            for row, text in zip(rows, texts, strict=True):
                matches = expected in text if substring else self.row_number(row) == expected
                if not expected or matches:
                    self.current_task = expected
                    return row
            if empty:
                now = time.monotonic()
                if state["empty_since"] is None:
                    state["empty_since"] = now
                # En páginas sin eventos DataTables se exige estabilidad; cuando
                # existe un draw/xhr terminado, el vacío ya pertenece a esta consulta.
                settled = bool(watch.get("draws") or watch.get("requestsCompleted"))
                if settled or now - float(state["empty_since"]) >= EMPTY_STABILITY_SECONDS:
                    raise LookupError(
                        f"Telcos no devolvió resultados para la tarea {expected or 'indicada'}."
                    )
            else:
                state["empty_since"] = None
            return False

        try:
            return self.wait(result, description, self.query_timeout)
        except TimeoutError as exc:
            if state["empty"]:
                raise LookupError(
                    f"Telcos no devolvió resultados para la tarea {expected or 'indicada'}."
                ) from exc
            if state["activity"] and state["texts"]:
                sample = "; ".join(state["texts"][:3])
                raise TaskResultMismatchError(
                    f"Telcos respondió, pero la tabla no contiene la tarea "
                    f"{expected or 'indicada'}. Resultado recibido: {sample[:300]}"
                ) from exc
            raise

    def consult(self, expected: str) -> None:
        expected = normalize(expected)
        _rows, initial_texts, initial_empty = self.table_snapshot()
        current_input = self.find(self.SEARCH, "el número de tarea")
        entered = normalize(current_input.get_attribute("value"))
        if expected and entered and entered != expected:
            raise ValueError(
                f"El campo de búsqueda contiene '{entered}', no la tarea '{expected}'."
            )
        self._start_table_watch(expected)
        self.click(self.CONSULT, "Consultar", timeout=self.long_timeout)
        self._await_table_result(
            expected,
            initial_texts,
            bool(initial_empty),
            f"el resultado correspondiente a la tarea {expected}",
        )

    def filter(self, text: str) -> None:
        expected = normalize(text)
        _rows, initial_texts, initial_empty = self.table_snapshot()
        self._start_table_watch(expected)
        self.set_text(
            ((By.CSS_SELECTOR, "#gridTareas_wrapper input[type='search']"),),
            text,
            "el filtro de tareas",
        )
        self._await_table_result(
            expected,
            initial_texts,
            bool(initial_empty),
            f"el resultado del filtro {text}",
            substring=True,
        )

    def select_task(self, number: str) -> None:
        requested = normalize(number)

        def row(_driver: webdriver.Chrome) -> Any:
            rows, texts, _empty = self.table_snapshot()
            if requested:
                for element, _text in zip(rows, texts, strict=True):
                    if self.row_number(element) == requested:
                        return element
                return False
            return rows[0] if rows else False

        self.click_resolved(row, f"la fila de la tarea {number or 'visible'}", timeout=self.long_timeout)
        self.current_task = requested or self.current_task

    def _task_row(self) -> Any:
        rows, texts, _empty = self.table_snapshot()
        if self.current_task:
            for row, _text in zip(rows, texts, strict=True):
                if self.row_number(row) == self.current_task:
                    return row
            return False
        return rows[0] if rows else False

    def _row_control(self, selectors: Sequence[str], *, read_only: bool = False) -> Any:
        if not self.current_task:
            raise ValueError("Primero consulte y seleccione el número de tarea antes de usar sus botones.")
        row = self._task_row()
        if not row:
            return False
        if not read_only and normalize(self.row_value(row, {'ESTADO'})) == 'FINALIZADA':
            raise ValueError(f"La tarea {self.current_task} está finalizada; la acción no está disponible.")
        for selector in selectors:
            for element in row.find_elements(By.CSS_SELECTOR, selector):
                if self.visible(element) and self.enabled(element):
                    return element
        return False

    def resume(self) -> None:
        self.click_resolved(
            lambda _driver: self._row_control(
                (
                    "button:has(.glyphicon-play)",
                    "button .glyphicon-step-forward",
                    "a .glyphicon-step-forward",
                    ".glyphicon-step-forward",
                )
            ),
            "Reanudar tarea",
            timeout=self.long_timeout,
        )
        self.find(
            ((By.ID, "txtObservacionTarea"),),
            "el formulario de ejecución",
            timeout=self.long_timeout,
        )

    def enter_observation(self, text: str) -> None:
        self.set_text(((By.ID, "txtObservacionTarea"),), text, "la observación")

    def accept_observation(self) -> None:
        self._assert_no_confirmation()
        self.click(
            (
                (By.ID, "btnGrabarEjecucionTarea"),
                (By.XPATH, "//*[@id='btnGrabarEjecucionTarea']//span"),
            ),
            "Aceptar observación",
        )
        self.find(
            self.CONFIRMATIONS,
            "la confirmación de observación",
            timeout=self.long_timeout,
        )

    def _assert_no_confirmation(self) -> None:
        if self.find_now(self.CONFIRMATIONS):
            raise RuntimeError(
                "Existe una confirmación anterior abierta; ciérrela antes de continuar."
            )

    def close_confirmation(self) -> None:
        self.click(self.CONFIRMATIONS, "el mensaje de confirmación", timeout=15)
        self.wait_hidden(self.CONFIRMATIONS, "que se cierre la confirmación", 15)

    def open_followup(self) -> None:
        self.click_resolved(lambda _driver: self._row_control(("button:has(.glyphicon-list-alt)",)), "Seguimiento")
        self.find(((By.ID, "btnIngresoSeguimiento"),), "el panel de seguimiento")

    def save_followup(self) -> None:
        self._assert_no_confirmation()
        self.click(((By.ID, "btnIngresoSeguimiento"),), "Guardar seguimiento")
        self.find(
            self.CONFIRMATIONS,
            "la confirmación del seguimiento",
            timeout=self.long_timeout,
        )

    def open_upload(self) -> None:
        self.click_resolved(lambda _driver: self._row_control(("button:has(.glyphicon-open-file)",)), "Abrir carga de archivos")
        self.find(
            self.file_inputs(),
            "el selector de archivo",
            visible=False,
            enabled=True,
            timeout=self.long_timeout,
        )

    def remote_file_hashes(self) -> set[str]:
        """Read authenticated attachments, including paginated rows, without uploading."""
        self._assert_no_confirmation()
        self.click_resolved(lambda _driver: self._row_control(("button:has(.glyphicon-eye-open)",), read_only=True), "Ver archivos antes de cargar")
        modal = ((By.ID, "modalVerArchivos"),)
        self.find(modal, "los archivos existentes de la tarea", timeout=self.long_timeout)
        links: set[str] = set()
        seen_pages: set[tuple[str, ...]] = set()
        def empty_row(row):
            text = normalize(row.text)
            return bool(row.find_elements(By.CSS_SELECTOR, '.dataTables_empty')) or (
                not row.find_elements(By.CSS_SELECTOR, 'a[href], button, [data-url], [onclick]') and any(marker in text for marker in (
                    'NO HAY ARCHIVOS', 'NO EXISTEN ARCHIVOS', 'NO TIENE ARCHIVOS',
                    'NO SE ENCONTRARON', 'NINGUN ARCHIVO', 'SIN ARCHIVOS', 'NO DATA AVAILABLE',
                    'NO HAY DATOS', 'NINGUN DATO', 'NO EXISTEN REGISTROS', 'NO SE HAN CARGADO ARCHIVOS', 'NO EXISTE ARCHIVO')))
        def document_urls(panel):
            urls = set()
            for a in panel.find_elements(By.CSS_SELECTOR, 'a[href], [data-url], [data-href], [onclick], iframe[src], embed[src], object[data]'):
                description = normalize(' '.join(str(a.get_attribute(key) or '') for key in ('onclick', 'href', 'title', 'aria-label')))
                if any(word in description for word in ('ELIMINAR', 'BORRAR', 'DELETE', 'GUARDAR', 'SUBIR')):
                    continue
                if 'paginate_button' in str(a.get_attribute('class') or ''):
                    continue
                raw = str(a.get_dom_attribute('href') or a.get_attribute('data-url') or a.get_attribute('data-href') or a.get_attribute('src') or a.get_attribute('data') or '')
                candidates = [raw] if raw and not raw.startswith(('#', 'javascript:')) else []
                script = str(a.get_dom_attribute('onclick') or (raw if raw.startswith('javascript:') else ''))
                # Read only explicit URL literals. IDs passed to download functions
                # are resolved through the actual download control below.
                candidates += re.findall(r'''["']((?:https?://|/|\./|\.\./|blob:)[^"']+)["'](?!\s*\+)''', script)
                for candidate in candidates:
                    if candidate.endswith('/'):
                        continue
                    url = urljoin(self.driver.current_url, candidate)
                    if url.startswith(('https://', 'http://', 'blob:')):
                        urls.add(url)
            return tuple(sorted(urls))
        try:
            for _ in range(100):
                self.wait_idle(timeout=self.long_timeout)
                stable = [None, time.monotonic()]
                def snapshot(_driver):
                    panel = self.find_now(modal)
                    if not panel:
                        return False
                    if self.driver.execute_script('return !!(window.jQuery && window.jQuery.active)'):
                        stable[0] = None
                        return False
                    urls = document_urls(panel)
                    signature = (tuple(sorted(urls)), panel.text)
                    if stable[0] != signature:
                        stable[:] = [signature, time.monotonic()]
                        return False
                    if time.monotonic() - stable[1] < 0.6:
                        return False
                    return (tuple(sorted(urls)),)
                urls, = self.wait(snapshot, "la lista de documentos existentes", self.long_timeout)
                urls = set(urls)
                panel = self.find(modal, "la lista de archivos")
                for row in panel.find_elements(By.CSS_SELECTOR, 'tbody tr'):
                    if empty_row(row) or document_urls(row):
                        continue
                    controls = row.find_elements(By.CSS_SELECTOR, 'button, a, [role="button"], [onclick]')
                    read_controls = [control for control in controls if self._is_file_download_control(control)]
                    if not read_controls:
                        self._capture_file_list_diagnostic(panel)
                        evidence = str(getattr(self, 'file_list_diagnostic_path', 'no disponible'))
                        raise RuntimeError(f"No se pudo interpretar un archivo de Telcos. Diagnóstico de la lista: {evidence}. No se cargó ningún duplicado.")
                    urls.add(self._file_download_url(read_controls[0]))
                urls = tuple(sorted(urls))
                if urls in seen_pages:
                    raise RuntimeError("La lista de archivos no avanzó de página; no se pudo verificar duplicados.")
                seen_pages.add(urls)
                links.update(urls)
                next_button = self.find_now(((By.CSS_SELECTOR, '#modalVerArchivos .paginate_button.next:not(.disabled), #modalVerArchivos button[aria-label="Next page"]:not([disabled])'),), enabled=True)
                if not next_button:
                    break
                self.click(((By.CSS_SELECTOR, '#modalVerArchivos .paginate_button.next:not(.disabled), #modalVerArchivos button[aria-label="Next page"]:not([disabled])'),), "la siguiente página de archivos")
                self.wait(lambda _driver: document_urls(self.find(modal, "la lista de archivos")) != urls,
                    "que cambie la página de archivos", self.long_timeout)
            else:
                raise RuntimeError("Demasiadas páginas de archivos; no se pudo verificar la lista completa.")
            hashes: set[str] = set()
            for url in sorted(links):
                self._check_cancelled()
                try:
                    value = self.driver.execute_async_script("""
                    const url=arguments[0], done=arguments[arguments.length-1];
                    const controller=new AbortController();
                    const timer=setTimeout(()=>controller.abort(),20000);
                    fetch(url,{credentials:'include',signal:controller.signal})
                      .then(async r=>{
                        if(!r.ok || (r.headers.get('content-type')||'').includes('text/html'))
                          throw new Error('El documento no está disponible o la sesión expiró');
                        const data=await r.arrayBuffer();
                        if(!globalThis.crypto?.subtle){
                          const bytes=new Uint8Array(data);let binary='';
                          for(let i=0;i<bytes.length;i+=8192)
                            binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
                          return {bytes:btoa(binary)};
                        }
                        const digest=await crypto.subtle.digest('SHA-256',data);
                        return {hash:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')};
                      }).then(done,error=>done({error:String(error)}))
                      .finally(()=>clearTimeout(timer));
                    """, url)
                except WebDriverException as exc:
                    value = {'error': type(exc).__name__}
                if isinstance(value, dict) and 'bytes' in value:
                    value = {'hash': hashlib.sha256(base64.b64decode(value['bytes'], validate=True)).hexdigest()}
                if not isinstance(value, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(value.get('hash', ''))):
                    try:
                        value = {'hash': self._http_file_hash(url)}
                    except Exception as exc:
                        panel = self.find(modal, "la lista de archivos")
                        self._capture_file_list_diagnostic(panel)
                        evidence = getattr(self, 'file_list_diagnostic_path', 'no disponible')
                        detail = sanitize_text(str(exc))
                        if isinstance(evidence, Path):
                            evidence.with_suffix('.json').write_text(json.dumps({
                                'url': sanitize_text(url), 'browser_error': sanitize_text(str(value)),
                                'download_error': detail}, ensure_ascii=False, indent=2), encoding='utf-8')
                        raise RuntimeError(f"No se pudo comparar un adjunto de Telcos: {detail}. Diagnóstico de archivos: {evidence}. No se envió este archivo ni se repitió una carga.") from exc
                hashes.add(value['hash'])
            return hashes
        finally:
            self.click(((By.CSS_SELECTOR, '#modalVerArchivos button.close, #modalVerArchivos [data-dismiss="modal"]'),
                        (By.XPATH, '//*[@id="modalVerArchivos"]//button[normalize-space(.)="Cerrar"]')), "Cerrar consulta de archivos")
            self.wait_hidden(modal, "el cierre de la consulta de archivos", 15)

    def _http_file_hash(self, url: str) -> str:
        """Read a file/embedded viewer through HTTP with domain-scoped session cookies.

        Some document servers allow downloads but not cross-origin fetch. This
        fallback neither disables TLS validation nor treats login HTML as a file.
        """
        class ViewerLinks(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
            def handle_starttag(self, tag, attrs):
                data = dict(attrs)
                if tag in {'iframe', 'embed'} and data.get('src'):
                    self.links.append(data['src'])
                elif tag == 'object' and data.get('data'):
                    self.links.append(data['data'])
                elif tag == 'a' and 'download' in data and data.get('href'):
                    self.links.append(data['href'])

        self._check_cancelled()
        with requests.Session() as session:
            try:
                cookies = self.driver.execute_cdp_cmd('Network.getCookies', {'urls': [self.driver.current_url, url]})['cookies']
            except WebDriverException:
                cookies = self.driver.get_cookies()
            for cookie in cookies:
                session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain') or urlsplit(self.driver.current_url).hostname,
                                    path=cookie.get('path', '/'), secure=bool(cookie.get('secure')))
            session.headers.update({'Referer': self.driver.current_url,
                                    'User-Agent': self.driver.execute_script('return navigator.userAgent')})
            pending = [url]
            seen = set()
            errors = []
            while pending and len(seen) < 6:
                self._check_cancelled()
                target = pending.pop(0)
                if target in seen or urlsplit(target).scheme not in {'https', 'http'}:
                    continue
                seen.add(target)
                try:
                    with session.get(target, timeout=(10, 20), stream=True) as response:
                        content_type = response.headers.get('Content-Type', '').lower()
                        if not response.ok:
                            errors.append(f'HTTP {response.status_code}')
                            continue
                        attachment = 'attachment' in response.headers.get('Content-Disposition', '').lower()
                        if not attachment and ('text/html' in content_type or 'application/xhtml+xml' in content_type):
                            # A viewer may embed the real document; a login form
                            # has no qualifying file link and remains an error.
                            parser = ViewerLinks()
                            parser.feed(response.text)
                            pending.extend(urljoin(response.url, link) for link in parser.links)
                            errors.append('HTML de visor o inicio de sesión, sin documento descargable' if not parser.links else 'Visor HTML intermedio')
                            continue
                        digest = hashlib.sha256()
                        size = 0
                        for chunk in response.iter_content(128 * 1024):
                            self._check_cancelled()
                            if not chunk:
                                continue
                            if size == 0 and chunk.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                                raise RuntimeError('El servidor devolvió HTML en lugar del documento')
                            digest.update(chunk)
                            size += len(chunk)
                        if not size:
                            errors.append('Documento vacío')
                            continue
                        return digest.hexdigest()
                except requests.RequestException as exc:
                    errors.append(type(exc).__name__)
            raise RuntimeError('; '.join(dict.fromkeys(errors)) or 'No hay dirección descargable del documento')

    @staticmethod
    def _is_file_download_control(control) -> bool:
        description = normalize(' '.join(str(control.get_attribute(key) or '') for key in ('title', 'aria-label', 'onclick', 'href')) + ' ' + control.text)
        if any(word in description for word in ('ELIMINAR', 'BORRAR', 'DELETE', 'GUARDAR', 'SUBIR')):
            return False
        return any(word in description for word in ('DESCARG', 'DOWNLOAD', 'VERARCHIVO', 'VER_ARCHIVO', 'ABRIRARCHIVO')) or bool(
            control.find_elements(By.CSS_SELECTOR, '.glyphicon-download, .glyphicon-download-alt, .fa-download'))

    def _file_download_url(self, control) -> str:
        """Resolve a read-only JS download without opening an unmanaged tab."""
        self.driver.execute_script("""
            window.__comprasFileProbe={open:window.open,urls:[]};
            window.open=function(url){
              const capture=u=>{if(u && u!=='about:blank')window.__comprasFileProbe.urls.push(String(u))};
              capture(url);const location={};Object.defineProperty(location,'href',{set:capture});
              const popup={focus(){},close(){}};
              Object.defineProperty(popup,'location',{get:()=>location,set:capture});return popup;
            };
        """)
        try:
            self.click_resolved(lambda _driver: control, "Descargar archivo existente para comparar")
            urls = self.wait(lambda _driver: self.driver.execute_script('return window.__comprasFileProbe.urls'),
                             "el enlace del control de descarga", min(self.long_timeout, 10))
            url = urljoin(self.driver.current_url, urls[-1])
            if not url.startswith(('https://', 'http://', 'blob:')):
                raise RuntimeError("El control de archivo no devolvió una dirección de descarga válida.")
            return url
        finally:
            self.driver.execute_script('if(window.__comprasFileProbe){window.open=window.__comprasFileProbe.open;delete window.__comprasFileProbe}')

    def _capture_file_list_diagnostic(self, panel) -> None:
        # Preserve structural evidence before closing the modal, never mailbox data.
        path = getattr(self, 'file_list_diagnostic_path', None)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(sanitize_text(panel.get_attribute('outerHTML') or ''), encoding='utf-8')

    def close_upload_without_saving(self) -> None:
        self.click(((By.CSS_SELECTOR, '#modalCagarArchivos button.close, #modalCagarArchivos [data-dismiss="modal"]'),
                    (By.XPATH, '//*[@id="modalCagarArchivos"]//button[normalize-space(.)="Cerrar" or normalize-space(.)="Cancelar"]')),
                   "Cerrar carga sin reenviar archivos")
        self.wait_hidden(((By.ID, 'modalCagarArchivos'),), "el cierre de la carga", 15)

    @staticmethod
    def file_inputs() -> tuple[Locator, ...]:
        return ((By.CSS_SELECTOR, "input[name='archivos[]']"), (By.CSS_SELECTOR, "input[type='file']"))

    def select_file(self, path: Path, context: dict[str, Any]) -> None:
        resolved = str(path.resolve())
        for attempt in range(3):
            field = self.find(
                self.file_inputs(),
                "el selector de archivo",
                visible=False,
                enabled=True,
            )
            try:
                # Telcos may reuse a multiple-file input between uploads.
                # Replace its selection instead of appending the previous file.
                # A file input can be hidden behind Telcos' styled chooser.
                # WebDriver clear() requires interactability; resetting only its
                # selection is allowed without making the control visible.
                self.driver.execute_script("arguments[0].value = '';", field)
                field.send_keys(resolved)

                def received(_driver: webdriver.Chrome) -> bool:
                    current = self.find_now(self.file_inputs(), visible=False, enabled=True)
                    if not current:
                        return False
                    return bool(current.get_attribute("value")) or bool(
                        self.driver.execute_script(
                            "return arguments[0].files && arguments[0].files.length;", current
                        )
                    )

                self.wait(received, "que Telcos reciba el archivo", 20)
                break
            except StaleElementReferenceException:
                if attempt == 2:
                    raise
        context["archivo_seleccionado"] = resolved
        context["archivos_seleccionados"] = [resolved]

    def upload(self, context: dict[str, Any]) -> None:
        if not context.get("archivo_seleccionado"):
            raise ValueError("Primero debe seleccionar un archivo.")
        before = self._upload_state()
        self._assert_no_confirmation()
        self.click(((By.ID, "btnCargarArchivo"),), "Cargar archivo")
        filename = normalize(Path(context["archivo_seleccionado"]).name)

        def completed(_driver: webdriver.Chrome) -> bool:
            if self.find_now(self.CONFIRMATIONS):
                return True
            current = self._upload_state()
            combined = " ".join(current[1])
            return current != before and (
                filename in combined
                or any(word in combined for word in ("CARGADO", "ADJUNTADO", "EXITOSO", "CORRECTAMENTE"))
            )

        self.wait(completed, "la confirmación de carga", self.long_timeout)

    def _upload_state(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        values: list[str] = []
        for locator in self.file_inputs():
            for item in self.driver.find_elements(*locator):
                try:
                    values.append(str(item.get_attribute("value") or ""))
                except StaleElementReferenceException:
                    continue
        messages: list[str] = []
        for selector in (".alert", "[role='alert']", ".modal.in", "#divArchivosTarea", "#gridArchivos"):
            for item in self.driver.find_elements(By.CSS_SELECTOR, selector):
                try:
                    if self.visible(item):
                        messages.append(normalize(getattr(item, "text", "")))
                except StaleElementReferenceException:
                    continue
        return tuple(values), tuple(messages)

    def open_reassignment(self) -> None:
        self.click_resolved(lambda _driver: self._row_control(("button:has(.glyphicon-dashboard)",)), "Reasignar")
        self.find(
            ((By.ID, "txtDepartment"),),
            "el formulario de reasignación",
            timeout=self.long_timeout,
        )

    def select_autocomplete(self, locators: Sequence[Locator], value: str, description: str) -> None:
        locators = tuple(locators)
        self.wait(lambda _driver: not self.busy(), f"cargar la base de {description}", 90)
        self.set_text(locators, value, description)
        field_id = self.find(locators, description, enabled=True).get_attribute("id")
        custom = ((By.CSS_SELECTOR, f"[id='{field_id}autocomplete-list'] > div"),) if field_id else ()
        suggestions = custom or (
            (By.CSS_SELECTOR, "ul.ui-autocomplete li"),
            (By.CSS_SELECTOR, ".tt-menu .tt-suggestion"),
            (By.CSS_SELECTOR, ".typeahead.dropdown-menu li"),
            (By.CSS_SELECTOR, ".select2-results__option"),
        )
        requested = normalize(value)

        def option(_driver: webdriver.Chrome) -> Any:
            visible: list[Any] = []
            for locator in suggestions:
                visible.extend(item for item in self.driver.find_elements(*locator) if self.visible(item))
            for item in visible:
                if requested == normalize(getattr(item, "text", "")):
                    return item
            return False

        for retry in range(3):
            try:
                self.wait(option, f"las opciones exactas de {description}", 30)
                break
            except TimeoutError:
                if retry == 2:
                    available = [item.text for locator in suggestions for item in self.driver.find_elements(*locator)
                                 if self.visible(item)]
                    raise TimeoutError(f"{description}: no se confirmó '{value}' tras 3 búsquedas. Opciones visibles: {available}") from None
                self.wait(lambda _driver: not self.busy(), f"terminar carga de {description}", 30)
                self.set_text(locators, value, description)
        def select_with_keyboard(_driver: webdriver.Chrome) -> bool:
            candidates = []
            for locator in suggestions:
                candidates.extend(item for item in self.driver.find_elements(*locator) if self.visible(item))
            matches = [i for i, item in enumerate(candidates) if requested == normalize(item.text)]
            if len(matches) != 1:
                return False
            target = matches[0]
            field = self.find_now(locators, enabled=True)
            if not field:
                return False
            if "autocomplete-active" in (candidates[target].get_attribute("class") or "").split():
                field.send_keys(Keys.RETURN)
                return True
            field.send_keys(Keys.DOWN)
            return False
        self.wait(select_with_keyboard, f"confirmar {description} con Enter", self.long_timeout)
        # Legacy Telcos commits the autocomplete on blur and then loads employees.
        self.find(locators, description, enabled=True).send_keys(Keys.TAB)

        def selected(_driver: webdriver.Chrome) -> Any:
            field = self.find_now(locators, enabled=True)
            if not field:
                return False
            actual = normalize(field.get_attribute("value"))
            dropdown_open = any(self.visible(item) for locator in custom
                                for item in self.driver.find_elements(*locator))
            return field if requested == actual and not dropdown_open else False

        self.wait(selected, f"la selección de {description}", 15)
        self.wait(lambda _driver: not self.busy(), f"cargar dependencias de {description}", 90)
        if field_id == "txtEmpleado":
            date_locators = ((By.ID, "txtDatetimepickerEjecReasigna"),)
            date_field = self.find(date_locators, "la fecha de ejecución", enabled=True)
            original = date_field.get_attribute("value")
            date_field.send_keys(Keys.RETURN, Keys.TAB)
            self.wait(
                lambda _driver: self.find(date_locators, "la fecha de ejecución").get_attribute("value") == original,
                "conservar la fecha de ejecución después de Enter y Tab", 15,
            )

    def save_reassignment(self) -> None:
        self._assert_no_confirmation()
        self.click(((By.ID, "btnGrabarReasignaTarea"),), "Guardar reasignación")
        def outcome(_driver: Any) -> Any:
            errors = self.driver.find_elements(By.CSS_SELECTOR, ".alert-danger")
            for error in errors:
                if self.visible(error) and error.text.strip():
                    message = error.text
                    if "USR_CREACION" in message and "ORA-01400" in message:
                        raise ValueError("Telcos rechazó la reasignación: ORA-01400 / USR_CREACION nulo. Revisar sesión y soporte de Sistemas. No se reintentará Guardar.")
                    raise ValueError("Telcos rechazó la reasignación. No se reintentará Guardar: " + message[:500])
            return self.find_now(self.CONFIRMATIONS)
        try:
            self.wait(outcome, "confirmación o error de reasignación", self.long_timeout)
        except TimeoutError:
            raise ValueError("Guardado de reasignación sin confirmación. Verificar la tarea en Telcos antes de reintentar.") from None

    def pause(self) -> None:
        self.click_resolved(lambda _driver: self._row_control(("button:has(.glyphicon-pause)",)), "Pausar tarea")
        self.wait(
            lambda _driver: self.pause_select(),
            "el catálogo de pausa",
            self.long_timeout,
        )

    def pause_select(self) -> Any:
        for element in self.driver.find_elements(By.ID, "cmbMotivoPausa"):
            if self.visible(element) and self.enabled(element) and any(
                str(option.get_attribute("value") or "").strip()
                for option in element.find_elements(By.TAG_NAME, "option")
            ):
                return element
        return False

    def select_pause_reason(self, raw: str, context: dict[str, Any]) -> None:
        raw = str(raw or "").strip()
        by_code = {item.split(" - ", 1)[0]: item.split(" - ", 1)[1] for item in PAUSE_REASONS}
        by_label = {normalize(label): code for code, label in by_code.items()}
        code = ""
        label = raw
        if " - " in raw:
            prefix, suffix = raw.split(" - ", 1)
            code, label = prefix.strip(), suffix.strip()
        elif raw.isdigit():
            code = raw
            label = by_code.get(code, "")
        else:
            code = by_label.get(normalize(raw), "")
        if code not in by_code or (label and normalize(label) != normalize(by_code[code])):
            raise ValueError(f"El motivo de pausa '{raw}' no pertenece al catálogo permitido.")
        label = by_code[code]

        def match(_driver: webdriver.Chrome) -> Any:
            select = self.pause_select()
            if not select:
                return False
            for option in select.find_elements(By.TAG_NAME, "option"):
                if str(option.get_attribute("value") or "").strip() == code or normalize(label) in normalize(option.text):
                    return select, option
            return False

        select, option = self.wait(match, f"el motivo {code} - {label}", self.long_timeout)
        value = str(option.get_attribute("value") or code)
        try:
            self.driver.execute_script(
                "arguments[0].value=arguments[1];"
                "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                select,
                value,
            )
        except JavascriptException:
            option.click()
        def selected(_driver: webdriver.Chrome) -> bool:
            current = self.pause_select()
            return bool(current and str(current.get_attribute("value") or "") == value)

        self.wait(selected, "la selección del motivo", 10)
        context["motivo_pausa_valor"] = value
        context["motivo_pausa_label"] = label

    def read_value(self, selector: str, attribute: str) -> str:
        def value(_driver: webdriver.Chrome) -> Any:
            element = self.find_now(((By.CSS_SELECTOR, selector),))
            if not element:
                return False
            raw = (
                getattr(element, "text", "")
                if attribute.casefold() in {"text", "texto"}
                else element.get_attribute(attribute)
            )
            return str(raw).strip() if str(raw or "").strip() else False

        return str(self.wait(value, f"el dato '{attribute}' de {selector}", self.long_timeout))


class SeleniumActionExecutor(WorkflowActionExecutor):
    def wait_ready(self) -> None:
        """Require a quiet interval, including delayed AJAX overlays, between actions."""
        quiet_since = None
        def ready(_driver):
            nonlocal quiet_since
            if self.page.blocking():
                quiet_since = None
                return False
            now = time.monotonic()
            quiet_since = now if quiet_since is None else quiet_since
            return now - quiet_since >= 0.6
        self.page.wait(ready, "que Telcos termine y estabilice la pantalla", self.page.long_timeout)

    def finish_task(self, context: dict[str, Any]) -> None:
        self.wait_ready()
        if self.page.find_now(self.page.CONFIRMATIONS) or self.page.find_now(((By.CSS_SELECTOR, ".modal.in, .modal.show"),)):
            raise RuntimeError("La tarea terminó con un mensaje o ventana abierta. Use «Revisar y reparar flujo» y agregue el cierre correspondiente. No se confirmó ni se repitió ninguna operación.")
        if self.page.current_task:
            def task_state(_driver):
                row = self.page._task_row()
                return (self.page.row_value(row, {'ESTADO'}),) if row else False
            state, = self.page.wait(task_state, "el estado final de la tarea", self.page.long_timeout)
            if normalize(state) in {"EN EJECUCION", "EJECUCION", "EJECUTANDO", "EN PROCESO"}:
                raise RuntimeError("La tarea sigue en ejecución en Telcos. Complete el flujo con Pausar tarea, Seleccionar motivo, Confirmar pausa y cerrar su mensaje antes de iniciar otra tarea. No se pausó automáticamente.")

    def __init__(
        self,
        page: TasksPage,
        settings: SettingsRepository,
        orders: OrderFileService,
    ):
        self.page = page
        self.settings = settings
        self.orders = orders

    def preflight(self, workflow, context):
        if any(step.action_id == "seleccionar_archivo" and step.params.get("modo_archivo") == "tipos" for step in workflow.steps):
            task = TaskRecord(task_number=str(context["task_number"]), payload=context)
            context["document_file_manifests"] = DocumentFileResolver(self.settings).prepare(workflow, task)
        preview = dict(context)
        dynamic = set()
        for index, step in enumerate(workflow.steps, 1):
            if step.action_id == 'capturar_datos_tarea':
                dynamic.update({'telcos_' + key for key in ('estado', 'tarea', 'observacion', 'responsable', 'proceso', 'caso', 'tarea_padre', 'cliente', 'fecha_ejecucion', 'fecha_estado', 'actualizado_por', 'contacto', 'telefono', 'se_factura', 'es_agendado', 'atender_antes', 'tiempo_transcurrido', 'numero_tarea')})
                continue
            if step.action_id == 'capturar_dato':
                dynamic.add(str(step.params.get('nombre', '')))
                continue
            if any('{' + key + '}' in str(step.params) for key in dynamic):
                if step.action_id == 'definir_variable':
                    dynamic.add(str(step.params.get('nombre', '')))
                continue
            try:
                params = resolve_value(step.params, preview)
                if step.action_id == 'definir_variable':
                    preview[str(params['nombre'])] = params['valor']
                if step.action_id == 'seleccionar_archivo' and params.get('modo_archivo') != 'tipos':
                    raw = str(params.get('ruta') or '@archivo_tarea')
                    if raw.startswith('@') and raw != '@archivo_tarea':
                        raw = str(self.settings.get('automation', f'actua_file_alias::{raw[1:]}'.lower(), ''))
                    path = self.orders.find_context_file(preview) if raw == '@archivo_tarea' else Path(raw)
                    if not path.is_file():
                        raise FileNotFoundError(f'No existe el adjunto: {path}')
            except Exception as exc:
                raise WorkflowExecutionError(index, step.action_id, exc, context=context) from exc
        if any(step.action_id == 'subir_archivo' for step in workflow.steps):
            # Verify the read-only file list before resuming or saving anything.
            self.page.open_personal()
            self.page.enter_task(str(context['task_number']), context)
            self.page.consult(str(context['task_number']))
            context['remote_file_hashes'] = self.page.remote_file_hashes()
            context['remote_file_task'] = str(context['task_number'])

    def execute(self, action_id: str, params: dict[str, Any], context: dict[str, Any]) -> None:
        if action_id != 'cerrar_mensaje_ok':
            context.pop('upload_omitted_no_confirmation', None)
        self.wait_ready()
        if self.page.current_task and action_id in {
            'reanudar_tarea', 'abrir_seguimiento', 'abrir_subida_archivo', 'abrir_reasignar', 'pausar_tarea'
        }:
            def validate_state(_driver):
                row = self.page._task_row()
                if not row:
                    return False
                if normalize(self.page.row_value(row, {'ESTADO'})) == 'FINALIZADA':
                    raise ValueError(f'La tarea {self.page.current_task} está finalizada; no admite {action_id}.')
                return True
            self.page.wait(validate_state, "la fila actualizada de la tarea", self.page.long_timeout)
        handler = getattr(self, f"action_{action_id}", None)
        if not callable(handler):
            raise ValueError(f"Acción Selenium no implementada: {action_id}")
        handler(params, context)

    def action_abrir_tareas_personales(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.open_personal()

    def action_ingresar_numero_tarea(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        self.page.enter_task(str(params.get("numero") or context["task_number"]), context)

    def action_consultar(self, _params: dict[str, Any], context: dict[str, Any]) -> None:
        self.page.consult(str(context.get("numero_tarea_consultada") or context["task_number"]))

    def action_filtrar_tareas(self, params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.filter(str(params.get("texto") or ""))

    def action_seleccionar_tarea(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        self.page.select_task(str(params.get("numero") or context.get("numero_tarea_consultada") or context["task_number"]))

    def action_reanudar_tarea(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.resume()

    def action_ingresar_observacion(self, params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.enter_observation(str(params.get("texto") or ""))

    def action_aceptar_observacion(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.accept_observation()

    def action_cerrar_mensaje_ok(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        if _context.pop("upload_omitted_no_confirmation", False):
            return
        self.page.close_confirmation()

    def action_abrir_seguimiento(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.open_followup()

    def action_guardar_seguimiento(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.save_followup()

    def action_escribir_seguimiento(self, params, _context):
        self.page.set_text(((By.ID, 'txtSeguimientoTarea'),), str(params['texto']), 'el seguimiento')

    def action_abrir_subida_archivo(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        if _context.get('remote_file_task') != str(self.page.current_task) or 'remote_file_hashes' not in _context:
            _context["remote_file_hashes"] = self.page.remote_file_hashes()
            _context['remote_file_task'] = str(self.page.current_task)
        self.page.open_upload()

    def action_seleccionar_archivo(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        if params.get("modo_archivo") == "tipos":
            manifest = context["document_file_manifests"][str(context["paso_actual"])]
            DocumentFileResolver.verify(manifest)
            context["typed_upload_manifest"] = manifest
            context["typed_upload_files"] = manifest["files"]
            self.page.select_file(Path(manifest["files"][0]["path"]), context)
            return
        context.pop("typed_upload_files", None)
        context.pop("typed_upload_manifest", None)
        raw = str(params.get("ruta") or "@archivo_tarea").strip()
        if raw.startswith("@") and raw != "@archivo_tarea":
            key = f"actua_file_alias::{raw[1:]}".lower()
            raw = str(self.settings.get("automation", key, ""))
        path = Path(raw) if raw and raw != "@archivo_tarea" else self.orders.find_context_file(context)
        if not path.is_file():
            raise FileNotFoundError(f"No se encontró el archivo: {path}")
        self.page.select_file(path, context)

    def action_subir_archivo(self, _params: dict[str, Any], context: dict[str, Any]) -> None:
        files = context.get("typed_upload_files")
        typed = bool(files)
        if typed:
            DocumentFileResolver.verify(context["typed_upload_manifest"])
        else:
            if not context.get("archivo_seleccionado"):
                raise ValueError("Primero debe seleccionar un archivo.")
            files = [{"path": context["archivo_seleccionado"]}]
        if "remote_file_hashes" not in context:
            raise RuntimeError("Falta verificar los archivos existentes: agregue Abrir carga de archivo antes de seleccionar y subir.")
        remote_hashes = context["remote_file_hashes"]
        outcomes = context.setdefault("document_upload_results", [])
        previous_count = len(outcomes)
        pending = []
        for item in files:
            previous = next((outcome for outcome in outcomes if outcome["path"] == item["path"]), None)
            if previous:
                if previous["status"] in {"Carga confirmada por Telcos", "Omitido: archivo idéntico ya existe en Telcos"}:
                    continue
                raise RuntimeError(f"El archivo {Path(item['path']).name} ya tiene una carga iniciada sin confirmación. No se reenviará automáticamente.")
            with Path(item["path"]).open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest in remote_hashes:
                outcomes.append({"path": item["path"], "sha256": digest,
                    "task_number": context.get("numero_tarea", ""), "status": "Omitido: archivo idéntico ya existe en Telcos"})
            else:
                pending.append({**item, "content_sha256": digest})
        if not pending:
            if len(outcomes) == previous_count:
                return
            # The next guided OK step has no server message when nothing was sent.
            if not context.get("upload_omitted_no_confirmation"):
                self.page.close_upload_without_saving()
            context["upload_omitted_no_confirmation"] = True
            return
        for index, item in enumerate(pending):
            if item["content_sha256"] in remote_hashes:
                outcomes.append({"path": item["path"], "sha256": item["content_sha256"], "status": "Omitido: archivo idéntico ya existe en Telcos"})
                continue
            if index:
                self.page.close_confirmation()
                self.page.open_upload()
            if index or item["path"] != files[0]["path"]:
                self.page.select_file(Path(item["path"]), context)
            if typed:
                DocumentFileResolver.verify({"folder": context["typed_upload_manifest"]["folder"], "files": [item]})
            outcome = {"path": item["path"], "task_number": context.get("numero_tarea", ""), "status": "Carga iniciada; confirmación pendiente"}
            outcomes.append(outcome)
            context["carga_archivos_iniciada"] = True
            self.page.upload(context)
            outcome["status"] = "Carga confirmada por Telcos"
            outcome["sha256"] = item["content_sha256"]
            remote_hashes.add(item["content_sha256"])


    def action_cerrar_mensaje_fin_tarea(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.click(((By.ID, "btnMensajeFinTarea"),), "Cerrar fin de tarea")
        self.page.wait_hidden(
            ((By.ID, "btnMensajeFinTarea"),),
            "que se cierre el mensaje de fin de tarea",
            15,
        )

    def action_abrir_reasignar(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.open_reassignment()

    def action_ingresar_departamento(self, params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.select_autocomplete(((By.ID, "txtDepartment"),), str(params["nombre"]), "Departamento")

    def action_ingresar_empleado(self, params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.select_autocomplete(((By.ID, "txtEmpleado"), (By.NAME, "txtEmpleado")), str(params["nombre"]), "Empleado")

    def action_observacion_reasignacion(self, params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.set_text(((By.ID, "txtaObsTareaFinalReasigna"),), params["texto"], "la observación de reasignación")

    def action_guardar_reasignacion(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.save_reassignment()

    def action_definir_variable(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        context[str(params["nombre"])] = params["valor"]

    def action_capturar_dato(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        selector = str(params["selector_css"])
        attribute = str(params.get("atributo") or "text")
        context[str(params["nombre"])] = self.page.read_value(selector, attribute)

    def action_esperar_elemento(self, params: dict[str, Any], _context: dict[str, Any]) -> None:
        selector = str(params["selector_css"])
        state = str(params.get("estado") or "visible")
        timeout = int(float(params.get("tiempo") or 20))
        if state not in {"visible", "presente", "habilitado", "oculto"}:
            raise ValueError(
                "Estado de espera no válido. Use visible, presente, habilitado u oculto."
            )
        locators = ((By.CSS_SELECTOR, selector),)
        if state == "oculto":
            self.page.wait_hidden(locators, f"que se oculte {selector}", timeout)
        else:
            self.page.find(
                locators,
                f"el elemento {selector}",
                timeout=timeout,
                visible=state != "presente",
                enabled=state == "habilitado",
            )

    def action_pausar_tarea(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.pause()

    def action_motivo_pausa(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        self.page.select_pause_reason(str(params["valor_o_label"]), context)

    def action_aceptar_pausa(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        if not self.page.pause_select():
            raise RuntimeError("El formulario de pausa no está listo.")
        self.page._assert_no_confirmation()
        self.page.click(
            (
                (By.ID, "btnGrabarPausaTarea"),
                (By.CSS_SELECTOR, "#modalEjecucionTarea #btnGrabarEjecucionTarea"),
                (By.XPATH, "//*[@id='btnGrabarPausaTarea']//span"),
            ),
            "Confirmar pausa",
        )
        self.page.find(
            self.page.CONFIRMATIONS,
            "la confirmación de pausa",
            timeout=self.page.long_timeout,
        )

    def action_capturar_datos_tarea(self, _params: dict[str, Any], context: dict[str, Any]) -> None:
        row = self.page.wait(lambda _driver: self.page._task_row(), "la tarea seleccionada")
        fields = {
            "estado": {"Estado"}, "tarea": {"Tarea"}, "observacion": {"Observacion"},
            "responsable": {"Responsable Asignado"}, "proceso": {"Nombre Proceso"},
            "caso": {"Numero Caso"}, "tarea_padre": {"No. Tarea Padre"},
            "cliente": {"Pto. Cliente"}, "fecha_ejecucion": {"Fecha Ejecucion"},
            "fecha_estado": {"Fecha Estado"}, "actualizado_por": {"Actualizado Por"},
            "contacto": {"Nombres de Contacto"}, "telefono": {"Número de Contacto"},
            "se_factura": {"Se Factura"}, "es_agendado": {"Es Agendado"},
            "atender_antes": {"Atender Antes"}, "tiempo_transcurrido": {"TiempoTranscurrido"},
        }
        context.update({f"telcos_{key}": self.page.row_value(row, names) for key, names in fields.items()})
        context["telcos_numero_tarea"] = self.page.row_number(row)

    def action_ver_seguimiento(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.click_resolved(lambda _driver: self.page._row_control(("button:has(.glyphicon-search)",), read_only=True), "Ver seguimiento")
        self.page.find(((By.ID, "modalMostrarSeguimiento"),), "el historial de seguimiento")

    def action_ver_archivos(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        self.page.click_resolved(lambda _driver: self.page._row_control(("button:has(.glyphicon-eye-open)",), read_only=True), "Ver archivos")
        self.page.find(((By.ID, "modalVerArchivos"),), "los documentos cargados")

    def action_cerrar_panel(self, _params: dict[str, Any], _context: dict[str, Any]) -> None:
        panels = ("modalMostrarSeguimiento", "modalVerArchivos", "modalIngresoSeguimiento",
                  "modalCagarArchivos", "modalEjecucionTarea", "modalReasignarTarea",
                  "modalReprogramarTarea")
        # Solo botones de cierre: nunca un botón Guardar, Subir o Aceptar.
        choices = tuple((By.XPATH, f"//*[@id='{panel}']//button[normalize-space(.)='Cerrar' or normalize-space(.)='Cancelar']") for panel in panels)
        self.page.click(choices, "Cerrar ventana sin guardar")
        self.page.wait_hidden(tuple((By.ID, panel) for panel in panels), "el cierre de la ventana", 15)

    def action_verificar_estado(self, params: dict[str, Any], context: dict[str, Any]) -> None:
        expected = normalize(str(params["estado"]))
        def matches(_driver):
            row = self.page._task_row()
            if not row:
                return False
            state = self.page.row_value(row, {"Estado"})
            context["telcos_estado"] = state
            return normalize(state) == expected
        self.page.wait(matches, f"el estado {params['estado']} de la tarea {self.page.current_task}", self.page.long_timeout)


class SeleniumTelcosGateway:
    _workflow_lock = threading.Lock()

    def __init__(
        self,
        settings: SettingsRepository,
        orders: OrderFileService,
        paths: AppPaths,
        driver_factory: DriverFactory | None = None,
    ):
        self.settings = settings
        self.orders = orders
        self.paths = paths
        self.driver_factory = driver_factory or DriverFactory()
        self._diagnostic_secrets: tuple[str, ...] = ()

    def validate(self, credentials: SessionCredentials, *, headless: bool = True) -> None:
        self._diagnostic_secrets = tuple(
            secret for secret in (credentials.password,) if secret
        )
        driver: webdriver.Chrome | None = None
        try:
            driver = self._new_authenticated_driver(credentials, headless, None)
        finally:
            self._safe_quit(driver)

    def execute_workflow(
        self, *args, **kwargs,
    ) -> OperationResult:
        if not self._workflow_lock.acquire(blocking=False):
            raise RuntimeError("Ya hay un flujo de Telcos en ejecución. Espere a que termine; solo se permite una tarea a la vez.")
        try:
            return self._execute_workflow(*args, **kwargs)
        finally:
            self._workflow_lock.release()

    def _execute_workflow(
        self,
        credentials: SessionCredentials,
        workflow: WorkflowDefinition,
        tasks: Sequence[TaskRecord],
        *,
        headless: bool,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OperationResult:
        from compras_tn.application.workflows import expand_workflow
        workflow = expand_workflow(workflow)
        self._diagnostic_secrets = tuple(
            secret for secret in (credentials.password,) if secret
        )
        from compras_tn.infrastructure.workflow_once import WorkflowOnce
        tasks = list({task.task_number: task for task in reversed(list(tasks))}.values())[::-1]
        once = WorkflowOnce(self.paths, workflow)
        active_task = None
        driver: webdriver.Chrome | None = None
        results: list[OperationItem] = []
        pending_tasks = []
        for task in tasks:
            pending = once.pending_task(task)
            if pending is None:
                results.append(OperationItem(key=task.task_number, status=ItemStatus.SKIPPED, message="Este flujo ya está en ejecución o las OC seleccionadas ya se procesaron. No se repetirá. Si el historial anterior no identifica las OC, revise ese resultado antes de reintentar."))
            else:
                pending_tasks.append(pending)
        tasks = pending_tasks
        if not tasks:
            return OperationResult.from_items(results, "No hay tareas nuevas para este flujo.")
        if any(step.action_id == "seleccionar_archivo" and step.params.get("modo_archivo") == "tipos" for step in workflow.steps):
            valid_tasks = []
            resolver = DocumentFileResolver(self.settings)
            for task in tasks:
                if self._is_cancelled(cancelled):
                    return self._cancelled_result(results, tasks)
                try:
                    manifest = resolver.prepare(workflow, task)
                    valid_tasks.append(task.model_copy(update={"payload": {**task.payload, "document_file_manifests": manifest}}))
                except (OSError, ValueError) as exc:
                    results.append(OperationItem(key=task.task_number, status=ItemStatus.FAILED, message=f"No se inició el flujo: {exc}"))
            tasks = valid_tasks
            if not tasks:
                return OperationResult.from_items(results, "Ninguna tarea inició: faltan archivos válidos.")
        try:
            try:
                driver = self._new_authenticated_driver(credentials, headless, cancelled)
            except OperationCancelled:
                return self._cancelled_result(results, tasks)
            except Exception as exc:
                failure = self._startup_failure(tasks, exc, "Ejecución de flujo")
                return OperationResult.from_items([*results, *failure.items], failure.message)
            retries = 1
            for index, task in enumerate(tasks, start=1):
                if self._is_cancelled(cancelled):
                    return self._cancelled_result(results, tasks)
                if not once.claim(task.task_number):
                    results.append(OperationItem(key=task.task_number, status=ItemStatus.SKIPPED, message="Otra ejecución ya inició este flujo para la tarea. No se repetirá."))
                    continue
                active_task = task.task_number
                last_error: Exception | None = None
                diagnostics: list[dict[str, Any]] = []
                final_context: dict[str, Any] = {}
                retry_blocked = False
                for attempt in range(1, retries + 1):
                    if self._is_cancelled(cancelled):
                        return self._cancelled_result(results, tasks)
                    if attempt > 1:
                        try:
                            driver = self._recover_or_replace(
                                driver,
                                credentials,
                                headless,
                                cancelled,
                            )
                        except OperationCancelled:
                            return self._cancelled_result(results, tasks)
                        except Exception as exc:
                            last_error = exc
                            diagnostics.append(
                                self._capture_diagnostic(
                                    driver,
                                    task.task_number,
                                    attempt,
                                    exc,
                                    action_id="recuperar_sesion",
                                )
                            )
                            break
                    page = self._tasks_page(driver, cancelled)
                    engine = WorkflowEngine(
                        SeleniumActionExecutor(page, self.settings, self.orders),
                        progress=(lambda step, total, label, index=index, task=task: progress(index - 1, len(tasks),
                            f"Tarea {task.task_number} · Paso {step}/{total}: {label}")) if progress else None,
                    )
                    try:
                        context = engine.execute(workflow, task)
                        context["diagnosticos_intentos"] = diagnostics
                        results.append(
                            OperationItem(
                                key=task.task_number,
                                status=ItemStatus.SUCCEEDED,
                                message=f"Flujo completado (intento {attempt}).",
                                payload=self._json_safe(context),
                            )
                        )
                        once.finish(task.task_number, "succeeded")
                        active_task = None
                        last_error = None
                        break
                    except OperationCancelled:
                        return self._cancelled_result(results, tasks)
                    except Exception as exc:
                        last_error = exc
                        if isinstance(exc, WorkflowExecutionError):
                            final_context = exc.context
                        diagnostics.append(
                            self._capture_diagnostic(
                                driver,
                                task.task_number,
                                attempt,
                                exc,
                            )
                        )
                        if self._is_cancelled(cancelled):
                            return self._cancelled_result(results, tasks)
                        if not self._can_retry_workflow(exc, attempt, retries):
                            retry_blocked = self._has_irreversible_progress(exc)
                            break
                if last_error is not None:
                    once.finish(task.task_number, "failed")
                    active_task = None
                    cause = self._root_cause(last_error)
                    status = (
                        ItemStatus.NOT_FOUND
                        if isinstance(cause, LookupError)
                        else ItemStatus.FAILED
                    )
                    suffix = (
                        " No se repitió el flujo completo porque Telcos ya pudo haber "
                        "guardado un paso anterior; se detuvo para evitar duplicados."
                        if retry_blocked
                        else ""
                    )
                    evidence = self._diagnostic_suffix(diagnostics)
                    results.append(
                        OperationItem(
                            key=task.task_number,
                            status=status,
                            message=f"{last_error}{suffix}{evidence}",
                            payload=self._json_safe(
                                {
                                    "diagnosticos_intentos": diagnostics,
                                    "contexto_ultimo_intento": final_context,
                                }
                            ),
                        )
                    )
                    # A failed task may still be running in Telcos. Do not resume
                    # another task or replay any completed steps automatically.
                    if workflow.stop_on_error:
                        results.extend(OperationItem(key=remaining.task_number, status=ItemStatus.SKIPPED,
                        message=f"No iniciada: revise primero la tarea {task.task_number}, que falló y podría seguir en ejecución.")
                        for remaining in tasks[index:])
                        break
                if progress:
                    progress(index, len(tasks), f"Tarea {task.task_number}")
            return OperationResult.from_items(results, "Ejecución de flujo finalizada.")
        finally:
            if active_task is not None:
                once.finish(active_task, "failed")
            self._safe_quit(driver)

    def reassign(
        self,
        credentials: SessionCredentials,
        tasks: Sequence[TaskRecord],
        department: str,
        employee: str,
        comment_template: str,
        *,
        headless: bool,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OperationResult:
        self._diagnostic_secrets = tuple(
            secret for secret in (credentials.password,) if secret
        )
        driver: webdriver.Chrome | None = None
        results: list[OperationItem] = []
        try:
            try:
                driver = self._new_authenticated_driver(credentials, headless, cancelled)
            except OperationCancelled:
                return self._cancelled_result(results, tasks)
            except Exception as exc:
                return self._startup_failure(tasks, exc, "Reasignación")
            retries = self._setting_int("actua_retries", 2, 1, 5)
            for index, task in enumerate(tasks, start=1):
                if self._is_cancelled(cancelled):
                    return self._cancelled_result(results, tasks)
                context = dict(task.payload)
                context.update(task_number=task.task_number, proveedor=task.supplier or "N/D")
                last_error: Exception | None = None
                diagnostics: list[dict[str, Any]] = []
                retry_blocked = False
                for attempt in range(1, retries + 1):
                    if self._is_cancelled(cancelled):
                        return self._cancelled_result(results, tasks)
                    if attempt > 1:
                        try:
                            driver = self._recover_or_replace(
                                driver,
                                credentials,
                                headless,
                                cancelled,
                            )
                        except OperationCancelled:
                            return self._cancelled_result(results, tasks)
                        except Exception as exc:
                            last_error = exc
                            diagnostics.append(
                                self._capture_diagnostic(
                                    driver,
                                    task.task_number,
                                    attempt,
                                    exc,
                                    action_id="recuperar_sesion",
                                )
                            )
                            break
                    page = self._tasks_page(driver, cancelled)
                    committed = False
                    step_name = "abrir_tareas_personales"
                    try:
                        step_name = "abrir_tareas_personales"
                        page.open_personal()
                        step_name = "ingresar_numero_tarea"
                        page.enter_task(task.task_number, context)
                        step_name = "consultar"
                        page.consult(task.task_number)
                        step_name = "seleccionar_tarea"
                        page.select_task(task.task_number)
                        step_name = "reanudar_tarea"
                        page.resume()
                        goods = task.purchase_mode == PurchaseMode.BIENES
                        observation = "SE RECIBE LA MERCADERIA" if goods else comment_template.format_map(defaultdict_value(context))
                        step_name = "ingresar_observacion"
                        page.enter_observation(observation)
                        step_name = "aceptar_observacion"
                        committed = True
                        page.accept_observation()
                        step_name = "cerrar_mensaje_ok"
                        page.close_confirmation()
                        if goods:
                            for detail in task.payload.get("details", []):
                                step_name = "registrar_factura_ingreso"
                                page.open_followup()
                                page.set_text(((By.ID, "txtSeguimientoTarea"),),
                                              f"SE INGRESA LA FACTURA {detail['Factura']} CON EL INGRESO {detail['Ingreso']}",
                                              "el seguimiento de factura e ingreso")
                                page.save_followup()
                                page.close_confirmation()
                        step_name = "abrir_reasignar"
                        page.open_reassignment()
                        step_name = "ingresar_departamento"
                        target_department = task.payload["department_override"] if goods else department
                        target_employee = task.payload["employee_override"] if goods else employee
                        page.select_autocomplete(((By.ID, "txtDepartment"),), target_department, "Departamento")
                        step_name = "ingresar_empleado"
                        page.select_autocomplete(((By.ID, "txtEmpleado"), (By.NAME, "txtEmpleado")), target_employee, "Empleado")
                        step_name = "observacion_reasignacion"
                        page.set_text(((By.ID, "txtaObsTareaFinalReasigna"),), "TRABAJO REALIZADO" if goods else observation, "la observación de reasignación")
                        step_name = "guardar_reasignacion"
                        page.save_reassignment()
                        step_name = "cerrar_mensaje_ok"
                        page.close_confirmation()
                        results.append(
                            OperationItem(
                                key=task.task_number,
                                status=ItemStatus.SUCCEEDED,
                                message=f"Tarea reasignada (intento {attempt}).",
                                payload={"diagnosticos_intentos": diagnostics},
                            )
                        )
                        last_error = None
                        break
                    except OperationCancelled:
                        return self._cancelled_result(results, tasks)
                    except Exception as exc:
                        last_error = exc
                        diagnostics.append(
                            self._capture_diagnostic(
                                driver,
                                task.task_number,
                                attempt,
                                exc,
                                action_id=step_name,
                            )
                        )
                        if self._is_cancelled(cancelled):
                            return self._cancelled_result(results, tasks)
                        if committed or not self._is_retryable(exc) or attempt >= retries:
                            retry_blocked = committed
                            break
                if last_error is not None:
                    cause = self._root_cause(last_error)
                    status = (
                        ItemStatus.NOT_FOUND
                        if isinstance(cause, LookupError)
                        else ItemStatus.FAILED
                    )
                    suffix = (
                        " No se reintentó para evitar duplicar la observación ya enviada."
                        if retry_blocked
                        else ""
                    )
                    evidence = self._diagnostic_suffix(diagnostics)
                    results.append(
                        OperationItem(
                            key=task.task_number,
                            status=status,
                            message=f"{last_error}{suffix}{evidence}",
                            payload={"diagnosticos_intentos": diagnostics},
                        )
                    )
                if progress:
                    progress(index, len(tasks), f"Tarea {task.task_number}")
            return OperationResult.from_items(results, "Reasignación finalizada.")
        finally:
            self._safe_quit(driver)

    def _tasks_page(
        self,
        driver: webdriver.Chrome,
        cancelled: Callable[[], bool] | None,
    ) -> TasksPage:
        page = TasksPage(
            driver,
            timeout=self._setting_int("actua_timeout", DEFAULT_TIMEOUT, 5, 120),
            long_timeout=self._setting_int("actua_long_timeout", LONG_TIMEOUT, 10, 180),
            query_timeout=self._setting_int("actua_query_timeout", QUERY_TIMEOUT, 10, 240),
            cancelled=cancelled,
        )
        page.file_list_diagnostic_path = self.paths.diagnostics / f"archivos-telcos-{time.time_ns()}.html"
        return page

    def _login_page(
        self,
        driver: webdriver.Chrome,
        cancelled: Callable[[], bool] | None,
    ) -> LoginPage:
        return LoginPage(
            driver,
            timeout=self._setting_int("actua_timeout", DEFAULT_TIMEOUT, 5, 120),
            long_timeout=self._setting_int("actua_long_timeout", LONG_TIMEOUT, 10, 180),
            cancelled=cancelled,
        )

    def _new_authenticated_driver(
        self,
        credentials: SessionCredentials,
        headless: bool,
        cancelled: Callable[[], bool] | None,
    ) -> webdriver.Chrome:
        driver = self.driver_factory.create(headless)
        try:
            self._login_page(driver, cancelled).login(credentials)
            return driver
        except Exception:
            self._safe_quit(driver)
            raise

    def _recover_or_replace(
        self,
        driver: webdriver.Chrome,
        credentials: SessionCredentials,
        headless: bool,
        cancelled: Callable[[], bool] | None,
    ) -> webdriver.Chrome:
        if self._is_cancelled(cancelled):
            raise OperationCancelled("Operación cancelada por el usuario.")
        try:
            if self._driver_usable(driver):
                # Recarga una URL conocida. Conserva cookies y la sesión, pero
                # elimina modales, referencias obsoletas y estados parciales.
                self._login_page(driver, cancelled).login(credentials, navigate=True)
                return driver
        except OperationCancelled:
            raise
        except Exception:
            pass
        self._safe_quit(driver)
        return self._new_authenticated_driver(credentials, headless, cancelled)

    @staticmethod
    def _driver_usable(driver: webdriver.Chrome | None) -> bool:
        if driver is None:
            return False
        try:
            return driver.execute_script("return 1;") == 1
        except (InvalidSessionIdException, NoSuchWindowException, WebDriverException):
            return False

    @staticmethod
    def _safe_quit(driver: webdriver.Chrome | None) -> None:
        if driver is None:
            return
        try:
            driver.quit()
        except WebDriverException:
            pass

    @staticmethod
    def _is_cancelled(cancelled: Callable[[], bool] | None) -> bool:
        return bool(cancelled and cancelled())

    @staticmethod
    def _cancelled_result(
        items: list[OperationItem], tasks: Sequence[TaskRecord]
    ) -> OperationResult:
        completed = list(items)
        completed.extend(
            OperationItem(
                key=task.task_number,
                status=ItemStatus.SKIPPED,
                message="No procesada por cancelación.",
            )
            for task in tasks[len(items) :]
        )
        return OperationResult(
            status=JobStatus.CANCELLED,
            items=completed,
            message="Operación cancelada por el usuario.",
            finished_at=utc_now(),
        )

    @staticmethod
    def _startup_failure(
        tasks: Sequence[TaskRecord],
        error: Exception,
        operation_name: str,
    ) -> OperationResult:
        items = [
            OperationItem(
                key=task.task_number,
                status=ItemStatus.FAILED,
                message=f"No se pudo iniciar Telcos: {error}",
            )
            for task in tasks
        ]
        return OperationResult.from_items(
            items,
            f"{operation_name} no iniciada: no fue posible abrir la sesión Telcos.",
        )

    @staticmethod
    def _diagnostic_suffix(diagnostics: Sequence[dict[str, Any]]) -> str:
        if not diagnostics:
            return ""
        last = diagnostics[-1]
        evidence = str(last.get("screenshot") or last.get("metadata") or "")
        return f" Diagnóstico: {evidence}" if evidence else ""

    def _setting_int(self, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(float(self.settings.get("automation", key, default)))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _root_cause(error: Exception) -> Exception:
        return error.cause if isinstance(error, WorkflowExecutionError) else error

    @classmethod
    def _has_irreversible_progress(cls, error: Exception) -> bool:
        if not isinstance(error, WorkflowExecutionError):
            return False
        return bool(
            set(error.completed_actions).intersection(IRREVERSIBLE_ACTIONS)
            or error.action_id in IRREVERSIBLE_ACTIONS
        )

    @classmethod
    def _is_retryable(cls, error: Exception) -> bool:
        cause = cls._root_cause(error)
        if isinstance(
            cause,
            (
                AuthenticationError,
                FileNotFoundError,
                InvalidSelectorException,
                OperationCancelled,
                ValueError,
            ),
        ):
            return False
        return isinstance(
            cause,
            (
                LookupError,
                RuntimeError,
                StaleElementReferenceException,
                TimeoutError,
                WebDriverException,
            ),
        )

    @classmethod
    def _can_retry_workflow(
        cls,
        error: Exception,
        attempt: int,
        retries: int,
    ) -> bool:
        return (
            attempt < retries
            and not cls._has_irreversible_progress(error)
            and cls._is_retryable(error)
        )

    def _capture_diagnostic(
        self,
        driver: webdriver.Chrome,
        task_number: str,
        attempt: int,
        error: Exception,
        *,
        action_id: str = "",
    ) -> dict[str, Any]:
        if isinstance(error, WorkflowExecutionError):
            step_number = error.step_number
            action_id = error.action_id
        else:
            step_number = 0
        # Keep filenames short for Windows installations nested in long paths.
        # Task, action and attempt remain available in the metadata file.
        stamp = utc_now().strftime("%H%M%S%f")
        base = self.paths.diagnostics / f"{stamp}_{attempt}"
        diagnostic: dict[str, Any] = {
            "attempt": attempt,
            "step": step_number,
            "action": action_id,
            "error_type": type(self._root_cause(error)).__name__,
            "error": sanitize_text(error, self._diagnostic_secrets),
            "url": "",
            "title": "",
            "screenshot": "",
            "metadata": "",
        }
        try:
            self.paths.diagnostics.mkdir(parents=True, exist_ok=True)
            page = TelcosPage(driver)
            diagnostic["url"] = page.safe_url()
            diagnostic["title"] = page.safe_title()
            screenshot = base.with_suffix(".png")
            if driver.save_screenshot(str(screenshot)):
                diagnostic["screenshot"] = str(screenshot)
            metadata = base.with_suffix(".txt")
            metadata.write_text(
                sanitize_text(
                    "\n".join(
                        (
                            f"Tarea: {task_number}",
                            f"Intento: {attempt}",
                            f"Paso: {step_number}",
                            f"Acción: {action_id}",
                            f"Tipo: {diagnostic['error_type']}",
                            f"Detalle: {error}",
                            f"URL: {diagnostic['url']}",
                            f"Título: {diagnostic['title']}",
                        )
                    ),
                    self._diagnostic_secrets,
                ),
                encoding="utf-8",
            )
            diagnostic["metadata"] = str(metadata)
        except (OSError, WebDriverException):
            pass
        return sanitize_data(diagnostic, self._diagnostic_secrets)

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)


class defaultdict_value(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "N/D"
