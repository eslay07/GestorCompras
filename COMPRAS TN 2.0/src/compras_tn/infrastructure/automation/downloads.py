from __future__ import annotations

import filecmp
import hashlib
import json
import logging
import re
import shutil
import time
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    NoSuchElementException,
    NoSuchFrameException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from compras_tn.application.ports import SeafileGateway, SettingsRepository
from compras_tn.domain.models import (
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    SessionCredentials,
    utc_now,
)
from compras_tn.infrastructure.automation.browser import create_corporate_browser
from compras_tn.infrastructure.delivery import MONTHS, task_folder
from compras_tn.infrastructure.orders import OrderFileService
from compras_tn.paths import AppPaths
from compras_tn.security import sanitize_text

PORTAL_URL = (
    "https://cas.telconet.ec/cas/login?service="
    "https://sites.telconet.ec/naf/compras/sso/check"
)
PORTAL_APP_URL = "https://sites.telconet.ec/naf/compras/sso/check"
Locator = tuple[str, str]


class NafCredentialsRequired(RuntimeError):
    """CAS returned a fresh form and the shared login state machine may retry."""


def _normalized(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char))
        .casefold()
        .split()
    )


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(slots=True)
class SupplyDownload:
    key: str
    path: Path | None = None
    error: Exception | None = None


class OrderNotApprovedError(PermissionError):
    """El portal clasificó explícitamente la OC como no descargable."""


class DownloadCancelledError(RuntimeError):
    """La descarga no se inició porque el usuario canceló el lote."""


