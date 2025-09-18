"""Descarga de órdenes de compra de Abastecimiento vía Selenium."""
from __future__ import annotations

import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import ElementClickInterceptedException

try:
    from .config import Config
    from .mover_pdf import mover_oc
    from .reporter import enviar_reporte
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc
    from reporter import enviar_reporte


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
    """Automatiza la descarga visible de órdenes de compra por abastecimiento.

    Los parámetros ``fecha_desde`` y ``fecha_hasta`` deben estar en formato
    ``dd/mm/yy``. ``solicitante`` y ``autoriza`` se utilizan para filtrar la
    consulta. Las credenciales y carpeta de descarga se toman de la
    configuración si no se especifican.
    """

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
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
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
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(destino)},
        )
    except Exception:  # pragma: no cover - depends on chrome
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
            "//div[contains(@class,'ng-star-inserted') and contains(.,'TELCONET S.A.')]")
        ,
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

    def _find(name: str, locator, retries: int = 5, delay: float = 2.0):
        for _ in range(retries):
            try:
                elem = driver.find_element(*locator)
                return elem
            except Exception:
                time.sleep(delay)
        raise RuntimeError(f"Fallo al localizar '{name}'")

    def _click(name: str, locator):
        elem = _find(name, locator)
        try:
            elem.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", elem)

    driver.get("https://cas.telconet.ec/cas/login?service=")
    _find("usuario", elements["usuario"]).send_keys(user)
    _find("contrasena", elements["contrasena"]).send_keys(pwd)
    _click("iniciar_sesion", elements["iniciar_sesion"])

    _click("lista_accesos", elements["lista_accesos"])
    _click("seleccion_compania", elements["seleccion_compania"])
    _find("lista_companias", elements["lista_companias"]).send_keys("TELCONET")
    _click("telconet_sa", elements["telconet_sa"])
    _click("boton_elegir", elements["boton_elegir"])
    _click("companias_boton_ok", elements["companias_boton_ok"])
    _click("lista_consultas", elements["lista_consultas"])
    _click("consulta_ordenes", elements["consulta_ordenes"])

    _find("fecha_desde", elements["fecha_desde"]).send_keys(fecha_desde)
    _find("fecha_hasta", elements["fecha_hasta"]).send_keys(fecha_hasta)
    sol = _find("solicitante", elements["solicitante"])
    sol.send_keys(solicitante)
    sol.send_keys(Keys.ENTER)
    aut = _find("autoriza", elements["autoriza"])
    aut.send_keys(autoriza)
    aut.send_keys(Keys.ENTER)

    _click("btnbuscarorden", elements["btnbuscarorden"])
    for _ in range(5):
        if not driver.find_elements(*elements["toast"]):
            break
        time.sleep(2)

    buttons = driver.find_elements(*elements["descargar_orden"])
    ordenes: list[dict[str, str]] = []
    for idx, btn in enumerate(buttons, start=1):
        try:
            row = btn.find_element(By.XPATH, "./ancestor::tr")
            celdas = row.find_elements(By.TAG_NAME, "td")
            numero = celdas[0].text.strip() if celdas else str(idx)
            proveedor = celdas[1].text.strip() if len(celdas) > 1 else ""
        except Exception:
            numero = str(idx)
            proveedor = ""
        try:
            btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", btn)
        antes = set(destino.glob("*.pdf"))
        for _ in range(120):
            time.sleep(0.5)
            nuevos = set(destino.glob("*.pdf")) - antes
            if nuevos:
                break
        ordenes.append({"numero": numero, "proveedor": proveedor})
        for _ in range(5):
            if not driver.find_elements(*elements["toast"]):
                break
            time.sleep(1)

    driver.quit()

    subidos, faltantes, _errores_mov = mover_oc(cfg, ordenes)
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
