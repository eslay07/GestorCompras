"""Automatizaciones con Selenium para Descargas OC.

Este módulo realiza el proceso completo de autenticación y descarga de órdenes
de compra desde el portal de Telconet. Cada elemento de la interfaz recibe un
nombre legible para facilitar el control de errores y la trazabilidad.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:  # allow running as script
    from .config import Config
    from .mover_pdf import mover_oc
    from .organizador_bienes import organizar as organizar_bienes
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc
    from organizador_bienes import organizar as organizar_bienes


def descargar_oc(
    ordenes,
    username: str | None = None,
    password: str | None = None,
    headless: bool = False,
):
    """Descarga una o varias órdenes de compra.

    ``ordenes`` es una lista de diccionarios con las claves ``numero`` y
    ``proveedor``. El proceso inicia sesión una sola vez y repite la búsqueda y
    descarga para cada OC encontrada en el correo.
    """

    if isinstance(ordenes, dict):
        ordenes = [ordenes]

    # Asegurar sincronización de SeaDrive antes de iniciar Selenium
    script = Path(__file__).resolve().parents[1] / "scripts" / "seadrive_autoresync.py"
    if script.exists():  # pragma: no cover - depende del entorno Windows
        try:
            subprocess.run([sys.executable, str(script)], check=False)
        except Exception:
            pass

    cfg = Config()
    download_dir = Path(cfg.carpeta_destino_local or Path.home() / "Documentos")
    download_dir.mkdir(parents=True, exist_ok=True)

    user = username if username is not None else cfg.usuario
    if user:
        user = user.split("@")[0]
    pwd = password if password is not None else cfg.password

    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)
    options.add_experimental_option(
        "excludeSwitches", ["enable-automation", "enable-logging"]
    )
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    driver = webdriver.Chrome(options=options)
    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": str(download_dir)},
        )
    except Exception:  # pragma: no cover - depends on Chrome implementation
        pass

    elements = {
        "usuario": (By.ID, "username"),
        "contrasena": (By.ID, "password"),
        "iniciar_sesion": (
            By.CSS_SELECTOR,
            "input.btn.btn-block.btn-submit[name='submit']",
        ),
        "lista_accesos": (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and contains(text(),'Accesos')]",
        ),
        "seleccion_compania": (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and contains(text(),'Selección de Compañía')]",
        ),
        "lista_companias": (By.CSS_SELECTOR, "input[aria-autocomplete='list']"),
        "telconet_sa": (
            By.XPATH,
            "//div[contains(@class,'ng-star-inserted') and contains(.,'TELCONET S.A.')]",
        ),
        "boton_elegir": (By.XPATH, "//span[contains(text(),'Elegir')]"),
        "companias_boton_ok": (
            By.CSS_SELECTOR,
            "button.swal2-confirm.swal2-styled",
        ),
        "lista_consultas": (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and contains(text(),'Consultas')]",
        ),
        "consulta_ordenes": (
            By.XPATH,
            "//span[contains(@class,'simple-sidenav__text') and contains(text(),'Consulta de Órdenes de Compra')]",
        ),
        "digitar_oc": (
            By.CSS_SELECTOR,
            "input[data-placeholder='Digite el número de la O/C']",
        ),
        "btnbuscarorden": (
            By.XPATH,
            "//button[.//span[contains(text(),'Aplicar filtros')]]",
        ),
        "descargar_orden": (
            By.XPATH,
            "//mat-icon[normalize-space()='save_alt']",
        ),
        "toast": (By.CSS_SELECTOR, "div.toast-container"),
        "menu_hamburguesa": (By.CSS_SELECTOR, "button.simple-sidenav__toggle"),
    }

    def _handle_overlays():
        """Cierra posibles ventanas emergentes y vuelve al contexto principal."""
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        for sel in [
            (By.CSS_SELECTOR, "button.swal2-confirm"),
            (By.CSS_SELECTOR, "button.swal2-cancel"),
        ]:
            try:
                driver.find_element(*sel).click()
                time.sleep(1)
            except Exception:
                continue

    def _find(name: str, condition, timeout: int = 40, retries: int = 5):
        """Ubica un elemento esperando a que sea válido.

        Se recorre el documento principal y cualquier iframe visible antes de
        desistir. Entre cada intento se deja un respiro de 2 segundos.
        """
        for intento in range(retries):
            _handle_overlays()
            contexts = [None]
            try:
                contexts += driver.find_elements(By.TAG_NAME, "iframe")
            except Exception:  # pragma: no cover - iframes not accessible
                pass
            for ctx in contexts:
                if ctx is not None:
                    driver.switch_to.frame(ctx)
                try:
                    return WebDriverWait(driver, timeout).until(condition)
                except Exception:  # pragma: no cover - transient UI errors
                    if ctx is not None:
                        driver.switch_to.default_content()
                    continue
            if intento == retries - 1:
                raise RuntimeError(f"Fallo al localizar '{name}'")
            time.sleep(2)

    def _click(name: str, locator, timeout: int = 40, retries: int = 5):
        """Encuentra un elemento y hace clic con reintentos."""
        for intento in range(retries):
            try:
                elem = _find(name, EC.element_to_be_clickable(locator), timeout)
                try:
                    elem.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", elem)
                return elem
            except Exception as exc:
                if intento == retries - 1:
                    raise RuntimeError(f"Fallo al hacer clic '{name}'") from exc
                time.sleep(2)

    errores: list[str] = []
    try:
        driver.get(
            "https://cas.telconet.ec/cas/login?service="
            "https://sites.telconet.ec/naf/compras/sso/check"
        )

        _find("usuario", EC.presence_of_element_located(elements["usuario"])).send_keys(
            user or "",
        )
        _find(
            "contrasena", EC.presence_of_element_located(elements["contrasena"])
        ).send_keys(pwd or "")
        _click("iniciar_sesion", elements["iniciar_sesion"])
        WebDriverWait(driver, 60).until(EC.url_contains("/naf/compras"))
        WebDriverWait(driver, 60).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        # Abrir menú lateral si no está visible (modo móvil)
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(elements["lista_accesos"])
            )
        except TimeoutException:
            try:
                _click(
                    "menu_hamburguesa", elements["menu_hamburguesa"], timeout=10
                )
                time.sleep(1)
            except Exception:
                pass
        _click("lista_accesos", elements["lista_accesos"])
        _click("seleccion_compania", elements["seleccion_compania"])
        _find(
            "lista_companias", EC.presence_of_element_located(elements["lista_companias"])
        ).send_keys("TELCONET S.A.")
        _click("telconet_sa", elements["telconet_sa"])
        _click("boton_elegir", elements["boton_elegir"])
        _click("companias_boton_ok", elements["companias_boton_ok"])
        _click("lista_consultas", elements["lista_consultas"])
        _click("consulta_ordenes", elements["consulta_ordenes"])

        for oc in ordenes:
            numero = oc.get("numero")
            proveedor = oc.get("proveedor", "")
            try:
                campo = _find(
                    "digitar_oc", EC.presence_of_element_located(elements["digitar_oc"])
                )
                campo.clear()
                campo.send_keys(numero)
                time.sleep(3)
                _click("btnbuscarorden", elements["btnbuscarorden"])

                # Esperar a que desaparezca cualquier notificación tipo toast
                try:  # pragma: no cover - depende del front-end
                    WebDriverWait(driver, 10).until(
                        EC.invisibility_of_element_located(elements["toast"])
                    )
                except TimeoutException:
                    pass
                _find(
                    "descargar_orden",
                    EC.presence_of_element_located(elements["descargar_orden"]),
                    timeout=60,
                )
                _click("descargar_orden", elements["descargar_orden"], timeout=60)

                antes = set(download_dir.glob("*.pdf"))
                for _ in range(120):  # esperar hasta 60 s
                    time.sleep(0.5)
                    nuevos = set(download_dir.glob("*.pdf")) - antes
                    if nuevos:
                        archivo = nuevos.pop()
                        break
                else:
                    raise RuntimeError("No se descargó archivo")

                if proveedor:
                    prov_clean = re.sub(r"[^\w\- ]", "_", proveedor)
                    nuevo_nombre = download_dir / f"{numero} - {prov_clean}.pdf"
                    archivo.rename(nuevo_nombre)
            except Exception as exc:  # pragma: no cover - runtime issues
                errores.append(f"OC {numero}: {exc}")
    finally:
        driver.quit()

    numeros = [oc.get("numero") for oc in ordenes]
    subidos, faltantes = mover_oc(cfg, ordenes)
    if getattr(cfg, "compra_bienes", False):
        organizar_bienes(cfg.carpeta_analizar, cfg.carpeta_analizar)
    faltantes.extend(n for n in numeros if any(n in e for e in errores))
    # evitar números repetidos al reportar faltantes
    faltantes = list(dict.fromkeys(faltantes))
    return subidos, faltantes, errores


if __name__ == "__main__":  # pragma: no cover
    descargar_oc([])

