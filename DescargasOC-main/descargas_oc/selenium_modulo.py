"""Automatizaciones con Selenium para Descargas OC.

Este módulo realiza el proceso de inicio de sesión y navegación inicial en el
portal de Telconet. Se asignan nombres legibles a los elementos para un mejor
control de errores y trazabilidad.
"""

from selenium import webdriver
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


def descargar_oc(
    numero_oc,
    fecha_aut=None,
    fecha_orden=None,
    username=None,
    password=None,
):
    """Descarga una orden de compra luego de autenticar al usuario.

    Se aceptan credenciales explícitas, de lo contrario se utilizan las
    configuradas en el módulo. Si el nombre de usuario contiene un ``@``, se
    elimina el dominio para compatibilidad con el portal de Telconet.
    """

    cfg = Config()
    download_dir = cfg.carpeta_destino_local

    # Credenciales: priorizar las proporcionadas por la sesión principal
    user = username if username is not None else cfg.usuario
    if user:
        user = user.split("@")[0]
    pwd = password if password is not None else cfg.password

    options = webdriver.ChromeOptions()
    if download_dir:
        prefs = {"download.default_directory": download_dir}
        options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)

    # Mapeo de elementos utilizados y sus selectores
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
    }

    def _find(name, condition, timeout=20):
        try:
            return WebDriverWait(driver, timeout).until(condition)
        except Exception as exc:  # pragma: no cover - interface errors
            raise RuntimeError(f"Fallo al localizar '{name}'") from exc

    try:
        driver.get(
            "https://cas.telconet.ec/cas/login?service="
            "https://sites.telconet.ec/naf/compras/sso/check"
        )

        _find("usuario", EC.presence_of_element_located(elements["usuario"])).send_keys(
            user or ""
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
    finally:
        driver.quit()

    root = Tk()
    root.attributes('-topmost', True)
    root.withdraw()
    messagebox.showinfo(
        "Prueba Selenium",
        "✅ Script automático de Selenium terminó",
    )
    root.destroy()

    return mover_oc(cfg, [numero_oc])

