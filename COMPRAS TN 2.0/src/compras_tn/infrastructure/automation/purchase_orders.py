from __future__ import annotations

from compras_tn.domain.purchase_order_observations import (
    OBSERVATION_LIMIT, build_observation, normalize_observation, format_decimal, observation_length,
)

import calendar
import re
import time
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from compras_tn.application.ports import SettingsRepository
from compras_tn.domain.models import (
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationResult,
    PurchaseOrderDraft,
    SessionCredentials,
    utc_now,
)
from compras_tn.infrastructure.automation.browser import create_corporate_browser
from compras_tn.infrastructure.automation.downloads import (
    PORTAL_APP_URL,
    DownloadCancelledError,
    OrderPortalPage,
    _normalized,
    _safe_int,
)
from compras_tn.paths import AppPaths

Locator = tuple[str, str]
GOODS_PURCHASE_ORDER_URL = (
    "https://sites.telconet.ec/naf/compras/movimientos/orden-compra/bienes"
)


class PurchaseOrderValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def pending_approvers(rows: list[list[str]]) -> list[str]:
    names = []
    for cells in rows:
        if len(cells) < 4:
            continue
        state = _normalized(cells[3])
        if state not in {"por aprobar", "por autorizar"}:
            continue
        name = re.sub(r"^\s*\d+\s*[-–—]\s*", "", cells[1]).strip()
        if not name:
            raise ValueError("El flujo de aprobación contiene un empleado vacío.")
        if name not in names:
            names.append(name)
    return names


def expiration_date(start: datetime) -> datetime:
    year = start.year + (1 if start.month == 12 else 0)
    month = 1 if start.month == 12 else start.month + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day)


