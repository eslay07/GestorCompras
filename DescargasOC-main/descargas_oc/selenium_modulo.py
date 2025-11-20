"""Automatizaciones con Selenium para Descargas OC.

Este módulo realiza el proceso completo de autenticación y descarga de órdenes
de compra desde el portal de Telconet. Cada elemento de la interfaz recibe un
nombre legible para facilitar el control de errores y la trazabilidad.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
import re

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

try:  # permite ejecutar como script
    from .config import Config
    from .mover_pdf import mover_oc, normalizar_nombre_archivo
    from .organizador_bienes import organizar as organizar_bienes
    from .pdf_info import actualizar_proveedores_desde_pdfs
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc, normalizar_nombre_archivo
    from organizador_bienes import organizar as organizar_bienes
    from pdf_info import actualizar_proveedores_desde_pdfs


def esperar_descarga_pdf(
    directory: Path,
    existentes: dict[Path, float],
    timeout: float = 60.0,
    intervalo: float = 0.5,
) -> Path:
    """Espera a que aparezca un PDF nuevo o actualizado en ``directory``."""

    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        time.sleep(intervalo)
        candidatos: list[tuple[float, Path]] = []
        for pdf in directory.glob("*.pdf"):
            try:
                mtime = pdf.stat().st_mtime
            except FileNotFoundError:
                continue
            anterior = existentes.get(pdf)
            if anterior is None or mtime > anterior:
                candidatos.append((mtime, pdf))
        if not candidatos:
            continue
        candidatos.sort()
        candidato = candidatos[-1][1]
        crdownload = candidato.with_suffix(candidato.suffix + ".crdownload")
        if crdownload.exists():
            continue
        try:
            size = candidato.stat().st_size
        except FileNotFoundError:
            continue
        time.sleep(min(intervalo / 2, 0.5))
        try:
            if candidato.stat().st_size != size:
                continue
        except FileNotFoundError:
            continue
        return candidato
    raise RuntimeError("No se descargó archivo")


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

    def _renombrar_descarga(archivo: Path, base: str | None) -> Path:
        if not base:
            return archivo
        destino = download_dir / f"{base}.pdf"
        if archivo == destino:
            return archivo
        intento = 0
        while True:
            candidato = destino if intento == 0 else download_dir / f"{base} ({intento}).pdf"
            try:
                archivo.rename(candidato)
                return candidato
            except FileExistsError:
                intento += 1
                continue
            except OSError:
                break
        return archivo

    user_raw = username if username is not None else cfg.usuario
    user = str(user_raw or "").strip()
    if "@" in user:
        user = user.split("@", 1)[0]
    pwd = password if password is not None else cfg.password

    ubicaciones_descarga: dict[str, str] = {}

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
    except Exception:  # pragma: no cover - depende de la implementación de Chrome
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

    def _find(name: str, locator, retries: int = 5, delay: float = 2.0):
        """Busca un elemento realizando varios intentos."""

        def search(loc):
            try:
                elems = driver.find_elements(*loc)
                if elems:
                    return elems[0]
            except Exception:
                return None

        for _ in range(retries):
            for handle in driver.window_handles:
                try:
                    driver.switch_to.window(handle)
                except Exception:
                    continue
                driver.switch_to.default_content()
                elem = search(locator)
                if elem:
                    return elem
                frames = driver.find_elements(By.TAG_NAME, "iframe")
                for frame in frames:
                    try:
                        driver.switch_to.frame(frame)
                        elem = search(locator)
                        if elem:
                            return elem
                    except Exception:
                        pass
                driver.switch_to.default_content()
            time.sleep(delay)
        raise RuntimeError(f"Fallo al localizar '{name}'")

    def _click(name: str, locator):
        for _ in range(3):
            elem = _find(name, locator)
            try:
                elem.click()
                return
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", elem)
                return
            except Exception:
                time.sleep(2)
        raise RuntimeError(f"No se pudo hacer click en '{name}'")

    errores: list[str] = []
    try:
        driver.get(
            "https://cas.telconet.ec/cas/login?service="
            "https://sites.telconet.ec/naf/compras/sso/check"
        )

        time.sleep(2)
        user_el = _find("usuario", elements["usuario"])
        pass_el = _find("contrasena", elements["contrasena"])
        user_el.send_keys(user or "")
        pass_el.send_keys(pwd or "")
        try:
            _click("iniciar_sesion", elements["iniciar_sesion"])
        except RuntimeError:
            # si no se encuentra el botón, intentar enviar Enter o usar submit
            try:
                pass_el = _find("contrasena", elements["contrasena"])
                try:
                    pass_el.send_keys(Keys.RETURN)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                driver.execute_script(
                    "const f=document.querySelector('form'); if(f) f.submit();"
                )
            except Exception:
                pass
        time.sleep(2)
        for _ in range(3):
            try:
                driver.switch_to.window(driver.window_handles[-1])
            except Exception:
                pass
            if driver.find_elements(*elements["lista_accesos"]):
                break
            try:
                menu = driver.find_elements(*elements["menu_hamburguesa"])
                if menu:
                    menu[0].click()
            except Exception:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("Fallo al localizar 'lista_accesos'")
        _click("lista_accesos", elements["lista_accesos"])
        _click("seleccion_compania", elements["seleccion_compania"])
        _find("lista_companias", elements["lista_companias"]).send_keys("TELCONET S.A.")
        _click("telconet_sa", elements["telconet_sa"])
        _click("boton_elegir", elements["boton_elegir"])
        _click("companias_boton_ok", elements["companias_boton_ok"])
        _click("lista_consultas", elements["lista_consultas"])
        _click("consulta_ordenes", elements["consulta_ordenes"])

        for oc in ordenes:
            numero = oc.get("numero")
            proveedor = oc.get("proveedor", "")
            try:
                campo = _find("digitar_oc", elements["digitar_oc"])
                campo.clear()
                campo.send_keys(numero)
                time.sleep(2)
                _click("btnbuscarorden", elements["btnbuscarorden"])

                for _ in range(5):
                    if not driver.find_elements(*elements["toast"]):
                        break
                    time.sleep(2)
                boton_descarga = _find("descargar_orden", elements["descargar_orden"])
                existentes = {
                    pdf: pdf.stat().st_mtime for pdf in download_dir.glob("*.pdf")
                }
                try:
                    boton_descarga.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", boton_descarga)

                archivo = esperar_descarga_pdf(download_dir, existentes)
                if not getattr(cfg, "compra_bienes", False):
                    prov_clean = None
                    if proveedor:
                        prov_clean = re.sub(r"[^\w\- ]", "_", proveedor)
                        prov_clean = re.sub(r"\s+", " ", prov_clean).strip()
                        if not prov_clean:
                            prov_clean = None
                    partes: list[str] = []
                    if numero:
                        partes.append(str(numero))
                    if prov_clean:
                        partes.append(prov_clean)
                    base_nombre = " - ".join(partes) if partes else None
                    archivo = _renombrar_descarga(archivo, base_nombre)
                antes = set(download_dir.glob("*.pdf"))
                for _ in range(120):  # esperar hasta 60 s
                    time.sleep(0.5)
                    nuevos = set(download_dir.glob("*.pdf")) - antes
                    if nuevos:
                        archivo = nuevos.pop()
                        break
                else:
                    raise RuntimeError("No se descargó archivo")
                if not getattr(cfg, "compra_bienes", False) and proveedor:
                    prov_clean = normalizar_nombre_archivo(proveedor)
                    nuevo_nombre = download_dir / f"{numero} - {prov_clean}.pdf"
                    try:
                        archivo.rename(nuevo_nombre)
                        archivo = nuevo_nombre
                    except Exception:
                        prov_clean = normalizar_nombre_archivo(proveedor, longitud_maxima=20)
                        nuevo_nombre = download_dir / f"{numero} - {prov_clean}.pdf"
                        try:
                            archivo.rename(nuevo_nombre)
                            archivo = nuevo_nombre
                        except Exception:
                            pass
            except Exception as exc:  # pragma: no cover - incidencias en ejecución
                errores.append(f"OC {numero}: {exc}")
    finally:
        driver.quit()

    if ordenes:
        actualizar_proveedores_desde_pdfs(ordenes, download_dir)

    numeros = [oc.get("numero") for oc in ordenes]
    subidos, faltantes, errores_mov, ubicaciones_descarga = mover_oc(cfg, ordenes)
    for numero, ruta in ubicaciones_descarga.items():
        for orden in ordenes:
            if str(orden.get("numero")) == str(numero):
                orden["ruta"] = ruta
    if getattr(cfg, "compra_bienes", False):
        organizar_bienes(cfg.carpeta_analizar, cfg.carpeta_analizar)
    errores.extend(errores_mov)
    faltantes = [n for n in faltantes if n not in ubicaciones_descarga]
    return subidos, faltantes, errores


if __name__ == "__main__":  # pragma: no cover
    descargar_oc([])