class OrderPortalPage:
    """Page Object tolerante a las transiciones lentas del portal NAF."""

    USERNAME = (
        (By.ID, "username"),
        (By.NAME, "username"),
        (By.NAME, "j_username"),
        (By.CSS_SELECTOR, "input[placeholder='Nombre de Usuario']"),
        (By.CSS_SELECTOR, "input[placeholder*='Usuario']"),
        (By.CSS_SELECTOR, "input[autocomplete='username']"),
        (By.CSS_SELECTOR, "input[type='email']"),
    )
    PASSWORD = (
        (By.ID, "password"),
        (By.NAME, "password"),
        (By.NAME, "j_password"),
        (By.CSS_SELECTOR, "input[placeholder='Contraseña']"),
        (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
        (By.CSS_SELECTOR, "input[type='password']"),
    )
    SUBMIT = (
        (By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"),
        (By.CSS_SELECTOR, "input.btn-submit[name='submit']"),
        (By.CSS_SELECTOR, "button[name='_eventId_proceed'], input[name='_eventId_proceed']"),
        (
            By.XPATH,
            "//button[contains(translate(normalize-space(.),'Óó','Oo'),'INICIAR SESION')]",
        ),
        (
            By.XPATH,
            "//input[contains(translate(@value,'Óó','Oo'),'INICIAR SESION')]",
        ),
    )
    EXECUTION = (
        (By.CSS_SELECTOR, "input[name='execution']"),
        (By.NAME, "execution"),
    )
    MENU_TOGGLE = (
        (By.CSS_SELECTOR, "mat-toolbar button[value='sidebarclosed']"),
        (By.CSS_SELECTOR, "button.simple-sidenav__toggle"),
        (By.CSS_SELECTOR, "button[aria-label*='menú'], button[aria-label*='menu']"),
        (By.XPATH, "//button[.//mat-icon[normalize-space()='menu']]"),
    )
    ACCESSES = (
        (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and "
            "contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'Accesos')]",
        ),
        (
            By.XPATH,
            "//*[self::a or self::button][contains(translate(normalize-space(.),"
            "'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'Accesos')]",
        ),
    )
    COMPANY_SELECTION = (
        (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and "
            "contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóúñÑ','AEIOUaeiounN'),"
            "'Seleccion de Compania')]",
        ),
        (
            By.XPATH,
            "//*[self::a or self::button][contains(translate(normalize-space(.),"
            "'ÁÉÍÓÚáéíóúñÑ','AEIOUaeiounN'),'Seleccion de Compania')]",
        ),
    )
    COMPANY_INPUT = (
        (By.CSS_SELECTOR, "input[aria-autocomplete='list']"),
        (By.CSS_SELECTOR, "input[role='combobox']"),
    )
    TELCONET_OPTION = (
        (
            By.XPATH,
            "//*[self::mat-option or @role='option' or contains(@class,'mat-option')]"
            "[contains(translate(normalize-space(.),'áéíóú','aeiou'),'TELCONET')]",
        ),
        (
            By.XPATH,
            "//div[contains(@class,'ng-star-inserted') and contains(normalize-space(.),"
            "'TELCONET S.A.')]",
        ),
    )
    CHOOSE_COMPANY = (
        (By.XPATH, "//button[.//span[contains(normalize-space(.),'Elegir')]]"),
        (By.XPATH, "//span[contains(normalize-space(.),'Elegir')]/ancestor::button[1]"),
    )
    CONFIRM_COMPANY = (
        (By.CSS_SELECTOR, "button.swal2-confirm"),
        (By.CSS_SELECTOR, ".swal2-actions button.swal2-confirm"),
        (By.CSS_SELECTOR, ".sweet-alert button.confirm"),
        (By.CSS_SELECTOR, ".swal-modal .swal-button--confirm"),
        (By.XPATH, "//*[@role='dialog']//button[normalize-space(.)='OK']"),
    )
    SSO_RETRY_DIALOG = (
        (By.CSS_SELECTOR, ".swal2-popup, .swal-modal, [role='dialog']"),
    )
    SSO_RETRY_YES = (
        (By.CSS_SELECTOR, ".swal2-popup button.swal2-confirm, .swal-modal button.confirm"),
        (
            By.XPATH,
            "//*[@role='dialog']//button[translate(normalize-space(.),'Íí','Ii')='Si']",
        ),
    )
    QUERIES = (
        (By.XPATH, "//span[normalize-space()='Consultas']"),
        (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and "
            "contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'Consultas')]",
        ),
        (By.XPATH, "//*[self::a or self::button][contains(normalize-space(.),'Consultas')]"),
    )
    ORDER_QUERY_MENU = (
        (By.XPATH, "//span[translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou')='Consulta de Ordenes de Compra']"),
        (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and "
            "contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),"
            "'Consulta de Ordenes de Compra')]",
        ),
        (
            By.XPATH,
            "//*[self::a or self::button][contains(translate(normalize-space(.),"
            "'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'Consulta de Ordenes de Compra')]",
        ),
    )
    ORDER_INPUT = (
        (By.XPATH, "//mat-form-field[.//mat-label[normalize-space()='N° Orden']]//input"),
        (By.CSS_SELECTOR, "input[data-placeholder*='número de la O/C']"),
        (By.CSS_SELECTOR, "input[data-placeholder*='numero de la O/C']"),
        (By.CSS_SELECTOR, "input[placeholder*='O/C']"),
    )
    APPLY_FILTERS = (
        (By.XPATH, "//button[.//span[contains(normalize-space(.),'Aplicar filtros')]]"),
        (By.XPATH, "//button[contains(normalize-space(.),'Aplicar filtros')]"),
    )
    DOWNLOAD_BUTTONS = (
        (By.XPATH, "//mat-icon[normalize-space()='save_alt']"),
        (By.CSS_SELECTOR, "button[aria-label*='Descargar'], button[title*='Descargar']"),
        (By.CSS_SELECTOR, "mat-icon[fonticon='save_alt']"),
    )
    RESULT_ROWS = (
        (By.XPATH, "//table[not(ancestor::table)][.//th[contains(., 'No Orden')]]/tbody/tr[td[2][normalize-space()]]"),
    )
    BUSY = (
        (By.CSS_SELECTOR, "mat-spinner, mat-progress-spinner"),
        (By.CSS_SELECTOR, ".ngx-spinner-overlay, .blockUI.blockOverlay"),
        (By.CSS_SELECTOR, ".loading:not([style*='display: none'])"),
        (By.CSS_SELECTOR, ".spinner:not([style*='display: none'])"),
        (By.CSS_SELECTOR, "[aria-busy='true']"),
        (By.CSS_SELECTOR, ".mat-progress-bar:not([style*='display: none'])"),
    )
    ALERTS = (
        (By.CSS_SELECTOR, ".toast-container, .toast-message"),
        (By.CSS_SELECTOR, ".swal2-html-container, .swal2-content"),
        (By.CSS_SELECTOR, "[role='alert']"),
        (By.CSS_SELECTOR, ".alert-danger, .error-message"),
    )
    EMPTY_RESULTS = (
        (By.CSS_SELECTOR, ".mat-row .mat-cell[colspan], .mat-no-data-row"),
        (By.CSS_SELECTOR, ".dataTables_empty, [class*='no-data'], [class*='empty']"),
        (
            By.XPATH,
            "//*[contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),"
            "'No se han encontrado datos') or contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'No se encontraron') or contains(translate(normalize-space(.),"
            "'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'Sin resultados') or contains("
            "translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'No existen registros')]",
        ),
    )

    def __init__(
        self,
        driver: webdriver.Chrome,
        download_folder: Path,
        *,
        diagnostics_folder: Path | None = None,
        element_timeout: int = 45,
        login_timeout: int = 100,
        query_timeout: int = 75,
        download_timeout: int = 120,
        login_attempts: int = 3,
        auth_module: str = "descargas_oc",
        headless: bool = False,
    ):
        self.driver = driver
        self.download_folder = download_folder
        self.diagnostics_folder = diagnostics_folder
        self.element_timeout = element_timeout
        self.login_timeout = login_timeout
        self.query_timeout = query_timeout
        self.download_timeout = download_timeout
        self.login_attempts = max(1, min(int(login_attempts), 3))
        self.auth_module = auth_module
        self.headless = bool(headless)
        self._diagnostic_secrets: tuple[str, ...] = ()
        self._submitted_executions: set[str] = set()

    @staticmethod
    def _visible(element: Any) -> bool:
        try:
            return bool(element.is_displayed())
        except (AttributeError, StaleElementReferenceException, WebDriverException):
            return False

    @staticmethod
    def _enabled(element: Any) -> bool:
        try:
            return bool(element.is_enabled())
        except (StaleElementReferenceException, WebDriverException):
            return False

    def _wait(self, predicate: Callable[[webdriver.Chrome], Any], description: str, timeout: int) -> Any:
        started = time.monotonic()
        next_progress = started + 10
        def guarded(driver):
            nonlocal next_progress
            cancelled = getattr(self, 'cancelled', None)
            if cancelled and cancelled():
                raise DownloadCancelledError('Descarga cancelada durante la espera.')
            now = time.monotonic()
            callback = getattr(self, 'auth_progress', None)
            if callback and now >= next_progress:
                callback(f"Esperando {description}: {int(now - started)} de {int(timeout)}s")
                next_progress = now + 10
            return predicate(driver)
        try:
            return WebDriverWait(
                self.driver,
                timeout,
                poll_frequency=0.25,
                ignored_exceptions=(
                    NoSuchElementException,
                    NoSuchFrameException,
                    StaleElementReferenceException,
                ),
            ).until(guarded)
        except TimeoutException as exc:
            raise TimeoutError(f"Tiempo agotado esperando {description} ({timeout}s).") from exc

    def _handles(self) -> list[str]:
        try:
            handles = list(self.driver.window_handles)
            current = self.driver.current_window_handle
        except WebDriverException:
            return []
        ordered = [current]
        ordered.extend(handle for handle in reversed(handles) if handle != current)
        return ordered

    def _elements_in_current_context(
        self,
        locators: Iterable[Locator],
        *,
        visible: bool,
        enabled: bool,
    ) -> list[Any]:
        for locator in locators:
            try:
                elements = self.driver.find_elements(*locator)
            except WebDriverException:
                continue
            usable = [
                element
                for element in elements
                if (not visible or self._visible(element))
                and (not enabled or self._enabled(element))
            ]
            if usable:
                return usable
        return []

    def _search_frames(
        self,
        locators: tuple[Locator, ...],
        *,
        visible: bool,
        enabled: bool,
        depth: int,
    ) -> list[Any]:
        elements = self._elements_in_current_context(
            locators, visible=visible, enabled=enabled
        )
        if elements:
            return elements
        if depth <= 0:
            return []
        try:
            frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe, frame")
        except WebDriverException:
            return []
        for frame in frames:
            try:
                self.driver.switch_to.frame(frame)
                found = self._search_frames(
                    locators,
                    visible=visible,
                    enabled=enabled,
                    depth=depth - 1,
                )
                if found:
                    return found
            except (NoSuchFrameException, StaleElementReferenceException, WebDriverException):
                pass
            try:
                self.driver.switch_to.parent_frame()
            except WebDriverException:
                break
        return []

    def _elements_now(
        self,
        locators: Iterable[Locator],
        *,
        visible: bool = True,
        enabled: bool = False,
    ) -> list[Any]:
        locators = tuple(locators)
        for handle in self._handles():
            try:
                self.driver.switch_to.window(handle)
                self.driver.switch_to.default_content()
            except WebDriverException:
                continue
            found = self._search_frames(
                locators, visible=visible, enabled=enabled, depth=3
            )
            if found:
                return found
        return []

    def _find_now(
        self,
        locators: Iterable[Locator],
        *,
        visible: bool = True,
        enabled: bool = False,
    ) -> Any:
        elements = self._elements_now(locators, visible=visible, enabled=enabled)
        return elements[0] if elements else False

    def _find(
        self,
        locators: Iterable[Locator],
        description: str,
        *,
        timeout: int | None = None,
        visible: bool = True,
        enabled: bool = False,
    ) -> Any:
        locators = tuple(locators)
        return self._wait(
            lambda _driver: self._find_now(
                locators, visible=visible, enabled=enabled
            ),
            description,
            timeout or self.element_timeout,
        )

    def _click_element(self, element: Any) -> None:
        if getattr(element, "tag_name", "") in ("span", "mat-icon"):
            parents = element.find_elements(
                By.XPATH, "./ancestor::*[self::a or self::button or @role='button'][1]")
            if parents:
                element = parents[0]
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                element,
            )
        except WebDriverException:
            pass
        # Never dispatch a synthetic click through a loading layer.
        element.click()

    def _click(
        self,
        locators: Iterable[Locator],
        description: str,
        *,
        timeout: int | None = None,
    ) -> Any:
        locators = tuple(locators)
        def click_ready(_driver: Any) -> Any:
            if self._find_now(self.BUSY):
                return False
            element = self._find_now(locators, enabled=True)
            if not element:
                return False
            try:
                self._click_element(element)
                return element
            except (ElementClickInterceptedException, ElementNotInteractableException,
                    StaleElementReferenceException):
                return False
        return self._wait(click_ready, f"pulsar {description} sin bloqueos",
                          timeout or self.element_timeout)

    def _write(
        self,
        locators: Iterable[Locator],
        text: str,
        description: str,
        *,
        verify: bool = True,
    ) -> Any:
        locators = tuple(locators)
        last_error: Exception | None = None
        for _attempt in range(3):
            element = self._find(locators, description, enabled=True)
            try:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", element
                )
                element.click()
                element.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                element.send_keys(text)
                if not verify:
                    return element
                if str(element.get_attribute("value") or "").strip() != text.strip():
                    self.driver.execute_script(
                        """
                        const element = arguments[0];
                        const value = arguments[1];
                        const prototype = element instanceof HTMLTextAreaElement
                          ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
                        setter.call(element, value);
                        element.dispatchEvent(new Event('input', {bubbles: true}));
                        element.dispatchEvent(new Event('change', {bubbles: true}));
                        """,
                        element,
                        text,
                    )
                return self._wait(
                    lambda _driver, element=element: element
                    if str(element.get_attribute("value") or "").strip() == text.strip()
                    else False,
                    f"que {description} reciba el valor",
                    8,
                )
            except (TimeoutError, StaleElementReferenceException, WebDriverException) as exc:
                last_error = exc
        raise RuntimeError(f"No fue posible escribir en {description}.") from last_error

    def _busy(self) -> bool:
        if self._find_now(self.BUSY):
            return True
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const jqBusy = !!(window.jQuery && window.jQuery.active > 0);
                    let angularBusy = false;
                    try {
                      const tests = window.getAllAngularTestabilities
                        ? window.getAllAngularTestabilities() : [];
                      angularBusy = tests.some(test => !test.isStable());
                    } catch (_) {}
                    return jqBusy || angularBusy;
                    """
                )
            )
        except WebDriverException:
            return False

    def wait_idle(self, *, timeout: int = 30, stable_for: float = 0.5) -> None:
        stable_since: float | None = None

        def idle(_driver: webdriver.Chrome) -> bool:
            nonlocal stable_since
            if self._busy():
                stable_since = None
                return False
            try:
                ready = self.driver.execute_script("return document.readyState")
            except WebDriverException:
                ready = None
            if ready not in {"interactive", "complete"}:
                stable_since = None
                return False
            now = time.monotonic()
            stable_since = stable_since or now
            return now - stable_since >= stable_for

        self._wait(idle, "que la página termine de cargar", timeout)

    def _navigate(self, url: str) -> None:
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                self.driver.get(url)
            except TimeoutException as exc:
                last_error = exc
                # Do not stop CAS/SSO redirects that outlive page_load_timeout.
                return
            except WebDriverException as exc:
                if not any(code in str(exc) for code in ("ERR_CONNECTION_TIMED_OUT", "ERR_CONNECTION_RESET", "ERR_NAME_NOT_RESOLVED")):
                    raise
                last_error = exc
                continue
            try:
                self._wait(
                    lambda _driver: self.driver.execute_script(
                        "return document.readyState === 'interactive' || "
                        "document.readyState === 'complete'"
                    ),
                    "la respuesta inicial del portal",
                    min(self.element_timeout, 30),
                )
                return
            except TimeoutError:
                # A still-loading document belongs to the authentication observer;
                # another get() here could abort an in-flight CAS redirect.
                return
        raise TimeoutError("NAF no respondió al abrir el acceso corporativo tras dos intentos. La consulta de OC todavía no se inició; revise la conexión al portal CAS.") from last_error

    def _login_error(self) -> str:
        texts: list[str] = []
        for element in self._elements_now(self.ALERTS):
            try:
                text = " ".join((element.text or "").split())
            except (StaleElementReferenceException, WebDriverException):
                continue
            normalized = _normalized(text)
            if text and any(
                marker in normalized
                for marker in (
                    "credencial",
                    "contrasena incorrect",
                    "usuario incorrect",
                    "autenticacion fallida",
                    "authentication failed",
                    "invalid username",
                )
            ):
                texts.append(text)
        return " | ".join(texts)

    def _cas_execution_fingerprint(self) -> str:
        """Identify the current CAS flow state without exposing its token."""
        field = self._find_now(self.EXECUTION, visible=False)
        if not field:
            return ""
        try:
            value = str(field.get_attribute("value") or "").strip()
        except (AttributeError, StaleElementReferenceException, WebDriverException):
            return ""
        return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""

    def _flow_execution_error(self) -> bool:
        try:
            query = parse_qs(urlsplit(self.driver.current_url).query)
        except (AttributeError, WebDriverException):
            return False
        messages = " ".join(
            str(value)
            for key, values in query.items()
            if "exception" in key.casefold()
            for value in values
        )
        return "error decoding flow execution" in _normalized(messages)

    def _fresh_cas_execution(self, previous: str = "", *, timeout: float = 3.0) -> str:
        def fresh(_driver: webdriver.Chrome) -> str | bool:
            fingerprint = self._cas_execution_fingerprint()
            if (
                fingerprint
                and fingerprint != previous
                and fingerprint not in self._submitted_executions
            ):
                return fingerprint
            return False

        return str(
            self._wait(
                fresh,
                "un estado nuevo del formulario CAS",
                timeout,
            )
        )

    def _prepare_cas_execution(self, previous: str = "") -> str:
        try:
            return self._fresh_cas_execution(previous)
        except TimeoutError:
            self._auth_transition("Recuperando formulario CAS con un estado nuevo")
            self._navigate(PORTAL_URL)
            return self._fresh_cas_execution(previous)

    def _shell_landmark(self) -> str | bool:
        if self._find_now(self.ORDER_INPUT):
            return "orders"
        if self._find_now(self.COMPANY_INPUT):
            return "company"
        if self._find_now(self.ORDER_QUERY_MENU):
            return "order-menu"
        if self._find_now(self.QUERIES):
            return "queries"
        if self._find_now(self.ACCESSES):
            return "accesses"
        url = urlsplit(self.driver.current_url)
        if url.hostname == "sites.telconet.ec" and url.path.startswith("/naf/compras/") and self._find_now((
            (By.XPATH, "//*[self::h1 or self::h2 or self::h3 or self::h4][normalize-space(.)='Dashboard']"),
        )):
            return "dashboard"
        return False

    def _auth_transition(self, state: str) -> None:
        if getattr(self, "_auth_state", "") == state:
            return
        self._auth_state = state
        elapsed = time.monotonic() - getattr(self, "_auth_started", time.monotonic())
        logging.getLogger(__name__).info("NAF estado=%s tiempo=%.1fs", state, elapsed)
        callback = getattr(self, "auth_progress", None)
        if callback:
            callback(state)

    def _toggle_menu_now(self) -> bool:
        toggle = self._find_now(self.MENU_TOGGLE, enabled=True)
        if not toggle:
            return False
        try:
            self._click_element(toggle)
            return True
        except WebDriverException:
            return False

    def _ensure_navigation_open(self) -> None:
        def opened(_driver: Any) -> bool:
            return bool(self.driver.execute_script("""
                const n=document.querySelector('#snav,mat-sidenav,mat-drawer');
                if(!n) return true;
                const r=n.getBoundingClientRect();
                return r.width>120 && r.right>120 && r.left>=-1;
            """))
        try:
            if opened(self.driver):
                return
            opening = self.driver.execute_script("""
                const n=document.querySelector('#snav,mat-sidenav,mat-drawer');
                return !!n && n.classList.contains('mat-drawer-opened')
                    && n.getBoundingClientRect().width>120;
            """)
            if opening:
                self._wait(opened, "terminar de desplegar el panel lateral", self.element_timeout)
                return
        except (AttributeError, WebDriverException):
            return
        self._auth_transition("Desplegando el panel lateral de NAF")
        self._wait(lambda _driver: not self._find_now(self.BUSY) and self._toggle_menu_now(),
                   "pulsar el boton del panel lateral sin bloqueos", self.element_timeout)
        self._wait(opened, "el panel lateral desplegado", self.element_timeout)

    def _wait_for_shell(self, timeout: int, *, submitted_execution: str = "") -> str:
        last_toggle = 0.0
        last_retry = 0.0
        retry_clicks = 0
        last_url = ""
        stable_since = 0.0
        restored_service = False

        def shell(_driver: webdriver.Chrome) -> str | bool:
            nonlocal last_retry, last_toggle, retry_clicks, last_url, stable_since, restored_service
            error = self._login_error()
            if error:
                raise PermissionError(f"El portal rechazó el inicio de sesión: {error}")
            landmark = self._shell_landmark()
            if landmark:
                self._auth_transition("Sesión NAF autenticada")
                return landmark
            now = time.monotonic()
            # URLs are used only in memory; never log query strings/tickets.
            current_url = self.driver.current_url
            if current_url != last_url:
                last_url, stable_since = current_url, now
            url = urlsplit(current_url)
            if url.hostname == "cas.telconet.ec" and self._find_now(self.USERNAME):
                self._auth_transition("Formulario CAS; esperando redirección")
                password = self._find_now(self.PASSWORD)
                empty_form = bool(password) and not password.get_attribute("value")
                current_execution = self._cas_execution_fingerprint()
                if self._flow_execution_error() and empty_form:
                    if current_execution and current_execution != submitted_execution:
                        message = (
                            "CAS descartó el estado del intento anterior y entregó "
                            "un formulario nuevo."
                        )
                    else:
                        message = (
                            "CAS descartó el estado del intento anterior; se esperará "
                            "un formulario nuevo."
                        )
                    raise NafCredentialsRequired(message)
                if now - stable_since >= 3:
                    generic = not parse_qs(url.query).get("service")
                    if not generic and not restored_service and not empty_form:
                        # The submitted form may still be waiting for its POST.
                        return False
                    if generic and not restored_service:
                        self._auth_transition("Recuperando sesión NAF: restaurando destino de Compras")
                        self._navigate(PORTAL_URL)
                        restored_service = True
                        last_url, stable_since = "", now
                    else:
                        raise NafCredentialsRequired("CAS vuelve a solicitar credenciales; se requiere el siguiente intento permitido.")
                return False
            dialog = self._find_now(self.SSO_RETRY_DIALOG)
            dialog_text = _normalized(getattr(dialog, "text", "")) if dialog else ""
            if dialog and "no se pudo validar la sesion" in dialog_text:
                self._auth_transition("Recuperando sesión NAF…")
                if retry_clicks < 2 and (retry_clicks == 0 or now - last_retry >= 5):
                    affirmative = self._find_now(self.SSO_RETRY_YES, enabled=True)
                    if affirmative:
                        self._click_element(affirmative)
                        retry_clicks += 1
                        last_retry = now
                return False
            self._auth_transition("Redirección NAF en curso")
            if now - last_toggle >= 1.5:
                self._toggle_menu_now()
                last_toggle = now
            return False

        return str(self._wait(shell, "la aplicación NAF y su menú de accesos", timeout))

    def _wait_for_any(
        self,
        alternatives: tuple[tuple[Iterable[Locator], str], ...],
        description: str,
        *,
        timeout: int,
    ) -> str:
        def resolve(_driver: webdriver.Chrome) -> str | bool:
            for locators, name in alternatives:
                if self._find_now(locators):
                    return name
            return False

        return str(self._wait(resolve, description, timeout))

    def _open_menu_item(
        self,
        locators: Iterable[Locator],
        description: str,
        expected: tuple[tuple[Iterable[Locator], str], ...],
    ) -> str:
        last_error: Exception | None = None
        lazy_route = locators == self.ORDER_QUERY_MENU or locators == getattr(self, "GOODS", None)
        deadline = time.monotonic() + self.element_timeout
        for _attempt in range(3):
            for expected_locators, expected_name in expected:
                if self._find_now(expected_locators):
                    return expected_name
            if not self._find_now(locators):
                self._toggle_menu_now()
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._click(locators, description, timeout=remaining)
                remaining = deadline - time.monotonic()
                if lazy_route:
                    # This route downloads a separate Angular bundle. Do not
                    # click it again while that bundle is loading on a slow link.
                    remaining = max(remaining, self.query_timeout, self.login_timeout, 120)
                    deadline = time.monotonic() + remaining
                    self._auth_transition(f"Cargando {description} en NAF")
                if remaining <= 0:
                    break
                return self._wait_for_any(
                    expected,
                    f"el contenido posterior a {description}",
                    timeout=remaining,
                )
            except DownloadCancelledError:
                raise
            except (TimeoutError, RuntimeError, StaleElementReferenceException) as exc:
                last_error = exc
                if lazy_route and isinstance(exc, TimeoutError):
                    raise TimeoutError(
                        f"NAF autentico la sesion, pero {description} no termino "
                        "de cargar. Revise los recursos pendientes del diagnostico. "
                        "No se repitio el clic ni se inicio ninguna operacion de OC."
                    ) from exc
                self._toggle_menu_now()
        raise TimeoutError(f"No se pudo abrir {description}.") from last_error

    def login_and_open_orders(self, credentials: SessionCredentials) -> None:
        self._diagnostic_secrets = tuple(
            secret for secret in (credentials.password,) if secret
        )
        try:
            self._login_and_open_orders(credentials)
        except (NafCredentialsRequired, InvalidSessionIdException, NoSuchWindowException):
            raise
        except Exception as exc:
            diagnostic = self.capture_diagnostic("inicio_y_menu", exc)
            suffix = f" Diagnóstico: {diagnostic}" if diagnostic else ""
            if isinstance(exc, PermissionError):
                raise PermissionError(f"{exc}{suffix}") from exc
            if isinstance(exc, TimeoutError):
                try:
                    parsed = urlsplit(self.driver.current_url)
                except (AttributeError, WebDriverException):
                    parsed = urlsplit("")
                if parsed.hostname == "sites.telconet.ec" and parsed.path.endswith("/sso/check"):
                    raise TimeoutError(
                        "NAF no completo la validacion SSO ni abrio el menu. "
                        "No se inicio ninguna operacion de OC. "
                        "Revise las respuestas HTTP y los fallos de red del diagnostico."
                        + suffix
                    ) from exc
                raise TimeoutError(f"{exc}{suffix}") from exc
            raise RuntimeError(f"No se pudo abrir Consulta de Órdenes.{suffix} {exc}") from exc

    def _login_and_open_orders(self, credentials: SessionCredentials) -> None:
        self._auth_started = time.monotonic()
        self._auth_transition("Abriendo NAF y su acceso corporativo")
        if not getattr(self, "_login_started", False):
            self._navigate(PORTAL_URL)
            self._login_started = True
        try:
            self.wait_idle(timeout=min(self.element_timeout, 10), stable_for=1.0)
        except TimeoutError:
            pass
        landmark = self._wait(
            lambda _driver: self._shell_landmark() or ("cas" if self._find_now(self.USERNAME) else False),
            "el formulario CAS o la sesión autenticada", self.login_timeout,
        )
        if landmark == "cas":
            cas_username = credentials.username.split("@", 1)[0].strip().upper()
            if not cas_username:
                raise PermissionError(
                    "No existe un usuario corporativo para ingresar a NAF."
                )
            previous_execution = ""
            last_retry: Exception | None = None
            for attempt in range(1, self.login_attempts + 1):
                attempt_started = time.monotonic()
                execution = self._prepare_cas_execution(previous_execution)
                self._auth_transition(
                    f"Enviando credenciales a CAS (intento {attempt} de {self.login_attempts})"
                )
                self._write(self.USERNAME, cas_username, "el usuario")
                password_field = self._write(
                    self.PASSWORD, credentials.password, "la contraseña"
                )
                self._submitted_executions.add(execution)
                previous_execution = execution
                try:
                    password_field.send_keys(Keys.ENTER)
                except TimeoutException:
                    pass  # El POST puede haberse enviado; nunca se pulsa dos veces.
                try:
                    landmark = self._wait_for_shell(
                        self.login_timeout,
                        submitted_execution=execution,
                    )
                    logging.getLogger(__name__).info(
                        "NAF login modulo=%s modo=%s intento=%d/%d resultado=autenticado tiempo=%.2fs",
                        self.auth_module,
                        "oculto" if self.headless else "visible",
                        attempt,
                        self.login_attempts,
                        time.monotonic() - attempt_started,
                    )
                    last_retry = None
                    break
                except NafCredentialsRequired as exc:
                    last_retry = exc
                    reason = (
                        "flow_execution_error"
                        if "descartó" in str(exc)
                        else "cas_form_returned"
                    )
                    logging.getLogger(__name__).warning(
                        "NAF login modulo=%s modo=%s intento=%d/%d resultado=reintento causa=%s tiempo=%.2fs",
                        self.auth_module,
                        "oculto" if self.headless else "visible",
                        attempt,
                        self.login_attempts,
                        reason,
                        time.monotonic() - attempt_started,
                    )
                    if attempt >= self.login_attempts:
                        raise NafCredentialsRequired(
                            f"CAS solicitó credenciales después de {self.login_attempts} intentos."
                        ) from exc
            if last_retry is not None:
                raise last_retry
        if not landmark:
            landmark = self._wait_for_shell(self.login_timeout)
        self._auth_transition("Sesión autenticada; abriendo menú NAF")
        try:
            self._navigate_shell_to_orders(str(landmark))
        except TimeoutError as exc:
            raise TimeoutError(f"Sesión NAF autenticada, pero no se pudo abrir el menú: {exc}") from exc
        self._auth_transition("Menú NAF operativo")

    def _navigate_shell_to_orders(self, landmark: str = "") -> None:
        if landmark == "orders" or self._find_now(self.ORDER_INPUT):
            return
        self._ensure_navigation_open()
        if not (self._find_now(self.QUERIES) or self._find_now(self.ORDER_QUERY_MENU)):
            state = self._wait_for_any(
                ((self.QUERIES, "queries"), (self.ORDER_QUERY_MENU, "orders-menu"),
                 (self.ORDER_INPUT, "orders"), (self.COMPANY_INPUT, "company"),
                 (self.COMPANY_SELECTION, "company-menu")),
                "Consultas o la seleccion de compania solicitada por NAF",
                timeout=self.login_timeout,
            )
            if state in ("company", "company-menu"):
                if state == "company-menu":
                    self._open_menu_item(
                        self.COMPANY_SELECTION,
                        "Selección de Compañía",
                        ((self.COMPANY_INPUT, "company"),),
                    )
                self._select_company()
        if not self._find_now(self.ORDER_QUERY_MENU):
            self._open_menu_item(
                self.QUERIES,
                "la lista de Consultas",
                ((self.ORDER_QUERY_MENU, "orders-menu"), (self.ORDER_INPUT, "orders")),
            )
        if not self._find_now(self.ORDER_INPUT):
            state = self._open_menu_item(
                self.ORDER_QUERY_MENU,
                "Consulta de Órdenes de Compra",
                ((self.ORDER_INPUT, "orders"), (self.COMPANY_INPUT, "company")),
            )
            if state == "company":
                self._select_company()
                if not self._find_now(self.ORDER_INPUT):
                    if not self._find_now(self.ORDER_QUERY_MENU):
                        self._open_menu_item(self.QUERIES, "Consultas después de seleccionar compañía",
                                             ((self.ORDER_QUERY_MENU, "orders-menu"),))
                    self._open_menu_item(self.ORDER_QUERY_MENU, "Consulta de Órdenes de Compra",
                                         ((self.ORDER_INPUT, "orders"),))
        self._find(
            self.ORDER_INPUT,
            "el formulario de consulta de órdenes",
            timeout=self.element_timeout,
            enabled=True,
        )

    def _select_company(self) -> None:
        company = self._write(self.COMPANY_INPUT, "TELCONET", "la compañía", verify=False)
        options = self._wait(
            lambda _driver: self._elements_now(self.TELCONET_OPTION),
            "la opción TELCONET S.A.",
            self.element_timeout,
        )
        exact = next(
            (
                option
                for option in options
                if _normalized(getattr(option, "text", "")).rstrip('.') == "telconet s.a"
            ),
            None,
        )
        if exact is None:
            raise LookupError("No se encontró la compañía exacta TELCONET S.A.")
        self._click_element(exact)
        self._click(self.CHOOSE_COMPANY, "el botón Elegir")
        def changed():
            try:
                company.is_enabled()
            except StaleElementReferenceException:
                return True
            return not self._find_now(self.COMPANY_INPUT)

        state = self._wait(
            lambda _driver: "confirm" if self._find_now(self.CONFIRM_COMPANY, enabled=True)
            else "orders" if self._find_now(self.ORDER_INPUT)
            else "reloaded" if changed() else False,
            "la confirmación de compañía",
            self.element_timeout,
        )
        if state == "confirm":
            # SweetAlert is an interactive dialog, not an idle-page prerequisite.
            button = self._find(self.CONFIRM_COMPANY, "OK de compañía", enabled=True)
            try:
                self._click_element(button)
            except TimeoutException:
                pass  # inspect the reload; do not acknowledge twice
            self._wait(
                lambda _driver: not self._find_now(self.CONFIRM_COMPANY)
                and (self._find_now(self.ORDER_INPUT) or changed()),
                "la recarga posterior a confirmar la compañía",
                self.element_timeout,
            )

    def recover_orders_page(self, credentials: SessionCredentials) -> None:
        try:
            self._navigate(PORTAL_APP_URL)
            landmark = self._wait_for_shell(self.login_timeout)
            self._navigate_shell_to_orders(landmark)
        except (PermissionError, TimeoutError, RuntimeError):
            self._login_and_open_orders(credentials)

    def _install_query_observer(self) -> None:
        try:
            self.driver.execute_script(
                """
                const previous = window.__comprasTNOrderQuery;
                if (previous && previous.observer) previous.observer.disconnect();
                const state = {activity: false, notifications: [], observer: null};
                const root = document.querySelector(
                  'table, mat-table, .mat-table, [role="rowgroup"], .dataTables_wrapper'
                );
                state.observer = new MutationObserver(records => {
                  if (records.length) state.activity = true;
                  for (const record of records) {
                    for (const node of record.addedNodes) {
                      const text = (node.innerText || node.textContent || '').trim();
                      const selector = '[role="alert"], .toast-container, .toast-message, '
                        + '.swal2-html-container';
                      if (text && (node.matches?.(selector) || node.querySelector?.(selector))) {
                        state.notifications.push(text);
                      }
                    }
                  }
                });
                if (root) {
                  state.observer.observe(root, {
                    childList: true, subtree: true, characterData: true, attributes: true
                  });
                }
                if (window.jQuery) {
                  window.jQuery(document).off('ajaxComplete.comprasTNOrders');
                  window.jQuery(document).one('ajaxComplete.comprasTNOrders', () => {
                    state.activity = true;
                  });
                }
                window.__comprasTNOrderQuery = state;
                """
            )
        except WebDriverException:
            pass

    def _observer_activity(self) -> bool:
        try:
            return bool(
                self.driver.execute_script(
                    "return !!(window.__comprasTNOrderQuery && "
                    "window.__comprasTNOrderQuery.activity);"
                )
            )
        except WebDriverException:
            return False

    def _notifications(self) -> list[str]:
        texts: list[str] = []
        try:
            observed = self.driver.execute_script(
                "return (window.__comprasTNOrderQuery && "
                "window.__comprasTNOrderQuery.notifications) || [];"
            )
            texts.extend(str(item) for item in observed or [] if str(item).strip())
        except WebDriverException:
            pass
        for element in self._elements_now(self.ALERTS):
            try:
                text = " ".join((element.text or "").split())
            except (StaleElementReferenceException, WebDriverException):
                continue
            if text:
                identity = str(getattr(element, "id", "") or "")
                texts.append(f"{identity}\u001f{text}")
        return list(dict.fromkeys(texts))

    def _result_snapshot(self) -> tuple[tuple[str, ...], int]:
        rows = self._elements_now(self.RESULT_ROWS)
        texts: list[str] = []
        for row in rows:
            try:
                text = _normalized(row.text)
            except (StaleElementReferenceException, WebDriverException):
                continue
            if text:
                texts.append(text)
        return tuple(texts), len(self._elements_now(self.DOWNLOAD_BUTTONS))

    def _empty_result_text(self) -> str:
        for element in self._elements_now(self.EMPTY_RESULTS):
            try:
                text = " ".join((element.text or "").split())
            except (StaleElementReferenceException, WebDriverException):
                continue
            normalized = _normalized(text)
            if any(
                marker in normalized
                for marker in (
                    "no se encontraron",
                    "no se han encontrado datos",
                    "sin resultados",
                    "no existen registros",
                    "ningun registro",
                )
            ):
                return text
        return ""

    @staticmethod
    def _same_number(expected: str, text: str) -> bool:
        expected_digits = re.sub(r"\D", "", expected).lstrip("0") or "0"
        candidates = re.findall(r"\d+", text)
        return any((candidate.lstrip("0") or "0") == expected_digits for candidate in candidates)

    def _matching_download_button(self, number: str) -> Any:
        for row in self._elements_now(self.RESULT_ROWS):
            try:
                cells = row.find_elements(By.CSS_SELECTOR, "td")
                if len(cells) < 2 or cells[1].text.strip() != number:
                    continue
                buttons: list[Any] = []
                for locator in self.DOWNLOAD_BUTTONS:
                    by, value = locator
                    if by == By.XPATH and value.startswith("//"):
                        value = f".{value}"
                    buttons.extend(row.find_elements(by, value))
                button = next(
                    (item for item in buttons if self._visible(item) and self._enabled(item)),
                    None,
                )
                if button:
                    return button
            except (StaleElementReferenceException, WebDriverException):
                continue
        return False

    def _wait_for_query_result(
        self,
        before: tuple[tuple[str, ...], int],
        *,
        expected_number: str | None,
        allow_empty: bool,
    ) -> Any:
        activity = False
        idle_since: float | None = None

        def result(_driver: webdriver.Chrome) -> Any:
            nonlocal activity, idle_since
            snapshot = self._result_snapshot()
            # Leer primero el observer: _busy() puede recorrer otra ventana
            # cuando busca overlays y cambiar temporalmente el contexto.
            observed = self._observer_activity()
            busy = self._busy()
            activity = activity or busy or observed or snapshot != before
            if busy:
                idle_since = None
                return False
            if not activity:
                return False
            now = time.monotonic()
            idle_since = idle_since or now
            if now - idle_since < 0.45:
                return False
            empty = self._empty_result_text()
            if empty:
                if allow_empty:
                    # WebDriverWait ignora colecciones vacías por ser falsy.
                    return "empty"
                raise LookupError(
                    f"La consulta de la OC {expected_number} no devolvió resultados: {empty}"
                )
            if expected_number:
                return self._matching_download_button(expected_number) or False
            buttons = self._elements_now(self.DOWNLOAD_BUTTONS, enabled=True)
            return buttons or False

        return self._wait(
            result,
            "la respuesta actualizada de la consulta de órdenes",
            self.query_timeout,
        )

    def download_order(
        self,
        number: str,
        credentials: SessionCredentials | None = None,
        *,
        attempts: int = 3,
        retry_notice: Callable[[int, str], None] | None = None,
    ) -> Path:
        number = str(number or "").strip()
        if not number:
            raise ValueError("Debe indicar el número de la OC.")
        last_error: Exception | None = None
        attempts = max(1, attempts)
        for attempt in range(1, attempts + 1):
            try:
                return self._download_order_once(number)
            except PermissionError:
                raise
            except (LookupError, TimeoutError, RuntimeError, WebDriverException) as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                if retry_notice:
                    retry_notice(attempt + 1, str(exc))
                if credentials is not None:
                    self.recover_orders_page(credentials)
        raise RuntimeError(
            f"No se pudo descargar la OC {number} después de {attempts} intentos: "
            f"{last_error}"
        ) from last_error

    def _download_order_once(self, number: str) -> Path:
        self._write(self.ORDER_INPUT, number, "el número de la OC")
        before_result = self._result_snapshot()
        self._install_query_observer()
        self._click(self.APPLY_FILTERS, "Aplicar filtros")
        button = self._wait_for_query_result(
            before_result, expected_number=number, allow_empty=False
        )
        before_files = self._snapshot()
        self._install_query_observer()
        self._click_element(button)
        return self.wait_for_download(before_files)

    def _date_fields(self) -> list[Any]:
        fields = self._elements_now(((By.CSS_SELECTOR, "input"),), enabled=True)
        matching: list[Any] = []
        for field in fields:
            try:
                hint = " ".join(
                    str(field.get_attribute(name) or "")
                    for name in ("placeholder", "data-placeholder", "aria-label", "id")
                )
            except (StaleElementReferenceException, WebDriverException):
                continue
            normalized = _normalized(hint)
            if "fecha" in normalized or any(
                item in normalized for item in ("mat-input-2", "mat-input-3")
            ):
                matching.append(field)
        return matching

    def _autocomplete_by_label(self, label: str, fallback_index: int) -> Any:
        script = """
            const needle = arguments[0].normalize('NFD')
              .replace(/[\u0300-\u036f]/g, '').toLowerCase();
            const visible = el => !!(el.offsetWidth || el.offsetHeight ||
              el.getClientRects().length) && !el.disabled;
            for (const input of document.querySelectorAll(
                'input[aria-autocomplete="list"], input[role="combobox"]')) {
              if (!visible(input)) continue;
              const container = input.closest(
                'ng-select, mat-form-field, .mat-form-field, .mat-mdc-form-field, .form-group');
              const linked = input.id ? document.querySelector(
                'label[for="' + CSS.escape(input.id) + '"]') : null;
              let text = [input.getAttribute('placeholder'),
                input.getAttribute('aria-label'), linked?.innerText,
                container?.innerText, container?.parentElement?.querySelector(
                  ':scope > label, :scope > .ng-placeholder')?.innerText
              ].filter(Boolean).join(' ');
              text = text.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
                .toLowerCase();
              if (text.includes(needle)) return input;
            }
            return null;
        """
        try:
            field = self.driver.execute_script(script, label)
            if field and self._visible(field) and self._enabled(field):
                return field
        except WebDriverException:
            pass
        fields = self._elements_now(self.COMPANY_INPUT, enabled=True)
        return fields[fallback_index] if -len(fields) <= fallback_index < len(fields) else False

    def _set_autocomplete(self, label: str, value: str, fallback_index: int) -> None:
        value = str(value or "").strip()
        field = self._wait(
            lambda _driver: self._autocomplete_by_label(label, fallback_index),
            f"el filtro {label}",
            self.element_timeout,
        )
        if not value:
            clear = self.driver.execute_script(
                "return arguments[0].closest('ng-select')?.querySelector('.ng-clear-wrapper') || null;",
                field,
            )
            if clear:
                self._click_element(clear)
            elif field.get_attribute("value"):
                self._click_element(field)
                field.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                field.send_keys(Keys.ESCAPE, Keys.TAB)

            def cleared(_driver: Any) -> bool:
                current = self._autocomplete_by_label(label, fallback_index)
                if not current:
                    return False
                selected = self.driver.execute_script(
                    "return arguments[0].closest('ng-select')?.querySelector('.ng-value-label')?.innerText || '';",
                    current,
                )
                return not selected and not (current.get_attribute("value") or "").strip()

            self._wait(cleared, f"dejar vacío el filtro {label}", self.element_timeout)
            return
        code_match = re.match(r"^\s*(\d+)\s*(?:-|$)", value)
        employee_code = code_match.group(1) if code_match else ""
        search_value = employee_code or value
        self._click_element(field)
        field.send_keys(Keys.CONTROL, "a", Keys.DELETE)
        field.send_keys(search_value)
        normalized_value = _normalized(value)

        def matching_option(_driver: Any) -> Any:
            options = self._elements_now((
                (By.CSS_SELECTOR, "mat-option"),
                (By.CSS_SELECTOR, ".mat-option, .mat-mdc-option, .ng-option, [role='option']"),
            ))
            try:
                exact = [option for option in options
                         if _normalized(option.text) == normalized_value]
                if len(exact) == 1:
                    return exact[0]
                if employee_code:
                    matching = [option for option in options if re.match(
                        rf"^\s*{re.escape(employee_code)}\s*-", option.text)]
                else:
                    matching = [option for option in options
                                if normalized_value in _normalized(option.text)]
                return matching[0] if len(matching) == 1 else False
            except (StaleElementReferenceException, WebDriverException):
                return False

        selected = self._wait(
            matching_option, f"la opción de {label} correspondiente a {value}", self.element_timeout
        )
        self._click_element(selected)

        def selection_applied(_driver: webdriver.Chrome) -> Any:
            current = self._autocomplete_by_label(label, fallback_index)
            if not current:
                return False
            try:
                current_value = _normalized(current.get_attribute("value") or "")
                selected_label = self.driver.execute_script(
                    "const c=arguments[0].closest('ng-select'); "
                    "return c?.querySelector('.ng-value-label')?.innerText || '';", current)
                current_value = _normalized(selected_label or current_value)
            except (StaleElementReferenceException, WebDriverException):
                return False
            matches = bool(re.match(rf"^{re.escape(employee_code)}\s*-", current_value)) if employee_code else normalized_value in current_value
            return current if matches else False

        self._wait(
            selection_applied,
            f"que el filtro {label} conserve la opción elegida",
            self.element_timeout,
        )

    def configure_supply_filters(
        self, start: str, end: str, requester: str, authorizer: str
    ) -> None:
        self._write(self.ORDER_INPUT, "", "el número de la OC (vacío en abastecimiento)")

        def date_fields(_driver: webdriver.Chrome) -> list[Any] | bool:
            fields = self._date_fields()
            return fields if len(fields) >= 2 else False

        fields = self._wait(
            date_fields,
            "los campos de fecha de abastecimiento",
            self.element_timeout,
        )
        for field, value in zip(fields[:2], (start, end), strict=True):
            wanted = datetime.strptime(value, "%d/%m/%Y").date()

            def date_accepted(_driver: Any, field: Any = field, wanted: Any = wanted) -> bool:
                try:
                    actual = field.get_attribute("value") or ""
                    return (field.get_attribute("aria-invalid") != "true"
                            and datetime.strptime(actual, "%d/%m/%Y").date() == wanted)
                except (ValueError, StaleElementReferenceException):
                    return False

            # NAF versions use different date adapters. Verify the displayed day
            # after blur before accepting either keyboard input format.
            for date_format in ("%d/%m/%Y", "%m/%d/%Y"):
                self._click_element(field)
                field.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                field.send_keys(wanted.strftime(date_format), Keys.TAB)
                if date_accepted(self.driver):
                    break
            self._wait(date_accepted, f"validar la fecha de abastecimiento {value}", self.element_timeout)
        self._set_autocomplete("solicitante", requester, -2)
        self._set_autocomplete("autoriza", authorizer, -1)
        before_result = self._result_snapshot()
        self._install_query_observer()
        self._click(self.APPLY_FILTERS, "Aplicar filtros")
        self._wait_for_query_result(
            before_result, expected_number=None, allow_empty=True
        )

    @staticmethod
    def _button_key(button: Any, index: int) -> str:
        try:
            row = button.find_element(By.XPATH, "./ancestor::*[self::tr or @role='row'][1]")
            text = " ".join((row.text or "").split())
        except (NoSuchElementException, StaleElementReferenceException, WebDriverException):
            text = ""
        match = re.search(r"\d{5,14}", text)
        return match.group(0) if match else f"resultado-{index + 1}"

    def download_all_visible_results(
        self,
        *,
        attempts: int = 2,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[SupplyDownload]:
        buttons = self._elements_now(self.DOWNLOAD_BUTTONS, enabled=True)
        total = len(buttons)
        check_cycle = getattr(progress, 'check_cycle', None)
        if callable(check_cycle):
            numbers = [self._button_key(button, index) for index, button in enumerate(buttons)]
            check_cycle([{'order_number': number} for number in numbers if re.fullmatch(r'\d{4,14}', number)])
        results: list[SupplyDownload] = []
        for index in range(total):
            if cancelled and cancelled():
                results.extend(
                    SupplyDownload(
                        key=f"resultado-{pending_index + 1}",
                        error=DownloadCancelledError("No procesado por cancelación."),
                    )
                    for pending_index in range(index, total)
                )
                break
            error: Exception | None = None
            path: Path | None = None
            key = f"resultado-{index + 1}"
            for attempt in range(1, max(1, attempts) + 1):
                buttons = self._elements_now(self.DOWNLOAD_BUTTONS, enabled=True)
                if index >= len(buttons):
                    error = RuntimeError(
                        "La tabla cambió mientras se procesaban sus resultados."
                    )
                    break
                button = buttons[index]
                key = self._button_key(button, index)
                before = self._snapshot()
                previous_notifications = tuple(self._notifications())
                self._install_query_observer()
                try:
                    self._click_element(button)
                    path = self.wait_for_download(
                        before, expected_number=key if re.fullmatch(r"\d{4,14}", key) else None,
                        previous_notifications=previous_notifications,
                    )
                    error = None
                    break
                except OrderNotApprovedError as exc:
                    error = exc
                    break
                except (OSError, TimeoutError, RuntimeError, WebDriverException) as exc:
                    error = exc
                    if attempt < attempts:
                        continue
            results.append(SupplyDownload(key=key, path=path, error=error))
            if progress:
                status = "Descargado" if path else "Falló"
                progress(index + 1, total, f"{status} archivo {index + 1} de {total}")
        return results

    def download_all_visible(
        self,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[Path]:
        """Mantiene compatibilidad con consumidores previos del Page Object."""
        return [
            result.path
            for result in self.download_all_visible_results(
                progress=progress, cancelled=cancelled
            )
            if result.path is not None
        ]

    def _snapshot(self) -> dict[Path, tuple[float, int]]:
        snapshot: dict[Path, tuple[float, int]] = {}
        for pattern in ("*.pdf", "*.crdownload", "*.tmp", "*.download"):
            for path in self.download_folder.glob(pattern):
                if not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                snapshot[path] = (stat.st_mtime, stat.st_size)
        return snapshot

    def wait_for_download(self, before: dict[Path, tuple[float, int]], *,
                          expected_number: str | None = None,
                          previous_notifications: tuple[str, ...] = ()) -> Path:
        stable: dict[Path, tuple[int, float]] = {}
        identified: dict[Path, tuple[float, int, str]] = {}

        previous_texts = {_normalized(text.rsplit("\x1f", 1)[-1]) for text in previous_notifications}

        def completed(_driver: webdriver.Chrome) -> Any:
            active = [text.rsplit("\x1f", 1)[-1] for text in self._notifications()
                      if _normalized(text.rsplit("\x1f", 1)[-1]) not in previous_texts]
            for notification in active:
                normalized = _normalized(notification)
                if not any(marker in normalized for marker in (
                    "no esta permitida", "no se encuentra aprobada",
                    "no esta aprobada", "sin permisos",
                )):
                    continue
                mentioned = re.findall(r"(?:orden|oc|o/c)\s*#?\s*(\d{4,14})", normalized)
                if expected_number and mentioned and expected_number not in mentioned:
                    continue
                raise OrderNotApprovedError(notification)
            changed_partials = False
            for pattern in ("*.crdownload", "*.tmp", "*.download"):
                for partial in self.download_folder.glob(pattern):
                    try:
                        stat = partial.stat()
                    except FileNotFoundError:
                        continue
                    previous = before.get(partial)
                    if previous is None or (stat.st_mtime, stat.st_size) != previous:
                        changed_partials = True
            candidates: list[Path] = []
            now = time.monotonic()
            for path in self.download_folder.glob("*.pdf"):
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                previous = before.get(path)
                if previous is not None and (stat.st_mtime, stat.st_size) == previous:
                    continue
                last_size, since = stable.get(path, (-1, now))
                if last_size != stat.st_size:
                    stable[path] = (stat.st_size, now)
                    continue
                if stat.st_size > 0 and now - since >= 0.7 and (expected_number or not changed_partials):
                    if expected_number:
                        cached = identified.get(path)
                        if cached is None or cached[:2] != (stat.st_mtime, stat.st_size):
                            try:
                                number = str(OrderFileService.extract(path).get("order_number") or "")
                            except ValueError:
                                continue
                            identified[path] = (stat.st_mtime, stat.st_size, number)
                        if identified[path][2] != expected_number:
                            continue
                    candidates.append(path)
            return (
                max(candidates, key=lambda item: item.stat().st_mtime)
                if candidates
                else False
            )

        try:
            return self._wait(
                completed,
                "que finalice la descarga del PDF",
                self.download_timeout,
            )
        except PermissionError:
            raise
        except TimeoutError as exc:
            notifications = " | ".join(
                text for text in self._notifications() if text not in previous_notifications
            )
            detail = f" Mensaje del portal: {notifications}" if notifications else ""
            raise TimeoutError(f"No se completó la descarga del PDF.{detail}") from exc

    def _network_diagnostic(self) -> str:
        # Never persist request headers, cookies, bodies or SSO query tokens.
        lines = []
        documents = set()
        pending = {}
        try:
            entries = self.driver.get_log("performance")
        except (AttributeError, WebDriverException):
            return "Red: registro no disponible."
        for entry in entries:
            try:
                message = json.loads(entry["message"])["message"]
                params = message["params"]
                method = message["method"]
                if method == "Network.requestWillBeSent":
                    parsed_resource = urlsplit(params["request"]["url"])
                    if parsed_resource.scheme in ("http", "https"):
                        pending[params["requestId"]] = (
                            f"{params.get('type', '')}: {parsed_resource.scheme}://"
                            f"{parsed_resource.hostname}{parsed_resource.path}"
                        )
                elif method == "Network.loadingFinished":
                    pending.pop(params["requestId"], None)
                elif method == "Network.loadingFailed":
                    resource = pending.pop(params["requestId"], "")
                    lines.append(f"Recurso fallido: {resource}; {params.get('errorText', '')}; motivo={params.get('blockedReason', '')}")
                if method == "Network.requestWillBeSent" and params.get("type") == "Document":
                    documents.add(params["requestId"])
                    parsed = urlsplit(params["request"]["url"])
                    lines.append(f"Documento: {parsed.scheme}://{parsed.hostname}{parsed.path}")
                elif method == "Network.responseReceived" and params.get("type") == "Document":
                    response = params["response"]
                    lines.append(f"Respuesta documento: HTTP {response['status']} ({response.get('mimeType', '')})")
                elif method == "Network.loadingFailed" and params.get("requestId") in documents:
                    lines.append(f"Fallo documento: {params.get('errorText', '')}; cancelado={params.get('canceled', False)}")
            except (KeyError, TypeError, ValueError):
                continue
        lines.extend(f"Pendiente: {resource}" for resource in pending.values())
        return "Red (documentos y recursos, sin credenciales):\n" + "\n".join(lines[-30:])

    def capture_diagnostic(self, stage: str, error: Exception) -> str:
        if self.diagnostics_folder is None:
            return ""
        try:
            self.diagnostics_folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage)[:60]
            base = self.diagnostics_folder / f"descargas-{stamp}-{safe_stage}"
            screenshot: Path | None = base.with_suffix(".png")
            metadata = base.with_suffix(".txt")
            try:
                self.driver.save_screenshot(str(screenshot))
            except WebDriverException:
                screenshot = None
            try:
                raw_url = str(self.driver.current_url or "")
                parsed = urlsplit(raw_url)
                url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
            except (ValueError, WebDriverException):
                url = "no disponible"
            try:
                title = self.driver.title
            except WebDriverException:
                title = "no disponible"
            try:
                body = str(
                    self.driver.execute_script(
                        "return (document.body && document.body.innerText) || '';"
                    )
                    or ""
                )
            except WebDriverException:
                body = ""
            content = sanitize_text(
                (
                    f"{self._network_diagnostic()}\n"
                    f"Etapa: {stage}\n"
                    f"Error: {type(error).__name__}: {error}\n"
                    f"URL: {url}\n"
                    f"Título: {title}\n"
                    f"Texto visible (máximo 4000 caracteres):\n{body[:4000]}\n"
                ),
                self._diagnostic_secrets,
            )
            metadata.write_text(content, encoding="utf-8")
            if screenshot is not None and screenshot.exists():
                return f"{metadata}; {screenshot}"
            return str(metadata)
        except OSError:
            return ""


class SeleniumOrderDownloadGateway:
    def __init__(
        self,
        settings: SettingsRepository,
        order_files: OrderFileService,
        seafile: SeafileGateway | None = None,
        app_paths: AppPaths | None = None,
    ):
        self.settings = settings
        self.order_files = order_files
        self.seafile = seafile
        self.app_paths = app_paths or AppPaths.default()

    def _setting_int(
        self, key: str, default: int, minimum: int, maximum: int
    ) -> int:
        return _safe_int(
            self.settings.get("downloads", key, default), default, minimum, maximum
        )

    def _create_driver(self, folder: Path, headless: bool) -> webdriver.Chrome:
        return create_corporate_browser(
            folder, headless, self._setting_int("page_load_timeout", 25, 20, 240),
            network_diagnostics=True,
            naf_navigation=True,
            naf_cache_dir=self.app_paths.root / "browser-cache" / "naf",
        )

    def _headless_for(self, request: OperationRequest) -> bool:
        default_key = (
            "abastecimiento_headless"
            if request.kind == "descarga_abastecimiento"
            else "headless"
        )
        return _as_bool(
            request.options.get(
                "headless",
                self.settings.get("downloads", default_key, True),
            )
        )

    def _resolve_supplier(
        self,
        order_number: str,
        *,
        fallback: str = "",
        path: Path | None = None,
        info: dict[str, Any] | None = None,
    ) -> str:
        try:
            return self.order_files.resolve_supplier(
                order_number,
                preferred_path=path,
                preferred_info=info,
                fallback=fallback,
            )
        except Exception:
            return str((info or {}).get("supplier") or fallback or "").strip()

    @staticmethod
    def _supplier_warning(raw: dict[str, Any], supplier: str) -> str:
        candidates = raw.get("supplier_candidates") or []
        if not isinstance(candidates, (list, tuple, set)):
            candidates = [candidates]
        distinct: list[str] = []
        for value in candidates:
            clean = str(value or "").strip()
            if clean and clean.casefold() not in {item.casefold() for item in distinct}:
                distinct.append(clean)
        if len(distinct) > 1:
            selected = supplier or "sin identificar"
            return (
                " · Advertencia: la OC llegó con proveedores diferentes "
                f"({'; '.join(distinct)}); se usó {selected}."
            )
        if not supplier:
            return " · Advertencia: no se pudo identificar el proveedor de la OC."
        return ""

    def _failure_items(self, request: OperationRequest, message: str) -> list[OperationItem]:
        if request.items:
            return [
                OperationItem(
                    key=str(item.get("order_number") or item.get("numero") or "OC"),
                    status=ItemStatus.FAILED,
                    message=message,
                    payload={
                        "supplier": self._resolve_supplier(
                            str(item.get("order_number") or item.get("numero") or ""),
                            fallback=str(item.get("supplier") or item.get("proveedor") or ""),
                        ),
                        "task_numbers": self._unique_tasks(
                            item.get("task_numbers"),
                            item.get("task_number"),
                            item.get("tarea"),
                        ),
                    },
                )
                for item in request.items
            ]
        return [
            OperationItem(
                key="descarga_abastecimiento",
                status=ItemStatus.FAILED,
                message=message,
            )
        ]

    @staticmethod
    def _cancelled_items(request: OperationRequest) -> list[OperationItem]:
        return [
            OperationItem(
                key=str(item.get("order_number") or item.get("numero") or "OC"),
                status=ItemStatus.SKIPPED,
                message="No procesado por cancelación.",
            )
            for item in request.items
        ]

    def download(self, credentials, request, *, progress=None, cancelled=None):
        from contextlib import nullcontext
        batch = getattr(self.seafile, 'batch', None)
        with batch() if batch else nullcontext():
            return self._download_batch(credentials, request, progress=progress, cancelled=cancelled)

    def _download_batch(
        self,
        credentials: SessionCredentials,
        request: OperationRequest,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> OperationResult:
        folder = Path(
            str(
                request.options.get("download_folder")
                or (self.settings.get("downloads", "abastecimiento_carpeta_descarga", "")
                    if request.kind == "descarga_abastecimiento" else "")
                or self.settings.get("downloads", "carpeta_destino_local", "")
                or (Path.home() / "Documents" / "ComprasTN")
            )
        )
        if request.kind == "descarga_abastecimiento" and folder.name.upper() != "ABASTECIMIENTO":
            folder = folder / "ABASTECIMIENTO"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return OperationResult.from_items(
                self._failure_items(request, f"No se pudo preparar la carpeta de descarga: {exc}"),
                "No se pudo iniciar la descarga.",
            )
        headless = self._headless_for(request)
        driver: webdriver.Chrome | None = None
        items: list[OperationItem] = []
        try:
            if cancelled and cancelled():
                return OperationResult(
                    status=JobStatus.CANCELLED,
                    items=self._cancelled_items(request),
                    finished_at=utc_now(),
                    message="Descarga cancelada antes de iniciar.",
                )
            try:
                if progress:
                    progress(0, len(request.items), "Abriendo navegador para descargar OC")
                driver = self._create_driver(folder, headless)
            except Exception as exc:
                return OperationResult.from_items(
                    self._failure_items(
                        request, f"No fue posible iniciar Chrome: {type(exc).__name__}: {exc}"
                    ),
                    "No se pudo iniciar la descarga.",
                )
            try:
                driver.execute_cdp_cmd(
                    "Page.setDownloadBehavior",
                    {"behavior": "allow", "downloadPath": str(folder.resolve())},
                )
            except WebDriverException:
                pass
            page = OrderPortalPage(
                driver,
                folder,
                diagnostics_folder=self.app_paths.diagnostics / "descargas_oc",
                element_timeout=self._setting_int("element_timeout", 45, 10, 180),
                login_timeout=self._setting_int("login_timeout", 100, 20, 300),
                query_timeout=self._setting_int("query_timeout", 75, 15, 240),
                download_timeout=self._setting_int(
                    "download_timeout", 120, 30, 600
                ),
                login_attempts=self._setting_int("login_retries", 3, 1, 3),
                auth_module=(
                    "descargas_abastecimiento"
                    if request.kind == "descarga_abastecimiento"
                    else "descargas_oc"
                ),
                headless=headless,
            )
            page.cancelled = cancelled
            page.auth_progress = lambda message: progress(0, len(request.items), message) if progress else None
            try:
                page.login_and_open_orders(credentials)
            except Exception as login_error:
                return OperationResult.from_items(
                    self._failure_items(request, str(login_error)),
                    "No se pudo ingresar al portal de órdenes.",
                )

            item_attempts = self._setting_int("item_retries", 3, 1, 5)
            if request.kind == "descarga_abastecimiento":
                supply_result = self._download_supply(
                    page,
                    credentials,
                    request,
                    item_attempts,
                    progress,
                    cancelled,
                )
                if isinstance(supply_result, OperationResult):
                    return supply_result
                items.extend(supply_result)
                if cancelled and cancelled():
                    return OperationResult(
                        status=JobStatus.CANCELLED,
                        items=items,
                        finished_at=utc_now(),
                        message="Descarga cancelada.",
                    )
            else:
                items.extend(
                    self._download_normal(
                        page,
                        credentials,
                        request,
                        item_attempts,
                        progress,
                        cancelled,
                    )
                )
                if cancelled and cancelled():
                    return OperationResult(
                        status=JobStatus.CANCELLED,
                        items=items,
                        finished_at=utc_now(),
                        message="Descarga cancelada.",
                    )
            if request.kind == "descarga_abastecimiento" and not items:
                return OperationResult(
                    status=JobStatus.SUCCEEDED,
                    items=[],
                    finished_at=utc_now(),
                    message="La consulta no devolvió órdenes para descargar.",
                )
            return OperationResult.from_items(items, "Descarga finalizada.")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException:
                    pass

    def _download_supply(
        self,
        page: OrderPortalPage,
        credentials: SessionCredentials,
        request: OperationRequest,
        item_attempts: int,
        progress: Callable[[int, int, str], None] | None,
        cancelled: Callable[[], bool] | None,
    ) -> list[OperationItem] | OperationResult:
        try:
            page.configure_supply_filters(
                str(request.options.get("start_date") or ""),
                str(request.options.get("end_date") or ""),
                str(request.options.get("requester") or ""),
                str(request.options.get("authorizer") or ""),
            )
            downloads = page.download_all_visible_results(
                attempts=min(item_attempts, 3),
                progress=progress,
                cancelled=cancelled,
            )
        except Exception as exc:
            from compras_tn.application.task_cycle import CycleDeclined
            if isinstance(exc, CycleDeclined):
                raise
            diagnostic = page.capture_diagnostic("abastecimiento_filtros", exc)
            message = str(exc)
            if diagnostic:
                message += f" Diagnóstico: {diagnostic}"
            return OperationResult.from_items(
                self._failure_items(request, message),
                "Falló la consulta de abastecimiento.",
            )
        items: list[OperationItem] = []
        for result in downloads:
            if result.path is None:
                error = result.error or RuntimeError("Descarga no completada.")
                if isinstance(error, DownloadCancelledError):
                    items.append(
                        OperationItem(
                            key=result.key,
                            status=ItemStatus.SKIPPED,
                            message=str(error),
                        )
                    )
                    continue
                diagnostic = page.capture_diagnostic(
                    f"abastecimiento_{result.key}", error
                )
                message = str(error)
                if diagnostic:
                    message += f" Diagnóstico: {diagnostic}"
                status = (
                    ItemStatus.SKIPPED
                    if isinstance(error, OrderNotApprovedError)
                    else ItemStatus.FAILED
                )
                items.append(
                    OperationItem(
                        key=result.key,
                        status=status,
                        error_code=(
                            "order_not_approved"
                            if isinstance(error, OrderNotApprovedError)
                            else "missing_local_file"
                        ),
                        message=message,
                    )
                )
                continue
            path = result.path
            final = path
            order_number = (result.key if re.fullmatch(r"\d{4,14}", result.key)
                            else self._number_from_name(path.name))
            try:
                info = OrderFileService.extract(path)
                order_number = str(info.get("order_number") or order_number)
                if re.fullmatch(r"\d{4,14}", result.key) and order_number != result.key:
                    raise ValueError(f"El PDF corresponde a la OC {order_number}, no a {result.key}.")
                supplier = self._resolve_supplier(
                    order_number,
                    path=path,
                    info=info,
                )
                final = self._rename(path, order_number, supplier)
                task_numbers = self._unique_tasks(info.get("task_numbers"), info.get("task_number"))
                delivery, transfer = self._upload_supply(credentials, final, cancelled=cancelled)
                task_destinations = [{"pdf_path": str(final), "task_number": "",
                                      "task_numbers": task_numbers, **transfer}]
                self.order_files.invalidate_inventory()
                items.append(
                    OperationItem(
                        key=order_number or result.key,
                        status=ItemStatus.SUCCEEDED,
                        message=str(final) + delivery,
                        payload={
                            "pdf_path": str(final),
                            "pdf_paths": [item["pdf_path"] for item in task_destinations],
                            "order_number": order_number,
                            "task_number": task_numbers[0] if task_numbers else "",
                            "task_numbers": task_numbers,
                            "task_destinations": task_destinations,
                            "supplier": supplier,
                        },
                    )
                )
            except Exception as exc:
                items.append(
                    OperationItem(
                        key=order_number or result.key,
                        status=ItemStatus.FAILED,
                        message=f"El PDF se descargó, pero no pudo finalizarse: {exc}",
                        payload={"pdf_path": str(final)},
                    )
                )
        return items

    def _download_normal(
        self,
        page: OrderPortalPage,
        credentials: SessionCredentials,
        request: OperationRequest,
        item_attempts: int,
        progress: Callable[[int, int, str], None] | None,
        cancelled: Callable[[], bool] | None,
    ) -> list[OperationItem]:
        total = len(request.items)
        items: list[OperationItem] = []
        for index, raw in enumerate(request.items, start=1):
            if cancelled and cancelled():
                for pending in request.items[index - 1 :]:
                    pending_number = str(
                        pending.get("order_number") or pending.get("numero") or "OC"
                    ).strip()
                    items.append(
                        OperationItem(
                            key=pending_number,
                            status=ItemStatus.SKIPPED,
                            message="No procesado por cancelación.",
                        )
                    )
                break
            number = str(raw.get("order_number") or raw.get("numero") or "").strip()
            local_path: Path | None = None

            def retry_notice(
                attempt: int,
                reason: str,
                *,
                _index: int = index,
                _number: str = number,
            ) -> None:
                if progress:
                    progress(
                        _index - 1,
                        total,
                        f"Reintentando OC {_number} ({attempt}/{item_attempts}): {reason}",
                    )

            try:
                path = page.download_order(
                    number,
                    credentials,
                    attempts=item_attempts,
                    retry_notice=retry_notice,
                )
                local_path = path
                info = OrderFileService.extract(path)
                if info.get('order_number') and info['order_number'] != number:
                    raise ValueError(f"El PDF corresponde a la OC {info['order_number']}, no a {number}.")
                input_supplier = str(raw.get("supplier") or raw.get("proveedor") or "")
                supplier = self._resolve_supplier(
                    number,
                    fallback=input_supplier,
                    path=path,
                    info=info,
                )
                final = self._rename(path, number, supplier)
                local_path = final
                document_tasks = self._unique_tasks(
                    info.get("task_numbers"), info.get("task_number")
                )
                input_tasks = self._unique_tasks(
                    raw.get("task_numbers"), raw.get("task_number"), raw.get("tarea")
                )
                task_numbers = self._unique_tasks(document_tasks, input_tasks)
                mismatch = bool(
                    document_tasks and input_tasks and set(document_tasks) != set(input_tasks)
                )
                final, task_destinations, delivery = self._finalize_task_destinations(
                    credentials,
                    final,
                    request.mode.value,
                    task_numbers,
                    cancelled=cancelled,
                )
                local_path = final
                self.order_files.invalidate_inventory()
                warning = (
                    " · Advertencia: las tareas del correo y del PDF no coinciden; "
                    "se conservaron todas."
                    if mismatch
                    else ""
                )
                warning += self._supplier_warning(raw, supplier)
                items.append(
                    OperationItem(
                        key=number,
                        status=ItemStatus.SUCCEEDED,
                        message=str(final) + delivery + warning,
                        payload={
                            "pdf_path": str(final),
                            "pdf_paths": [item["pdf_path"] for item in task_destinations],
                            "order_number": number,
                            "task_number": task_numbers[0] if task_numbers else "",
                            "task_numbers": task_numbers,
                            "task_destinations": task_destinations,
                            "supplier": supplier,
                            "external_ids": self._unique_tasks(
                                raw.get("external_ids"), raw.get("external_id")
                            ),
                        },
                    )
                )
            except OrderNotApprovedError as exc:
                input_tasks = self._unique_tasks(
                    raw.get("task_numbers"), raw.get("task_number"), raw.get("tarea")
                )
                supplier = self._resolve_supplier(
                    number,
                    fallback=str(raw.get("supplier") or raw.get("proveedor") or ""),
                    path=local_path,
                )
                items.append(
                    OperationItem(
                        key=number,
                        status=ItemStatus.SKIPPED,
                        error_code="order_not_approved",
                        message=str(exc) + self._supplier_warning(raw, supplier),
                        payload={
                            "pdf_path": str(local_path) if local_path else "",
                            "task_number": input_tasks[0] if input_tasks else "",
                            "task_numbers": input_tasks,
                            "supplier": supplier,
                            "external_ids": self._unique_tasks(
                                raw.get("external_ids"), raw.get("external_id")
                            ),
                        },
                    )
                )
            except Exception as exc:
                input_tasks = self._unique_tasks(
                    raw.get("task_numbers"), raw.get("task_number"), raw.get("tarea")
                )
                supplier = self._resolve_supplier(
                    number,
                    fallback=str(raw.get("supplier") or raw.get("proveedor") or ""),
                    path=local_path,
                )
                diagnostic = page.capture_diagnostic(f"oc_{number}", exc)
                message = str(exc) + self._supplier_warning(raw, supplier)
                if diagnostic:
                    message += f" Diagnóstico: {diagnostic}"
                items.append(
                    OperationItem(
                        key=number,
                        status=ItemStatus.FAILED,
                        error_code="missing_local_file",
                        message=message,
                        payload={
                            "pdf_path": str(local_path) if local_path else "",
                            "task_number": input_tasks[0] if input_tasks else "",
                            "task_numbers": input_tasks,
                            "supplier": supplier,
                            "external_ids": self._unique_tasks(
                                raw.get("external_ids"), raw.get("external_id")
                            ),
                        },
                    )
                )
            if progress:
                progress(index, total, f"Procesada OC {number}")
        return items

    @staticmethod
    def _number_from_name(name: str) -> str:
        match = re.search(r"\d{4,14}", name)
        return match.group(0) if match else ""

    @staticmethod
    def _rename(path: Path, number: str, supplier: str) -> Path:
        short_supplier = " ".join(supplier.split()[:2])
        safe_supplier = re.sub(r"[^\w\- ]+", "_", short_supplier).strip()
        base = " - ".join(part for part in (f"ORDEN {number}".strip(), safe_supplier) if part)
        destination = path.with_name(f"{base}.pdf")
        counter = 1
        while destination.exists() and destination.resolve() != path.resolve():
            destination = path.with_name(f"{base} ({counter}).pdf")
            counter += 1
        if destination.resolve() != path.resolve():
            path.replace(destination)
        return destination

    @staticmethod
    def _unique_tasks(*values: Any) -> list[str]:
        result: list[str] = []
        for value in values:
            candidates = value if isinstance(value, (list, tuple, set)) else [value]
            for candidate in candidates:
                clean = str(candidate or "").strip()
                if clean and clean not in result:
                    result.append(clean)
        return result

    @staticmethod
    def _month_from_path(path: Path) -> str:
        for part in reversed(path.parts[:-1]):
            if part.upper() in MONTHS:
                return part.title()
        return ""

    @staticmethod
    def _copy_destination(source: Path, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / source.name
        if destination.resolve() == source.resolve():
            return source
        if destination.exists() and filecmp.cmp(source, destination, shallow=False):
            return destination
        counter = 1
        while destination.exists():
            destination = folder / f"{source.stem} ({counter}){source.suffix}"
            counter += 1
        shutil.copy2(source, destination)
        return destination

    def _current_month_folder(self, root: Path) -> Path:
        if root.name.upper() in MONTHS:
            return root
        month = MONTHS[datetime.now(ZoneInfo("America/Guayaquil")).month - 1]
        existing = next(
            (
                item
                for item in root.iterdir()
                if item.is_dir() and item.name.upper() == month
            ),
            None,
        )
        folder = existing or (root / month.title())
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _organize_for_tasks(
        self,
        path: Path,
        mode: str,
        task_numbers: list[str],
    ) -> list[dict[str, Any]]:
        if mode != "bienes":
            return [
                {
                    "task_number": task,
                    "month": self._month_from_path(path),
                    "pdf_path": str(path),
                    "preparation_status": "succeeded",
                }
                for task in task_numbers
            ]
        root_value = str(
            self.settings.get("downloads", "carpeta_analizar", "")
        ).strip()
        root = Path(root_value) if root_value else None
        if root is None or not root.is_dir():
            return [
                {
                    "task_number": task,
                    "month": self._month_from_path(path),
                    "pdf_path": str(path),
                    "preparation_status": "succeeded",
                    "message": "Carpeta para organizar no configurada.",
                }
                for task in task_numbers
            ]
        if not task_numbers:
            destination = self._copy_destination(path, root / "ordenes sin tarea")
            if destination.resolve() != path.resolve():
                path.unlink(missing_ok=True)
            return [
                {
                    "task_number": "",
                    "month": self._month_from_path(destination),
                    "pdf_path": str(destination),
                    "preparation_status": "succeeded",
                }
            ]

        destinations: list[dict[str, Any]] = []
        for task in task_numbers:
            try:
                matches = [
                    item
                    for item in root.rglob("*")
                    if item.is_dir() and task_folder(item.name, task)
                ]
                if len(matches) > 1:
                    raise ValueError(
                        f"Hay varias carpetas locales para la tarea {task}; revise la organización."
                    )
                folder = matches[0] if matches else self._current_month_folder(root) / task
                destination = self._copy_destination(path, folder)
                destinations.append(
                    {
                        "task_number": task,
                        "month": self._month_from_path(destination),
                        "pdf_path": str(destination),
                        "preparation_status": "succeeded",
                    }
                )
            except Exception as exc:
                destinations.append(
                    {
                        "task_number": task,
                        "month": "",
                        "pdf_path": str(path),
                        "preparation_status": "failed",
                        "message": sanitize_text(str(exc)),
                    }
                )
        successful_paths = {
            Path(item["pdf_path"]).resolve()
            for item in destinations
            if item["preparation_status"] == "succeeded"
        }
        if (
            successful_paths
            and all(item["preparation_status"] == "succeeded" for item in destinations)
            and path.resolve() not in successful_paths
        ):
            path.unlink(missing_ok=True)
        return destinations

    def _finalize_task_destinations(
        self,
        credentials: SessionCredentials,
        path: Path,
        mode: str,
        task_numbers: list[str],
        *,
        cancelled: Callable[[], bool] | None,
    ) -> tuple[Path, list[dict[str, Any]], str]:
        destinations = self._organize_for_tasks(path, mode, task_numbers)
        if not task_numbers:
            prepared_path = Path(str(destinations[0]["pdf_path"])) if destinations else path
            delivery, transfer = self._upload_if_configured(
                credentials, prepared_path, "", mismatch=True, cancelled=cancelled
            )
            if destinations:
                destinations[0].update(transfer)
            return prepared_path, destinations, delivery

        messages: list[str] = []
        for destination in destinations:
            if destination.get("preparation_status") != "succeeded":
                destination["upload_status"] = "not_started"
                messages.append(str(destination.get("message") or "Preparación fallida"))
                continue
            delivery, transfer = self._upload_if_configured(
                credentials,
                Path(str(destination["pdf_path"])),
                str(destination["task_number"]),
                cancelled=cancelled,
            )
            destination.update(transfer)
            messages.append(f"Tarea {destination['task_number']}{delivery}")
        successful = [
            Path(str(item["pdf_path"]))
            for item in destinations
            if item.get("preparation_status") == "succeeded"
        ]
        primary = successful[0] if successful else path
        return primary, destinations, " · ".join(messages)

    def _upload_supply(self, credentials: SessionCredentials, path: Path, *, cancelled=None) -> tuple[str, dict]:
        stages = {"download_status": "succeeded", "preparation_status": "succeeded"}
        repo_id = str(self.settings.get("downloads", "seafile_repo_id", "")).strip()
        if not repo_id or self.seafile is None:
            return " · Telcodrive no configurado", {**stages, "upload_status": "not_configured"}
        queue = getattr(self.seafile, "delivery", None)
        if queue is not None:
            identifier = queue.enqueue_supply(path)
            if cancelled and cancelled():
                return " · Subida pendiente por cancelación", {**stages, "upload_status": "pending", "transfer_id": identifier}
            result = queue.deliver(identifier, credentials)
            for retry in range(2):
                if result["status"] != "pending" or "404" not in str(result.get("message", "")):
                    break
                if cancelled and cancelled():
                    break
                time.sleep(retry + 1)
                result = queue.deliver(identifier, credentials)
            return f" · Telcodrive: {result['status']} ({result['message']})", {
                **stages, "upload_status": result["status"], "transfer_id": identifier,
                "remote_dir": result["remote_dir"],
            }
        root = str(self.settings.get("downloads", "seafile_parent_dir", "/") or "/")
        if not root.startswith("/") or ".." in PurePosixPath(root).parts:
            raise ValueError("La raíz remota debe ser una ruta absoluta sin ..")
        parent = str(PurePosixPath(root) / "ABASTECIMIENTO")
        with self.seafile.connection(credentials, repo_id) as remote:
            remote.ensure_dir(parent)
            status = remote.upload_verified(path, parent)
        return f" · Telcodrive: {status}", {**stages, "upload_status": status, "remote_dir": parent}

    def _upload_if_configured(
        self, credentials: SessionCredentials, path: Path, task: str = "", *, mismatch: bool = False, cancelled=None
    ) -> tuple[str, dict]:
        stages = {'download_status': 'succeeded', 'preparation_status': 'succeeded'}
        repo_id = str(
            self.settings.get("downloads", "seafile_repo_id", "")
        ).strip()
        if not repo_id or self.seafile is None:
            return " · Telcodrive no configurado", {**stages, 'upload_status': 'not_configured'}
        queue = getattr(self.seafile, "delivery", None)
        if queue is not None:
            identifier = queue.enqueue(path, task, mismatch=mismatch)
            if cancelled and cancelled():
                return ' · Subida pendiente por cancelación', {**stages, 'upload_status': 'pending', 'transfer_id': identifier}
            result = queue.deliver(identifier, credentials)
            return f" · Telcodrive: {result['status']} ({result['message']})", {
                **stages, 'upload_status': result['status'], 'transfer_id': identifier, 'remote_dir': result['remote_dir']}
        parent_dir = str(
            self.settings.get("downloads", "seafile_parent_dir", "/") or "/"
        )
        self.seafile.upload(credentials, path, repo_id, parent_dir)
        return " · Subido a Seafile", {**stages, 'upload_status': 'uploaded'}