class GoodsPurchaseOrderPage(OrderPortalPage):
    APPROVAL_FLOW = ((By.XPATH, "//button[@mattooltip='Ver flujo de aprobación' or @mattooltip='Ver flujo de aprobacion' or @title='Ver flujo de aprobación' or @aria-label='Ver flujo de aprobación']"),)
    SEND_APPROVAL = ((By.XPATH, "//button[@mattooltip='Enviar aprobación' or @mattooltip='Enviar a aprobación' or @mattooltip='Enviar a aprobacion' or @mattooltip='Enviar aprobacion' or @title='Enviar aprobación' or @aria-label='Enviar aprobación']"),)
    _TOOLTIP = "translate(concat(@mattooltip,' ',@title,' ',@aria-label,' ',@ng-reflect-message),'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚ','abcdefghijklmnopqrstuvwxyzáéíóú')"
    APPROVAL_FLOW += ((By.XPATH, f"//button[contains({_TOOLTIP},'flujo') and contains({_TOOLTIP},'aprob')]"),)
    SEND_APPROVAL += ((By.XPATH, f"//button[contains({_TOOLTIP},'enviar') and contains({_TOOLTIP},'aprob')]"),)
    SEND_APPROVAL += ((By.XPATH, "//button[.//mat-icon[normalize-space()='check']]"),)
    APPROVAL_DIALOG = ((By.CSS_SELECTOR, "mat-dialog-container, [role='dialog']"),)

    def read_approval_flow(self, number: str) -> list[str]:
        self._click(self.APPROVAL_FLOW, "Ver flujo de aprobación")
        dialog = self._find(self.APPROVAL_DIALOG, "el flujo de aprobación", timeout=self.query_timeout)
        heading = re.search(r"\bn[°ºo.]*\s*(?:de\s+)?orden\s*[:#-]?\s*(\d{4,14})\b", _normalized(dialog.text))
        if not heading or heading.group(1) != number:
            raise PurchaseOrderValidationError("aprobacion_orden_distinta", "El flujo de aprobación no corresponde a la OC esperada.")
        all_names = []
        signatures = set()
        while True:
            self._wait(lambda _d: not self._busy(), "cargar los aprobadores", self.query_timeout)
            dialog = self._find(self.APPROVAL_DIALOG, "el flujo de aprobación")
            def loaded_rows(_driver):
                current = self._find_now(self.APPROVAL_DIALOG)
                if not current:
                    return False
                values = [[cell.text for cell in row.find_elements(By.CSS_SELECTOR, "td, mat-cell")]
                          for row in current.find_elements(By.CSS_SELECTOR, "tr, mat-row")]
                return values if any(len(cells) >= 4 and cells[1].strip() and cells[3].strip() for cells in values) else False
            rows = self._wait(loaded_rows, "las filas del flujo de aprobación de la OC " + number, self.query_timeout)
            dialog = self._find(self.APPROVAL_DIALOG, "el flujo de aprobación")
            signature = repr(rows)
            if signature in signatures:
                raise PurchaseOrderValidationError("aprobacion_paginacion", "La paginación de aprobadores no avanzó.")
            signatures.add(signature)
            all_names.extend(pending_approvers(rows))
            next_buttons = dialog.find_elements(By.CSS_SELECTOR, "button.mat-paginator-navigation-next, button[aria-label='Next page'], button[aria-label='Página siguiente']")
            next_button = next((b for b in next_buttons if b.is_displayed() and b.is_enabled() and b.get_attribute("aria-disabled") != "true"), None)
            if next_button is None:
                break
            next_button.click()
            self._wait(lambda _d: repr([[c.text for c in r.find_elements(By.CSS_SELECTOR, "td, mat-cell")]
                for r in self._find(self.APPROVAL_DIALOG, "el flujo de aprobación").find_elements(By.CSS_SELECTOR, "tr, mat-row")]) != signature,
                "la siguiente página de aprobadores", self.query_timeout)
        dialog.send_keys(Keys.ESCAPE)
        return list(dict.fromkeys(all_names))

    def _approval_state(self) -> str:
        body = self._find_now(((By.TAG_NAME, "body"),))
        text = _normalized(body.text) if body else ""
        match = re.search(r"(?:^|\s)[a-z]{1,3}\s*\|\s*(creado|pendiente|por aprobar|por autorizar|aprobado|autorizado)\b", text)
        return match.group(1) if match else ""

    def send_and_read_approval(self, number: str, stage: Callable[[str, list[str]], None], previous: str = "") -> list[str]:
        if self._saved_numbers() != {number}:
            raise PurchaseOrderValidationError("aprobacion_orden_distinta", "No se verificó la OC antes de enviar a aprobación.")
        flow_was_visible = bool(self._elements_now(self.APPROVAL_FLOW))
        uncertain = previous in {"sending", "sent", "ambiguous"}
        if uncertain and not flow_was_visible:
            raise PurchaseOrderValidationError("aprobacion_ambigua", "El envío anterior no tiene confirmación. Revise la OC en NAF; no se repitió el visto.")
        state = self._approval_state()
        if uncertain and state == "creado":
            raise PurchaseOrderValidationError("aprobacion_ambigua", "La OC sigue CREADO y el envío anterior es ambiguo. Revísela en NAF; no se repitió el visto.")
        already_sent = state in {"pendiente", "por aprobar", "por autorizar", "aprobado", "autorizado"}
        # The list icon also exists on CREATED orders. Its visibility alone
        # must never skip the authorized send step on a new/pending receipt.
        if already_sent or uncertain:
            names = self.read_approval_flow(number)
        else:
            button = self._find(self.SEND_APPROVAL, "Enviar aprobación", enabled=True)
            if len(self._elements_now(self.SEND_APPROVAL, enabled=True)) != 1:
                raise PurchaseOrderValidationError("aprobacion_ambigua", "Hay varios controles de envío; no se pulsó ninguno.")
            self._prepare_form_control(button, "Enviar aprobación")
            stage("sending", [])
            try:
                button.click()
                def approval_ready(_driver):
                    current = self._approval_state()
                    if current == "creado" or self._busy():
                        return False
                    if not self._elements_now(self.APPROVAL_FLOW):
                        return False
                    # Prefer the verified NAF status. For older layouts without
                    # status text, require an actual post-click transition.
                    return (current in {"pendiente", "por aprobar", "por autorizar", "aprobado", "autorizado"}
                            or not flow_was_visible
                            or not self._elements_now(self.SEND_APPROVAL, enabled=True))
                def flow_or_confirm(driver):
                    if approval_ready(driver):
                        return "flow"
                    for panel in self._elements_now(self.APPROVAL_DIALOG):
                        if "aprob" in _normalized(panel.text):
                            buttons = panel.find_elements(By.XPATH, ".//button[normalize-space(.)='Sí' or normalize-space(.)='Si' or normalize-space(.)='Enviar' or normalize-space(.)='Aceptar']")
                            if len(buttons) == 1 and buttons[0].is_enabled():
                                return buttons[0]
                    return False
                response = self._wait(flow_or_confirm, "el envío a aprobación y el cambio de estado de la OC", self.query_timeout)
                if response != "flow":
                    response.click()
                    self._wait(approval_ready, "el cambio de estado después de confirmar aprobación", self.query_timeout)
                stage("sent", [])
            except Exception:
                stage("ambiguous", [])
                raise
            names = self.read_approval_flow(number)
        if not names:
            raise PurchaseOrderValidationError("aprobadores_pendientes", "No se encontraron aprobadores pendientes. No se vació GENERAL ni se repitió el envío.")
        stage("read", names)
        return names

    MOVEMENTS = (
        (By.XPATH, "//*[self::a or self::button or self::span][contains(translate(normalize-space(.),'ÁÉÍÓÚáéíóú','AEIOUaeiou'),'Movimientos')]") ,
    )
    PURCHASE_ORDERS = (
        (By.XPATH, "//*[self::a or self::button or self::span][contains(translate(normalize-space(.),'Óó','Oo'),'Ordenes de Compra')]") ,
    )
    GOODS = (
        (By.XPATH, "//*[self::a or self::button or self::span][normalize-space()='Bienes']"),
    )
    FORM_TITLE = (
        (By.XPATH, "//*[contains(translate(normalize-space(.),'Óó','Oo'),'Orden de compra - bienes')]"),
    )
    SAVE = (
        (By.XPATH, "//button[.//*[normalize-space()='Guardar'] or normalize-space()='Guardar']"),
    )
    ADD_ARTICLE = (
        (By.XPATH, "//a[normalize-space(.)='Deseo agregar un nuevo registro']"),
        (By.XPATH, "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agregar un nuevo registro')]"),
    )
    OBSERVATIONS_TAB = (
        (By.XPATH, "//*[@role='tab'][normalize-space(.)='text_formatObservaciones' or contains(normalize-space(.),'Observaciones')]"),
    )
    OBSERVATION = (
        (By.XPATH, "//*[@role='tabpanel' and @aria-labelledby=//*[@role='tab' and @aria-selected='true' and contains(normalize-space(.),'Observaciones')]/@id]//textarea[not(@readonly) and not(@disabled)]"),
    )
    ORDER_NUMBER = (
        (By.XPATH, "//h4[contains(normalize-space(.),'de orden')]"),
        (By.XPATH, "//mat-form-field[.//mat-label[contains(normalize-space(.),'orden')]]//input"),
    )

    def _shell_landmark(self) -> str | bool:
        if self._find_now(self.FORM_TITLE):
            return "goods-form"
        if self._find_now(self.GOODS):
            return "goods"
        if self._find_now(self.PURCHASE_ORDERS):
            return "purchase-orders"
        if self._find_now(self.MOVEMENTS):
            return "movements"
        return super()._shell_landmark()

    # Company selection and login are shared with manual OC downloads.
    _select_company = OrderPortalPage._select_company

    def _try_direct_goods_route(self) -> bool:
        # The route preserves the requested destination through company selection
        # and avoids traversing the complete Angular menu on every login.
        try:
            self._navigate(GOODS_PURCHASE_ORDER_URL)
            state = self._wait_for_any(
                (
                    (self.FORM_TITLE, "form"),
                    (self.COMPANY_INPUT, "company"),
                ),
                "el formulario de Bienes o la selección de compañía",
                timeout=min(self.element_timeout, 15),
            )
            if state == "form":
                return True
            self._select_company()
            self._find(
                self.FORM_TITLE,
                "el formulario Orden de compra - bienes",
                timeout=min(self.element_timeout, 15),
            )
            return True
        except DownloadCancelledError:
            raise
        except (AttributeError, TimeoutError, RuntimeError, WebDriverException):
            # Keep the proven menu route as a compatibility fallback.
            return False

    def _navigate_shell_to_orders(self, landmark: str = "") -> None:
        if self._find_now(self.FORM_TITLE):
            return
        self._ensure_navigation_open()
        # Permission menus arrive after authentication. Never reload the shell
        # merely because they have not arrived yet: that aborts check_sso.
        if not self._find_now(self.MOVEMENTS) and not self._find_now(self.COMPANY_INPUT):
            state = self._wait_for_any(
                ((self.MOVEMENTS, "movements"), (self.COMPANY_INPUT, "company"),
                 (self.FORM_TITLE, "form")),
                "los permisos del menu de NAF o la seleccion de compania",
                timeout=self.login_timeout,
            )
            if state == "form":
                return
            self._ensure_navigation_open()
        if landmark == "company" or self._find_now(self.COMPANY_INPUT):
            self._select_company()
        if not self._find_now(self.MOVEMENTS):
            self._toggle_menu_now()
        try:
            self._open_menu_item(
                self.MOVEMENTS,
                "Movimientos",
                ((self.PURCHASE_ORDERS, "purchase-orders"), (self.GOODS, "goods")),
            )
        except TimeoutError:
            # Algunas sesiones exigen escoger compañía antes de mostrar Movimientos.
            if self._find_now(self.ACCESSES):
                self._open_menu_item(
                    self.ACCESSES,
                    "Accesos",
                    ((self.COMPANY_SELECTION, "company-menu"), (self.MOVEMENTS, "movements")),
                )
                if self._find_now(self.COMPANY_SELECTION):
                    self._open_menu_item(
                        self.COMPANY_SELECTION,
                        "Selección de Compañía",
                        ((self.COMPANY_INPUT, "company"),),
                    )
                    self._select_company()
            self._open_menu_item(
                self.MOVEMENTS,
                "Movimientos",
                ((self.PURCHASE_ORDERS, "purchase-orders"), (self.GOODS, "goods")),
            )
        if not self._find_now(self.GOODS):
            self._open_menu_item(
                self.PURCHASE_ORDERS,
                "Órdenes de Compra",
                ((self.GOODS, "goods"), (self.FORM_TITLE, "form")),
            )
        if not self._find_now(self.FORM_TITLE):
            state = self._open_menu_item(
                self.GOODS,
                "Bienes",
                ((self.FORM_TITLE, "form"), (self.COMPANY_INPUT, "company")),
            )
            if state == "company":
                self._select_company()
                if not self._find_now(self.FORM_TITLE):
                    # Reopen the menu once after the company context changes.
                    self._open_menu_item(
                        self.MOVEMENTS, "Movimientos",
                        ((self.PURCHASE_ORDERS, "purchase-orders"), (self.GOODS, "goods")),
                    )
                    if not self._find_now(self.GOODS):
                        self._open_menu_item(
                            self.PURCHASE_ORDERS, "Órdenes de Compra",
                            ((self.GOODS, "goods"),),
                        )
                    self._open_menu_item(
                        self.GOODS, "Bienes después de seleccionar compañía",
                        ((self.FORM_TITLE, "form"),),
                    )
        self._find(self.FORM_TITLE, "el formulario Orden de compra - bienes")

    @staticmethod
    def _label_xpath(label: str, tag: str = "input") -> tuple[Locator, ...]:
        safe = label.replace("'", "")
        return (
            (By.XPATH, f"//mat-form-field[.//mat-label[contains(normalize-space(.),'{safe}')]]//{tag}"),
            (By.XPATH, f"//*[self::label or self::span][contains(normalize-space(.),'{safe}')]/following::{tag}[1]"),
            (By.CSS_SELECTOR, f"{tag}[placeholder*='{safe}'], {tag}[aria-label*='{safe}']"),
        )

    def _select_exact(
        self,
        label: str,
        value: str,
        *,
        error_code: str,
        index: int = 0,
        allow_unique_code: bool = False,
    ) -> None:
        expected = _normalized(value)
        confirmed_labels: set[str] = set()

        def selected_value() -> str:
            fields = self._field_elements(label)
            if len(fields) <= index:
                return ""
            selected = self.driver.execute_script(
                "const e=arguments[0], s=e.closest('ng-select'); "
                "return s ? [...s.querySelectorAll('.ng-value-label')].map(v=>v.textContent).join(' ') : e.value;",
                fields[index],
            )
            return _normalized(selected)

        def committed(_driver: Any) -> bool:
            try:
                actual = selected_value()
                return bool(actual) and actual in confirmed_labels
            except StaleElementReferenceException:
                return False

        def open_catalog(_driver: Any) -> bool:
            try:
                fields = self._field_elements(label)
                if len(fields) <= index or not fields[index].is_enabled():
                    return False
                # Re-selecting the current frequency can leave ng-select open.
                # Only the committed label counts, never text in the search input.
                if selected_value() == expected:
                    confirmed_labels.add(expected)
                    return True
                field = fields[index]
                field.click()
                if not field.get_attribute("readonly"):
                    field.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                    field.send_keys(value)
                return True
            except StaleElementReferenceException:
                return False
        self._wait(open_catalog, f"abrir el catálogo {label}", self.element_timeout)
        pattern = re.compile(rf"(?:^|\s|[()/-]){re.escape(expected)}(?:$|\s|[()/-])")
        last_count = 0

        def choose(_driver: Any) -> bool:
            nonlocal last_count
            if confirmed_labels == {expected} and committed(_driver):
                return True
            # Angular replaces the options while the supplier search is loading.
            # Resolve and click in one poll; never retain an option across polls.
            try:
                if self._elements_now(((By.CSS_SELECTOR, "ng-select.ng-select-loading, ng-dropdown-panel .ng-spinner-loader"),)):
                    return False
                options = self._elements_now((
                    (By.CSS_SELECTOR, "ng-dropdown-panel .ng-option:not(.ng-option-disabled), "
                     "mat-option, [role='option'], .mat-option"),
                ))
                matches = [option for option in options
                           if _normalized(option.text) == expected or (
                               label in ("Solicita", "Tipo") and
                               re.sub(r"^[a-z0-9]+\s*-\s*", "", _normalized(option.text)) == expected)]
                if not matches and allow_unique_code:
                    matches = [option for option in options
                               if pattern.search(_normalized(option.text))]
                last_count = len(matches)
                if len(matches) != 1:
                    return False
                option_text = _normalized(matches[0].text)
                display = option_text
                if label == "Proveedor":
                    display = re.sub(r"^\d+\s*-\s*", "", option_text)
                    display = re.sub(rf"\s*-\s*{re.escape(expected)}$", "", display)
                elif label in ("Solicita", "Tipo"):
                    display = re.sub(r"^[a-z0-9]+\s*-\s*", "", option_text)
                elif label == "Bodega":
                    display = re.sub(rf"^{re.escape(expected)}\s*-\s*", "", option_text)
                elif label == "No. Artículo":
                    display = expected
                confirmed_labels.update((option_text, display))
                fields = self._field_elements(label)
                if len(fields) <= index:
                    return False
                # Only Enter on the exact marked result, never on uncommitted text.
                if "ng-option-marked" not in (matches[0].get_attribute("class") or "").split():
                    fields[index].send_keys(Keys.DOWN)
                    return False
                fields[index].send_keys(Keys.RETURN)
                return True
            except StaleElementReferenceException:
                return False

        try:
            self._wait(choose, f"la selección de {label}", self.element_timeout)
        except TimeoutError as exc:
            raise PurchaseOrderValidationError(
                error_code,
                f"{label}: no se pudo seleccionar '{value}' "
                f"(coincidencias exactas: {last_count}).",
            ) from exc
        recovery_clicks = 0
        next_recovery = time.monotonic() + 1

        def confirm_selection(driver: Any) -> bool:
            nonlocal recovery_clicks, next_recovery
            if committed(driver):
                return True
            # NAF sometimes consumes Enter while refreshing the frequency catalog.
            # Retry only the exact visible option, never the form or Guardar.
            if label != "Frecuencia de pago" or recovery_clicks >= 2 or time.monotonic() < next_recovery:
                return False
            next_recovery = time.monotonic() + 1
            try:
                options = self._elements_now(((By.CSS_SELECTOR,
                    "ng-dropdown-panel .ng-option:not(.ng-option-disabled)"),))
                matches = [option for option in options if _normalized(option.text) == expected]
                if len(matches) == 1:
                    matches[0].click()
                    recovery_clicks += 1
            except (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException):
                return False
            return committed(driver)

        self._wait(confirm_selection, f"confirmar el valor seleccionado de {label}", self.element_timeout)
        def blur(_driver: Any) -> bool:
            try:
                fields = self._field_elements(label)
                if len(fields) <= index:
                    return False
                fields[index].send_keys(Keys.ESCAPE)
                fields = self._field_elements(label)
                if len(fields) <= index:
                    return False
                fields[index].send_keys(Keys.TAB)
                return True
            except StaleElementReferenceException:
                return False
        self._wait(blur, f"salir del campo {label}", self.element_timeout)

        def closed_and_committed(_driver: Any) -> bool:
            try:
                fields = self._field_elements(label)
                if len(fields) <= index or not committed(_driver):
                    return False
                return bool(self.driver.execute_script(
                    "const e=arguments[0], s=e.closest('ng-select'); "
                    "if(s) return !s.classList.contains('ng-select-opened') && e.getAttribute('aria-expanded') !== 'true'; "
                    "const id=e.getAttribute('aria-controls') || e.getAttribute('aria-owns'); "
                    "const panel=id && document.getElementById(id); "
                    "return e.getAttribute('aria-expanded') !== 'true' && (!panel || !panel.getClientRects().length);",
                    fields[index],
                ))
            except StaleElementReferenceException:
                return False
        self._wait(closed_and_committed, f"cerrar y validar el catálogo de {label}", self.element_timeout)

    def _prepare_form_control(self, element: Any, description: str) -> None:
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center',inline:'nearest'});", element)
        menu_handled = False
        def clear(_driver: Any) -> bool:
            nonlocal menu_handled
            state = self.driver.execute_script("""
                const e=arguments[0], r=e.getBoundingClientRect();
                if(!r.width || !r.height || e.disabled) return 'wait';
                const x=Math.max(0,Math.min(innerWidth-1,r.x+r.width/2));
                const y=Math.max(0,Math.min(innerHeight-1,r.y+r.height/2));
                const hit=document.elementFromPoint(x,y);
                if(hit && (hit===e || e.contains(hit))) return 'clear';
                return hit && hit.closest('[class*="simple-sidenav"],mat-sidenav,mat-drawer')
                    ? 'menu' : 'wait';
            """, element)
            if state == 'clear':
                return True
            if state == 'menu' and not menu_handled:
                menu_handled = True
                self._toggle_menu_now()
                ActionChains(self.driver).move_to_element(
                    self.driver.find_element(By.TAG_NAME, 'body')).perform()
            return False
        try:
            self._wait(clear, f"dejar libre {description}", self.element_timeout)
        except TimeoutError as exc:
            raise PurchaseOrderValidationError(
                "control_naf_obstruido", f"{description}: un elemento tapa el control; no se pulso."
            ) from exc

    def _set_date(self, label: str, value: datetime) -> None:
        # Live NAF uses the native US parser despite displaying day/month/year.
        self._set_text(label, value.strftime("%m/%d/%Y"))
        def accepted(_driver: Any) -> bool:
            try:
                fields = self._field_elements(label)
                if not fields:
                    return False
                actual = fields[0].get_attribute("value") or ""
                return datetime.strptime(actual.strip(), "%d/%m/%Y").date() == value.date()
            except (ValueError, StaleElementReferenceException):
                return False
        self._wait(accepted, f"validar la fecha mostrada en {label}", self.element_timeout)

    def _set_text(self, label: str, value: str, *, index: int = 0) -> None:
        numeric = label in ("Mensual", "Días de entrega", "Cant.", "Precio")
        def ready(_driver: Any) -> Any:
            try:
                fields = self._field_elements(label)
                return fields[index] if len(fields) > index and fields[index].is_enabled() else False
            except StaleElementReferenceException:
                return False

        attempts = 0
        def write(_driver: Any) -> bool:
            nonlocal attempts
            try:
                field = ready(_driver)
                if not field:
                    return False
                attempts += 1
                if attempts > 3:
                    raise PurchaseOrderValidationError("campo_naf_inestable", f"{label}: NAF reemplazó el control durante la escritura.")
                self._prepare_form_control(field, label)
                field.click()
                field.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                field.send_keys(value)
                return True
            except StaleElementReferenceException:
                return False
        try:
            self._wait(ready, f"habilitar {label}", self.element_timeout)
            self._wait(write, f"llenar {label}", self.element_timeout)
            def committed(_driver: Any) -> bool:
                try:
                    field = ready(_driver)
                    if not field:
                        return False
                    actual = field.get_attribute("value") or ""
                    return Decimal(actual) == Decimal(value) if numeric else actual.strip() == value.strip()
                except (InvalidOperation, StaleElementReferenceException):
                    return False
            self._wait(committed, f"verificar escritura de {label}", self.element_timeout)
            def press(key: str) -> Any:
                def action(driver: Any) -> bool:
                    try:
                        field = ready(driver)
                        if not field or not committed(driver):
                            return False
                        field.send_keys(key)
                        return True
                    except StaleElementReferenceException:
                        return False
                return action
            if numeric:
                self._wait(press(Keys.RETURN), f"confirmar {label} con Enter", self.element_timeout)
            self._wait(press(Keys.TAB), f"salir de {label}", self.element_timeout)
            if numeric:
                self._wait(committed, f"confirmar {label} después de Enter", self.element_timeout)
        except TimeoutError as exc:
            raise PurchaseOrderValidationError(
                "campo_naf_no_encontrado", f"No se pudo llenar el campo {label}. {exc}",
            ) from exc

    def _field_elements(self, label: str) -> list[Any]:
        if label == "Mensual":
            return self._elements_now(((By.XPATH, "//mat-form-field[.//mat-label[translate(normalize-space(.), 'abcdefghijklmnopqrstuvwxyz', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ')='MENSUAL']]//input[@type='number']"),), enabled=True)
        mapped = {
            "Proveedor": 'ng-select[name="noProveedor"] input',
            "Solicita": 'ng-select[name="noEmpleado"] input',
            "Frecuencia de pago": 'ng-select[name="idTipoFrecuencia"] input',
            "Tipo": 'ng-select[name="idTipoTransaccion"] input',
            "Bodega": 'ng-select[name="codigo"] input',
            "Tipo de distribución": 'ng-select[name="valor2"] input',
            "Fecha": 'input[name="fecha"]',
            "Fecha de vencimiento": 'input[name="fechaVence"]',
            "No. Artículo": 'oc-bienes-detalles ng-select[name="noArticulo"] input',
            "Cant.": 'oc-bienes-detalles td.mat-column-cantidad input',
            "Precio": 'oc-bienes-detalles td.mat-column-costoUnitario input',
        }
        if label in mapped:
            return self._elements_now(((By.CSS_SELECTOR, mapped[label]),), enabled=True)
        # Match the actual field label, never a section such as "Solicitantes".
        return self.driver.execute_script(
            """
            const norm = s => (s || '').normalize('NFD')
                .replace(/[\\u0300-\\u036f]/g, '').toLowerCase()
                .replace(/\\([^)]*\\)/g, '').replace(/[*.：:]/g, '')
                .replace(/\\s+/g, ' ').trim();
            const wanted = norm(arguments[0]);
            const visible = e => e.getClientRects().length > 0;
            const inputs = node => [...node.querySelectorAll(
                'input:not([type=hidden]),textarea')].filter(visible);
            const labels = [...document.querySelectorAll(
                'mat-label,label,th,[role=columnheader],.mat-header-cell,span')]
                .filter(e => visible(e) && (norm(e.textContent) === wanted ||
                    (wanted === 'tipo de distribucion' && norm(e.textContent) === 'tipo de distribucion manual')));
            for (const label of labels) {
                if (label.matches('th,[role=columnheader],.mat-header-cell')) {
                    const table = label.closest('table');
                    if (table) {
                        const col = [...label.parentElement.children].indexOf(label);
                        return [...table.querySelectorAll('tbody tr')]
                            .flatMap(row => row.children[col] ? inputs(row.children[col]) : []);
                    }
                }
                const id = label.getAttribute('for');
                const linked = id && document.getElementById(id);
                if (linked && visible(linked)) {
                    if (linked.matches('input,textarea')) return [linked];
                    const fields = inputs(linked);
                    if (fields.length === 1) return fields;
                }
                for (let node = label.parentElement; node && node !== document.body;
                     node = node.parentElement) {
                    const fields = inputs(node);
                    if (fields.length > 1) break;
                    if (fields.length === 1) return fields;
                }
            }
            return [...document.querySelectorAll('input:not([type=hidden]),textarea')]
                .filter(e => visible(e) &&
                    [e.placeholder, e.getAttribute('aria-label')].some(v => norm(v) === wanted));
            """, label,
        ) or []

    def _set_checkbox(self, label: str, checked: bool) -> None:
        locators = (
            (By.XPATH, f"//mat-checkbox[contains(normalize-space(.),'{label}')]"),
            (By.XPATH, f"//label[contains(normalize-space(.),'{label}')]/preceding::input[@type='checkbox'][1]"),
        )
        element = self._find(locators, f"la casilla {label}")
        selected = "checked" in str(element.get_attribute("class")) or bool(
            self.driver.execute_script(
                "const e=arguments[0]; const i=e.matches('input')?e:e.querySelector('input'); return i && i.checked;",
                element,
            )
        )
        if selected != checked:
            self._click_element(element)

    def fill(self, draft: PurchaseOrderDraft) -> PurchaseOrderDraft:
        now = datetime.now(ZoneInfo("America/Guayaquil"))
        if not draft.ruc:
            raise PurchaseOrderValidationError(
                "proveedor_sin_ruc",
                f"El proveedor '{draft.supplier}' no tiene RUC asociado.",
            )
        self._select_exact(
            "Proveedor",
            draft.ruc,
            error_code="proveedor_no_encontrado",
            allow_unique_code=True,
        )
        self._select_exact(
            "Solicita",
            draft.requester,
            error_code="solicitante_no_encontrado",
        )
        self._set_date("Fecha", now)
        self._select_exact("Tipo", "BIENES", error_code="catalogo_naf_no_encontrado")
        self._set_checkbox("Genera Inventario", True)
        self._select_exact("Frecuencia de pago", "MENSUAL", error_code="catalogo_naf_no_encontrado")
        self._set_text("Mensual", "1")
        self._select_exact(
            "Bodega",
            "BQEF",
            error_code="catalogo_naf_no_encontrado",
            allow_unique_code=True,
        )
        # Frecuencia/Mensual recalculan estos valores en NAF: fijarlos después.
        self._set_text("Días de entrega", "30")
        self._set_date("Fecha de vencimiento", expiration_date(now))
        self._select_exact("Tipo de distribución", "Manual", error_code="catalogo_naf_no_encontrado")
        for index, article in enumerate(draft.articles):
            if len(self._field_elements("No. Artículo")) <= index:
                self._click(self.ADD_ARTICLE, "Agregar un nuevo registro")
                self._wait(
                    lambda _driver, row_index=index: len(self._field_elements("No. Artículo")) > row_index,
                    "la fila editable del artículo (NAF no la habilitó; no se guardará la orden)",
                    self.element_timeout,
                )
            self._select_exact(
                "No. Artículo",
                article.code,
                error_code="articulo_no_existe",
                index=index,
                allow_unique_code=True,
            )
            self._set_text("Cant.", format_decimal(article.quantity), index=index)
            self._set_text("Precio", format_decimal(article.unit_price), index=index)
            self._normalize_article_description(article, index)
        self.fill_observation(build_observation(draft))
        return draft

    def _normalize_article_description(self, article, index):
        for label in ('Descripción', 'Descripcion'):
            fields = self._field_elements(label)
            if len(fields) <= index:
                continue
            field = fields[index]
            if not callable(getattr(field, 'get_attribute', None)):
                continue
            current = field.get_attribute('value') or ''
            if not current:
                def populated(_driver):
                    try:
                        ready = self._field_elements(label)
                        return ready[index].get_attribute('value') if len(ready) > index else False
                    except StaleElementReferenceException:
                        return False
                current = self._wait(populated, 'cargar la descripción del artículo antes de normalizarla', self.element_timeout)
                field = self._field_elements(label)[index]
            normalized = normalize_observation(current)
            if current and current != normalized:
                if not field.is_enabled() or field.get_attribute('readonly'):
                    # Catalog descriptions are readonly to keyboard input. Update only
                    # this unsaved form control through its normal input/change events;
                    # never remove readonly, enable a disabled control, or edit the catalog.
                    written = self.driver.execute_script("""
                        const field = arguments[0], value = arguments[1];
                        const disabled = field.disabled, readonly = field.readOnly;
                        if (!disabled && !readonly) return false;
                        const prototype = field.tagName === 'TEXTAREA'
                            ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
                        setter.call(field, value);
                        field.dispatchEvent(new Event('input', {bubbles: true}));
                        field.dispatchEvent(new Event('change', {bubbles: true}));
                        field.dispatchEvent(new Event('blur', {bubbles: true}));
                        return field.value === value && field.readOnly === readonly && field.disabled === disabled;
                    """, field, normalized)
                    if not written:
                        raise PurchaseOrderValidationError('descripcion_rechazada',
                            f'Artículo {article.code}: NAF no aceptó la descripción normalizada en el formulario.')
                    def accepted(_driver):
                        try:
                            ready = self._field_elements(label)
                            return len(ready) > index and ready[index].get_attribute('value') == normalized
                        except StaleElementReferenceException:
                            return False
                    self._wait(accepted, 'confirmar la descripción normalizada de la OC', self.element_timeout)
                else:
                    self._set_text(label, normalized, index=index)
            return
        if normalize_observation(article.description) != article.description:
            raise PurchaseOrderValidationError('descripcion_no_editable',
                f'Artículo {article.code}: no se encontró la descripción editable de NAF para normalizar sus caracteres. No se guardó la orden.')

    def fill_observation(self, observation: str) -> None:
        self._verified_observation = ""
        observation = normalize_observation(observation)
        if not observation:
            raise PurchaseOrderValidationError("observacion_rechazada", "La observación está vacía; no se guardará la orden.")
        try:
            self._click(self.OBSERVATIONS_TAB, "la pestaña Observaciones")
            field = self._find(self.OBSERVATION, "Observaciones", enabled=True)
            maximum = field.get_attribute("maxlength")
            limit = min(OBSERVATION_LIMIT, int(maximum)) if maximum and maximum.isdigit() else OBSERVATION_LIMIT
            if observation_length(observation) > limit:
                raise ValueError(f"Observación supera el límite NAF de {limit}; recargue GENERAL para dividir la orden antes de guardar.")
            self._write(self.OBSERVATION, observation, "el campo Observaciones")
            self._find(self.OBSERVATION, "Observaciones", enabled=True).send_keys(Keys.TAB)
            self._wait(
                lambda _driver: self._observation_matches(observation),
                "confirmar la observación completa después de salir del campo", self.element_timeout,
            )
            self._verified_observation = observation
        except Exception as exc:
            raise PurchaseOrderValidationError(
                "observacion_rechazada", f"No se pudo ingresar la observación: {exc}"
            ) from exc

    def _observation_matches(self, expected: str) -> bool:
        try:
            field = self._find_now(self.OBSERVATION, enabled=True)
            return bool(field) and field.get_attribute("aria-invalid") != "true" and (
                (field.get_attribute("value") or "").replace("\r\n", "\n") == expected
            )
        except StaleElementReferenceException:
            return False

    def _saved_numbers(self) -> set[str]:
        """Read fresh DOM references; a replaced heading is not a failed save."""
        numbers: set[str] = set()
        path = urlsplit(self.driver.current_url).path
        match = re.fullmatch(r"/naf/compras/movimientos/orden-compra/bienes/(\d{4,14})/?", path)
        if match:
            numbers.add(match.group(1))
        for element in self._elements_now(self.ORDER_NUMBER):
            value = str(element.get_attribute("value") or element.text).strip()
            match = re.fullmatch(r"(?:n[°ºo]?\s*de orden\s*[:#-]?\s*)?(\d{4,14})", _normalized(value))
            if match:
                numbers.add(match.group(1))
        return numbers

    def save_once(self) -> str:
        expected = getattr(self, "_verified_observation", "")
        if not expected or not self._observation_matches(expected):
            raise PurchaseOrderValidationError("observacion_rechazada", "La observación no está verificada; no se pulsó Guardar.")
        before = set(self._notifications())
        previous = self._wait(lambda _driver: (self._saved_numbers(),),
                              "leer el estado anterior a Guardar", self.element_timeout)[0]
        button = self._find(self.SAVE, "el botón Guardar", enabled=True)
        self._prepare_form_control(button, "Guardar")
        # Consume verification before the click: an ambiguous response cannot resubmit.
        self._verified_observation = ""
        # No JS fallback: even a failed WebDriver response can mean NAF received
        # the click. From this point only observe, never dispatch it again.
        try:
            button.click()
        except (ElementClickInterceptedException, ElementNotInteractableException) as exc:
            raise PurchaseOrderValidationError(
                "control_naf_obstruido", "NAF impidio pulsar Guardar. No se repitio el clic."
            ) from exc
        except Exception:
            pass
        deadline = time.monotonic() + self.query_timeout
        confirmation = ""
        candidate = ""
        while time.monotonic() < deadline:
            cancelled = getattr(self, "cancelled", None)
            if cancelled and cancelled():
                raise PurchaseOrderValidationError("guardado_ambiguo", "Consulta cancelada tras Guardar; recuperar antes de regenerar.")
            try:
                numbers = self._saved_numbers()
                current = [text for text in self._notifications() if text not in before]
            except StaleElementReferenceException:
                time.sleep(0.25)
                continue
            body = " ".join(current)
            if body:
                confirmation = body
                if any(word in _normalized(body) for word in ("error", "invalido", "rechaz", "no validos", "no valido")):
                    raise PurchaseOrderValidationError("error_naf", body)
                match = re.search(r"(?:orden|oc)\D{0,20}(\d{4,14})", body, re.IGNORECASE)
                if match and numbers:
                    numbers.add(match.group(1))
            if len(numbers) == 1 and numbers.isdisjoint(previous):
                number = next(iter(numbers))
                if candidate == number:
                    return number
                candidate = number
            else:
                candidate = ""
            time.sleep(0.25)
        raise PurchaseOrderValidationError(
            "guardado_ambiguo",
            "NAF no mostró una confirmación inequívoca con el número de orden; no se reintentó Guardar."
            + (f" Respuesta: {confirmation}" if confirmation else ""),
        )

    def open_fresh_form(self) -> None:
        self._verified_observation = ""
        self._navigate(PORTAL_APP_URL)
        landmark = self._wait_for_shell(self.login_timeout)
        self._navigate_shell_to_orders(landmark)
        self._wait(
            lambda _driver: self.driver.execute_script(
                "const supplier=document.querySelector('ng-select[name=noProveedor]');"
                "const headings=[...document.querySelectorAll('h4')];"
                "return !!supplier && !supplier.querySelector('.ng-value-label') && "
                "!document.querySelector('ng-select[name=noArticulo] .ng-value-label') && "
                "headings.some(e=>/de orden\\s*-\\s*$/i.test(e.textContent));"
            ),
            "un formulario nuevo sin proveedor, artículos ni número de orden anterior", self.element_timeout,
        )


