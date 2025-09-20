"""Descarga de órdenes de compra de Abastecimiento vía Selenium."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    StaleElementReferenceException,
)

try:  # permitir la ejecución como script
    from .config import Config
    from .mover_pdf import mover_oc
    from .reporter import enviar_reporte
    from .selenium_modulo import esperar_descarga_pdf
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc
    from reporter import enviar_reporte
    from selenium_modulo import esperar_descarga_pdf
    from logger import get_logger


logger = get_logger(__name__)
WAIT_TIMEOUT = 30


def _normalizar_fecha(valor: str) -> str:
    if not valor:
        return ""
    texto = valor.strip()
    for formato in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            fecha = datetime.strptime(texto, formato)
            return fecha.strftime("%d/%m/%Y")
        except ValueError:
            continue
    return texto


def descargar_abastecimiento(
    fecha_desde: str,
    fecha_hasta: str,
    solicitante: str,
    autoriza: str,
    username: str | None = None,
    password: str | None = None,
    download_dir: str | None = None,
    headless: bool = False,
):
    """Automatiza la descarga visible de órdenes de compra por abastecimiento."""

    cfg = Config()
    user = username if username is not None else cfg.usuario
    if user:
        user = user.split("@")[0]
    pwd = password if password is not None else cfg.password
    destino = Path(
        download_dir
        or cfg.abastecimiento_carpeta_descarga
        or cfg.carpeta_destino_local
        or Path.home()
    )
    destino.mkdir(parents=True, exist_ok=True)

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": str(destino),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    try:
        try:
            driver.execute_cdp_cmd(
                "Page.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": str(destino)},
            )
        except Exception:  # pragma: no cover - depende de Chrome
            pass

        elements = {
            "usuario": (By.ID, "username"),
            "contrasena": (By.ID, "password"),
            "iniciar_sesion": (
                By.CSS_SELECTOR,
                "button[type='submit'], input[type='submit']",
            ),
            "lista_accesos": (
                By.XPATH,
                "//span[contains(@class,'simple-sidenav__text') and text()='Accesos']",
            ),
            "seleccion_compania": (
                By.XPATH,
                "//span[contains(@class,'simple-sidenav__text') and text()='Selección de Compañía']",
            ),
            "lista_companias": (By.CSS_SELECTOR, "input[aria-autocomplete='list']"),
            "telconet_sa": (
                By.XPATH,
                "//div[contains(@class,'ng-star-inserted') and contains(.,'TELCONET S.A.')]",
            ),
            "boton_elegir": (By.XPATH, "//span[text()='Elegir']"),
            "companias_boton_ok": (
                By.CSS_SELECTOR,
                "button.swal2-confirm.swal2-styled",
            ),
            "lista_consultas": (
                By.XPATH,
                "//span[contains(@class,'simple-sidenav__text') and text()='Consultas']",
            ),
            "consulta_ordenes": (
                By.XPATH,
                "//span[contains(@class,'simple-sidenav__text') and text()='Consulta de Órdenes de Compra']",
            ),
            "fecha_desde": (By.ID, "mat-input-2"),
            "fecha_hasta": (By.ID, "mat-input-3"),
            "solicitante": (
                By.XPATH,
                "(//input[@aria-autocomplete='list'])[1]",
            ),
            "autoriza": (
                By.XPATH,
                "(//input[@aria-autocomplete='list'])[2]",
            ),
            "btnbuscarorden": (
                By.XPATH,
                "//button[.//span[text()='Aplicar filtros']]",
            ),
            "descargar_orden": (
                By.XPATH,
                "//mat-icon[normalize-space()='save_alt']",
            ),
            "toast": (By.CSS_SELECTOR, "div.toast-container"),
        }

        def esperar_clickable(nombre: str, locator, timeout: int = WAIT_TIMEOUT):
            try:
                return WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable(locator)
                )
            except TimeoutException as exc:
                logger.error("No se encontró el elemento '%s'", nombre)
                raise RuntimeError(f"No se pudo localizar '{nombre}'") from exc

        def limpiar_y_escribir(nombre: str, locator, texto: str):
            elemento = esperar_clickable(nombre, locator)
            elemento.click()
            elemento.send_keys(Keys.CONTROL, "a")
            elemento.send_keys(Keys.DELETE)
            if texto:
                elemento.send_keys(texto)
            return elemento

        def hacer_click(nombre: str, locator):
            elemento = esperar_clickable(nombre, locator)
            try:
                elemento.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", elemento)
            return elemento

        def esperar_toast():
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: not d.find_elements(*elements["toast"])
                )
            except TimeoutException:
                pass

        driver.get("https://cas.telconet.ec/cas/login?service=")
        limpiar_y_escribir("usuario", elements["usuario"], user)
        limpiar_y_escribir("contrasena", elements["contrasena"], pwd)
        hacer_click("iniciar_sesion", elements["iniciar_sesion"])

        hacer_click("lista_accesos", elements["lista_accesos"])
        hacer_click("seleccion_compania", elements["seleccion_compania"])
        limpiar_y_escribir("lista_companias", elements["lista_companias"], "TELCONET")
        hacer_click("telconet_sa", elements["telconet_sa"])
        hacer_click("boton_elegir", elements["boton_elegir"])
        hacer_click("companias_boton_ok", elements["companias_boton_ok"])
        hacer_click("lista_consultas", elements["lista_consultas"])
        hacer_click("consulta_ordenes", elements["consulta_ordenes"])

        fecha_desde_fmt = _normalizar_fecha(fecha_desde)
        fecha_hasta_fmt = _normalizar_fecha(fecha_hasta)
        limpiar_y_escribir("fecha_desde", elements["fecha_desde"], fecha_desde_fmt).send_keys(
            Keys.TAB
        )
        limpiar_y_escribir("fecha_hasta", elements["fecha_hasta"], fecha_hasta_fmt).send_keys(
            Keys.TAB
        )

        if solicitante:
            sol_input = limpiar_y_escribir(
                "solicitante", elements["solicitante"], solicitante
            )
            time.sleep(0.5)
            sol_input.send_keys(Keys.ENTER)

        if autoriza:
            aut_input = limpiar_y_escribir("autoriza", elements["autoriza"], autoriza)
            time.sleep(0.5)
            aut_input.send_keys(Keys.ENTER)

        hacer_click("btnbuscarorden", elements["btnbuscarorden"])
        esperar_toast()

        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.find_elements(*elements["descargar_orden"]) or not d.find_elements(*elements["toast"])
            )
        except TimeoutException:
            logger.info("No se encontraron órdenes para los filtros proporcionados.")
            total_botones = 0
        else:
            total_botones = len(driver.find_elements(*elements["descargar_orden"]))

        ordenes: list[dict[str, str]] = []
        for idx in range(total_botones):
            botones = driver.find_elements(*elements["descargar_orden"])
            if idx >= len(botones):
                break
            btn = botones[idx]
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            except Exception:
                pass
            time.sleep(0.2)
            try:
                fila = btn.find_element(By.XPATH, "./ancestor::tr")
                celdas = fila.find_elements(By.TAG_NAME, "td")
                numero = celdas[0].text.strip() if celdas else str(idx + 1)
                proveedor = celdas[1].text.strip() if len(celdas) > 1 else ""
            except Exception:
                numero = str(idx + 1)
                proveedor = ""

            ordenes.append({"numero": numero, "proveedor": proveedor})
            existentes = {pdf: pdf.stat().st_mtime for pdf in destino.glob("*.pdf")}
            try:
                btn.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                driver.execute_script("arguments[0].click();", btn)
            try:
                archivo_descargado = esperar_descarga_pdf(destino, existentes)
                logger.info("OC %s descargada en %s", numero, archivo_descargado)
            except Exception as exc:
                logger.error("No se pudo descargar la OC %s: %s", numero, exc)
            esperar_toast()

        logger.info("Total de órdenes detectadas: %s", len(ordenes))
    finally:
        driver.quit()

    subidos, faltantes, errores_mov = mover_oc(cfg, ordenes)
    for err in errores_mov:
        logger.error("Mover OC: %s", err)
    enviar_reporte(
        subidos,
        faltantes,
        ordenes,
        cfg,
        categoria="abastecimiento",
        destinatario=cfg.abastecimiento_correo_reporte,
    )
    return subidos, faltantes


if __name__ == "__main__":  # pragma: no cover
    descargar_abastecimiento("01/01/24", "02/01/24", "", "")
