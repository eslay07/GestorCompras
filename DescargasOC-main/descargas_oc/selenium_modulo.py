"""Automatizaciones con Selenium para Descargas OC.

Este módulo realiza el proceso completo de autenticación y descarga de órdenes
de compra desde el portal de Telconet. Cada elemento de la interfaz recibe un
nombre legible para facilitar el control de errores y la trazabilidad.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from tkinter import Tk, messagebox

try:  # allow running as script
    from .config import Config
    from .mover_pdf import mover_oc
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc


def descargar_oc(ordenes, username: str | None = None, password: str | None = None):
    """Descarga una o varias órdenes de compra.

    ``ordenes`` es una lista de diccionarios con las claves ``numero`` y
    ``proveedor``. El proceso inicia sesión una sola vez y repite la búsqueda y
    descarga para cada OC encontrada en el correo.
    """

    if isinstance(ordenes, dict):
        ordenes = [ordenes]

    cfg = Config()
    download_dir = Path.home() / "Documentos"
    download_dir.mkdir(parents=True, exist_ok=True)
    cfg.data["carpeta_destino_local"] = str(download_dir)
    cfg.data["carpeta_analizar"] = str(download_dir)

    user = username if username is not None else cfg.usuario
    if user:
        user = user.split("@")[0]
    pwd = password if password is not None else cfg.password

    options = webdriver.ChromeOptions()
    prefs = {"download.default_directory": str(download_dir)}
    options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)

    elements = {
        "usuario": (By.ID, "username"),
        "contrasena": (By.ID, "password"),
        "iniciar_sesion": (
            By.CSS_SELECTOR,
            "input.btn.btn-block.btn-submit[name='submit']",
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
        "digitar_oc": (
            By.CSS_SELECTOR,
            "input[data-placeholder='Digite el número de la O/C']",
        ),
        "btnbuscarorden": (
            By.XPATH,
            "//button[.//span[text()='Aplicar filtros']]"
            time.sleep(3),
        ),
        "descargar_orden": (
            By.XPATH,
            "//mat-icon[normalize-space()='save_alt']",
        ),
        "toast": (By.CSS_SELECTOR, "div.toast-container"),
    }

    def _notify(title: str, msg: str, kind: str = "error") -> None:
        root = Tk()
        root.attributes("-topmost", True)
        root.withdraw()
        getattr(messagebox, f"show{kind}")(title, msg)
        root.destroy()

    def _find(name: str, condition, timeout: int = 40):
        try:
            return WebDriverWait(driver, timeout).until(condition)
        except Exception as exc:  # pragma: no cover - interface errors
            _notify("Error Selenium", f"Fallo al localizar '{name}'")
            raise RuntimeError(f"Fallo al localizar '{name}'") from exc

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
        _find(
            "iniciar_sesion",
            EC.element_to_be_clickable(elements["iniciar_sesion"]),
        ).click()

        _find(
            "lista_accesos", EC.element_to_be_clickable(elements["lista_accesos"])
        ).click()
        _find(
            "seleccion_compania",
            EC.element_to_be_clickable(elements["seleccion_compania"]),
        ).click()
        _find(
            "lista_companias", EC.presence_of_element_located(elements["lista_companias"])
        ).send_keys("TELCONET S.A.")
        _find("telconet_sa", EC.element_to_be_clickable(elements["telconet_sa"])).click()
        _find("boton_elegir", EC.element_to_be_clickable(elements["boton_elegir"])).click()
        _find(
            "companias_boton_ok",
            EC.element_to_be_clickable(elements["companias_boton_ok"]),
        ).click()
        _find(
            "lista_consultas", EC.element_to_be_clickable(elements["lista_consultas"])
        ).click()
        _find(
            "consulta_ordenes", EC.element_to_be_clickable(elements["consulta_ordenes"])
        ).click()

        for oc in ordenes:
            numero = oc.get("numero")
            proveedor = oc.get("proveedor", "")
            try:
                campo = _find(
                    "digitar_oc", EC.presence_of_element_located(elements["digitar_oc"])
                )
                campo.clear()
                campo.send_keys(numero)
                _find(
                    "btnbuscarorden",
                    EC.element_to_be_clickable(elements["btnbuscarorden"]),
                ).click()

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
                boton_descarga = _find(
                    "descargar_orden",
                    EC.element_to_be_clickable(elements["descargar_orden"]),
                    timeout=60,
                )
                try:
                    boton_descarga.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", boton_descarga)

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
                _notify("Error OC", f"OC {numero}: {exc}")
    finally:
        driver.quit()

    if errores:
        _notify("Descarga incompleta", "\n".join(errores))
    else:
        _notify(
            "Prueba Selenium",
            "✅ Script automático de Selenium terminó",
            kind="info",
        )

    numeros = [oc.get("numero") for oc in ordenes]
    subidos, faltantes = mover_oc(cfg, numeros)
    faltantes.extend(n for n in numeros if any(n in e for e in errores))
    return subidos, faltantes


if __name__ == "__main__":  # pragma: no cover
    descargar_oc([])