class SeleniumPurchaseOrderGateway:
    def __init__(self, settings: SettingsRepository, app_paths: AppPaths):
        self.settings = settings
        self.app_paths = app_paths

    def _create_driver(self, headless: bool) -> webdriver.Chrome:
        return create_corporate_browser(
            Path.cwd(), headless,
            _safe_int(self.settings.get("downloads", "page_load_timeout", 25), 25, 20, 240),
            network_diagnostics=True,
            naf_navigation=True,
            naf_cache_dir=self.app_paths.root / "browser-cache" / "naf",
        )

    def _page(self, driver: webdriver.Chrome) -> GoodsPurchaseOrderPage:
        element_timeout = self.settings.get(
            "automation", "oc_element_timeout", None
        )
        if element_timeout in (None, ""):
            element_timeout = self.settings.get(
                "automation", "oc_field_timeout", 45
            )
        return GoodsPurchaseOrderPage(
            driver,
            Path.cwd(),
            diagnostics_folder=self.app_paths.diagnostics / "precarga_oc",
            element_timeout=_safe_int(element_timeout, 45, 10, 180),
            login_timeout=_safe_int(
                self.settings.get("automation", "oc_login_timeout", 100),
                100,
                20,
                300,
            ),
            query_timeout=int(self.settings.get("automation", "oc_save_timeout", 75)),
            login_attempts=self._login_attempts(),
            auth_module="carga_automatica_oc",
        )

    def _login_attempts(self) -> int:
        try:
            value = int(self.settings.get("automation", "oc_login_retries", 3))
        except (TypeError, ValueError):
            value = 3
        return max(1, min(value, 3))

    def recover_approvers(self, credentials, entries, callback, *, headless=False, progress=None, cancelled=None):
        driver = None
        items = []
        try:
            driver = self._create_driver(headless)
            page = self._page(driver)
            page.headless, page.cancelled = headless, cancelled
            page.auth_progress = lambda message: progress(0, len(entries), message) if progress else None
            page.login_and_open_orders(credentials)
            for index, entry in enumerate(entries, 1):
                if cancelled and cancelled():
                    break
                number = entry["number"]
                try:
                    page._navigate(GOODS_PURCHASE_ORDER_URL + "/" + number)
                    page._wait(lambda _d: page._saved_numbers() == {number}, "abrir la OC existente", page.query_timeout)
                    callback(PurchaseOrderDraft.model_validate(entry["draft"]), number, page)
                    items.append(OperationItem(key=number, status=ItemStatus.SUCCEEDED, message="Aprobadores sincronizados en O."))
                except Exception as exc:
                    diagnostic = page.capture_diagnostic(f"aprobacion_{number}", exc)
                    items.append(OperationItem(key=number, status=ItemStatus.FAILED, message=f"{exc}. {diagnostic}"))
                if progress:
                    progress(index, len(entries), f"Revisada aprobación de OC {number}")
            return OperationResult.from_items(items, "Recuperación de aprobadores finalizada; no se crearon órdenes.")
        finally:
            if driver:
                driver.quit()

    def preload(
        self,
        credentials: SessionCredentials,
        drafts: Sequence[PurchaseOrderDraft],
        *,
        headless: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        before_save: Callable[[PurchaseOrderDraft], None] | None = None,
        on_saved: Callable[[PurchaseOrderDraft, str], None] | None = None,
        after_saved: Callable[[PurchaseOrderDraft, str, Any], None] | None = None,
    ) -> OperationResult:
        driver: webdriver.Chrome | None = None
        items: list[OperationItem] = []
        total = len(drafts)
        try:
            page: GoodsPurchaseOrderPage | None = None
            username = credentials.username.split("@", 1)[0].strip().upper()
            if cancelled and cancelled():
                raise RuntimeError("Precarga cancelada antes de ingresar a NAF.")
            if progress:
                progress(0, total, f"Ingresando a NAF como {username}…")
            driver = self._create_driver(headless)
            page = self._page(driver)
            page.headless = headless
            page.cancelled = cancelled
            page.auth_progress = (
                lambda message: progress(0, total, message) if progress else None
            )
            try:
                page.login_and_open_orders(credentials)
            except Exception as exc:
                raise RuntimeError(
                    f"No se completó el acceso a NAF como {username}. {exc}"
                ) from exc
            for index, draft in enumerate(drafts, start=1):
                key = draft.operation_key
                if cancelled and cancelled():
                    items.extend(
                        OperationItem(
                            key=pending.operation_key,
                            status=ItemStatus.SKIPPED,
                            error_code="cancelled",
                            message="No procesado por cancelación.",
                        )
                        for pending in drafts[index - 1:]
                    )
                    return OperationResult(
                        status=JobStatus.CANCELLED,
                        items=items,
                        finished_at=utc_now(),
                        message="Precarga de OC cancelada.",
                    )
                save_started = False
                try:
                    if index > 1:
                        page.open_fresh_form()
                    resolved = page.fill(draft)
                    if before_save:
                        before_save(draft)
                    save_started = True
                    number = page.save_once()
                    if progress:
                        progress(index, total, f"Guardada en NAF: OC {number}. Pendiente de sincronizar.")
                    if on_saved:
                        try:
                            on_saved(draft, number)
                        except Exception as exc:
                            items.append(OperationItem(
                                key=key, status=ItemStatus.FAILED, error_code="oc_guardada_hoja_pendiente",
                                message=f"OC {number} guardada; sincronización pendiente: {exc}. No regenerar.",
                                payload={"task_number": draft.task_number, "task_numbers": draft.task_numbers, "ruc": draft.ruc,
                                         "order_number": number, "sheet_written": False},
                            ))
                            items.extend(OperationItem(key=d.operation_key, status=ItemStatus.SKIPPED,
                                                       message="Lote detenido por sincronización pendiente.") for d in drafts[index:])
                            return OperationResult.from_items(items, "Lote detenido; recuperar la OC guardada antes de continuar.")
                    if after_saved:
                        try:
                            after_saved(draft, number, page)
                        except Exception as exc:
                            diagnostic = page.capture_diagnostic(f"aprobacion_{number}", exc)
                            items.append(OperationItem(key=key, status=ItemStatus.FAILED,
                                error_code="oc_aprobacion_pendiente",
                                message=f"OC {number} guardada y sincronizada en G. Aprobación/columna O pendiente: {exc}. Use Recuperar aprobadores; no regenerar. {diagnostic}",
                                payload={"task_number": draft.task_number, "task_numbers": draft.task_numbers, "order_number": number, "sheet_written": True}))
                            items.extend(OperationItem(key=d.operation_key, status=ItemStatus.SKIPPED,
                                message="Lote detenido por aprobación pendiente.") for d in drafts[index:])
                            return OperationResult.from_items(items, "Recupere los aprobadores de la OC existente antes de continuar.")
                    items.append(
                        OperationItem(
                            key=key,
                            status=ItemStatus.SUCCEEDED,
                            message=f"Guardada en NAF: OC {number}; " + ("Sincronizada en Google Sheets." if on_saved else "Pendiente de sincronizar."),
                            payload={
                                "task_number": draft.task_number,
                                "task_numbers": draft.task_numbers,
                                "department": draft.department,
                                "supplier": draft.supplier,
                                "ruc": draft.ruc,
                                "requester": resolved.requester,
                                "order_number": number,
                                "sheet_written": on_saved is not None,
                                "articles": len(draft.articles),
                                "subtotal": format_decimal(draft.subtotal),
                            },
                        )
                    )
                except PurchaseOrderValidationError as exc:
                    diagnostic = page.capture_diagnostic(f"oc_{draft.task_number}", exc) if save_started else ""
                    items.append(
                        OperationItem(
                            key=key,
                            status=ItemStatus.FAILED,
                            error_code=exc.code,
                            message=str(exc) + (f" Diagnóstico: {diagnostic}" if diagnostic else ""),
                            payload={
                                "task_number": draft.task_number,
                                "supplier": draft.supplier,
                                "ruc": draft.ruc,
                                "requester": draft.requester,
                            },
                        )
                    )
                except Exception as exc:
                    diagnostic = page.capture_diagnostic(f"oc_{draft.task_number}", exc)
                    items.append(
                        OperationItem(
                            key=key,
                            status=ItemStatus.FAILED,
                            error_code="error_naf",
                            message=f"{exc}" + (f" Diagnóstico: {diagnostic}" if diagnostic else ""),
                            payload={
                                "task_number": draft.task_number,
                                "supplier": draft.supplier,
                                "ruc": draft.ruc,
                                "requester": draft.requester,
                            },
                        )
                    )
                if save_started and items[-1].status == ItemStatus.FAILED:
                    items.extend(
                        OperationItem(
                            key=pending.operation_key,
                            status=ItemStatus.SKIPPED,
                            message="Lote detenido: revisar el resultado del último Guardar en NAF.",
                        ) for pending in drafts[index:]
                    )
                    return OperationResult.from_items(items, "Guardado no confirmado; revisar NAF antes de continuar. No regenerar.")
                if progress:
                    progress(index, total, f"Procesada OC {index} de {total}: tarea {draft.task_number}")
            return OperationResult.from_items(items, "Precarga de órdenes finalizada.")
        except Exception as exc:
            detail = str(exc).strip()
            pending = [
                OperationItem(
                    key=draft.operation_key,
                    status=ItemStatus.FAILED,
                    error_code="error_naf",
                    message=detail,
                )
                for draft in drafts
            ]
            return OperationResult.from_items(
                pending,
                "No se pudo iniciar la precarga de órdenes."
                + (f" {detail}" if detail else ""),
            )
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except WebDriverException:
                    pass
