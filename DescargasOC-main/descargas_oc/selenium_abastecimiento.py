"""Descarga de órdenes de compra de Abastecimiento vía Selenium."""
from __future__ import annotations

import re
import time
import unicodedata
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


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparaciones flexibles."""

    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower().strip()


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


def _nombre_archivo(numero: str | None, proveedor: str | None) -> str | None:
    """Genera el nombre base del PDF como en el módulo Selenium normal."""

    numero_limpio = (numero or "").strip()
    proveedor_limpio = re.sub(r"\s+", " ", (proveedor or "").strip())
    proveedor_limpio = re.sub(r"[^\w\- ]", "_", proveedor_limpio)
    if proveedor_limpio:
        proveedor_limpio = proveedor_limpio.strip()

    partes: list[str] = []
    if numero_limpio:
        partes.append(numero_limpio)
    if proveedor_limpio:
        partes.append(f"NOMBRE {proveedor_limpio}")
    if not partes:
        return None
    base = " - ".join(partes)
    return base[:180].rstrip(" .-_") or None


def _renombrar_descarga(archivo: Path, base: str | None) -> Path:
    """Renombra la descarga reciente asegurando nombres únicos."""

    if not base:
        return archivo
    base = base.strip()
    if not base:
        return archivo

    destino = archivo.with_name(f"{base}.pdf")
    intento = 0
    while True:
        candidato = destino if intento == 0 else archivo.with_name(f"{base} ({intento}).pdf")
        if archivo == candidato:
            return archivo
        try:
            archivo.rename(candidato)
            return candidato
        except FileExistsError:
            intento += 1
            continue
        except OSError as exc:  # pragma: no cover - entorno Windows
            logger.warning("No se pudo renombrar %s a %s: %s", archivo, candidato, exc)
            return archivo


_SCRIPT_BUSCAR_AUTOCOMPLETE = r"""
const normalizar = (texto) => (texto || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .toLowerCase()
  .replace(/\s+/g, ' ')
  .trim();

const needle = normalizar(arguments[0] || '');
if (!needle) {
  return null;
}

const visibles = [];
const campos = Array.from(document.querySelectorAll('mat-form-field, .mat-form-field'));
for (const campo of campos) {
  const label = normalizar(campo.innerText);
  if (label && label.includes(needle)) {
    const input = campo.querySelector('input[aria-autocomplete="list"]');
    if (input && input.offsetParent !== null && !input.disabled) {
      visibles.push(input);
    }
  }
}

if (!visibles.length) {
  const inputs = Array.from(document.querySelectorAll('input[aria-autocomplete="list"]'));
  for (const input of inputs) {
    if (!input || input.offsetParent === null || input.disabled) {
      continue;
    }
    const attrs = [
      input.getAttribute('placeholder'),
      input.getAttribute('aria-label'),
      input.getAttribute('name'),
      input.id
    ].join(' ');
    if (normalizar(attrs).includes(needle)) {
      visibles.push(input);
    }
  }
}

return visibles.length ? visibles[0] : null;
"""


def _buscar_autocomplete_por_texto(driver, etiqueta: str):
    """Localiza el input de autocompletado usando la etiqueta visible."""

    etiqueta = etiqueta or ""

    def _resolver(drv):
        try:
            elemento = drv.execute_script(_SCRIPT_BUSCAR_AUTOCOMPLETE, etiqueta)
        except Exception:
            return None
        if not elemento:
            return None
        try:
            if elemento.is_displayed() and elemento.is_enabled():
                return elemento
        except StaleElementReferenceException:
            return None
        return None

    try:
        return WebDriverWait(driver, WAIT_TIMEOUT).until(_resolver)
    except TimeoutException as exc:  # pragma: no cover - entorno con cambios de UI
        raise RuntimeError(f"No se pudo localizar '{etiqueta}'") from exc


def _extraer_variantes(texto: str) -> list[str]:
    if not texto:
        return []
    variantes = [
        parte.strip()
        for parte in re.split(r"[;|,\n]+", texto)
        if parte.strip()
    ]
    if not variantes:
        variantes = [texto.strip()]
    return variantes


def _construir_consultas(variantes: list[str], original: str) -> list[str]:
    consultas: list[str] = []
    for variante in variantes:
        match = re.search(r"\d+", variante)
        if match:
            consultas.append(match.group(0))
    consultas.extend(variantes)
    if original:
        consultas.append(original)
    vistas: set[str] = set()
    ordenadas: list[str] = []
    for consulta in consultas:
        limpia = consulta.strip()
        if limpia and limpia not in vistas:
            vistas.add(limpia)
            ordenadas.append(limpia)
    return ordenadas


def _esperar_opciones_visibles(driver, timeout: int = 5) -> list:
    opciones_locator = (By.CSS_SELECTOR, "mat-option")

    try:
        return WebDriverWait(driver, timeout).until(
            lambda d: [
                opcion
                for opcion in d.find_elements(*opciones_locator)
                if opcion.is_displayed()
            ]
        )
    except TimeoutException:
        return []


def _esperar_cierre_opciones(driver, timeout: int = 5):
    opciones_locator = (By.CSS_SELECTOR, "mat-option")

    try:
        WebDriverWait(driver, timeout).until(
            lambda d: not any(
                opcion.is_displayed() for opcion in d.find_elements(*opciones_locator)
            )
        )
    except TimeoutException:
        pass


def _seleccionar_opcion_visible(opciones, variantes: list[str]) -> bool:
    if not opciones:
        return False

    variantes_norm = [_normalizar_texto(variante) for variante in variantes if variante]

    for variante_norm in variantes_norm:
        if not variante_norm:
            continue
        for opcion in list(opciones):
            try:
                texto_opcion = opcion.text
            except StaleElementReferenceException:
                continue
            if _normalizar_texto(texto_opcion).find(variante_norm) != -1:
                opcion.click()
                return True
    return False


def _valor_coincide(valor: str, variantes: list[str], consultas: list[str]) -> bool:
    valor_norm = _normalizar_texto(valor)
    if not valor_norm:
        return False

    for variante in variantes:
        variante_norm = _normalizar_texto(variante)
        if variante_norm and variante_norm in valor_norm:
            return True

    for consulta in consultas:
        consulta_norm = _normalizar_texto(consulta)
        if consulta_norm and consulta_norm in valor_norm:
            return True

    valor_digitos = re.sub(r"\D", "", valor_norm)
    if valor_digitos:
        for consulta in consultas:
            consulta_digitos = re.sub(r"\D", "", _normalizar_texto(consulta))
            if consulta_digitos and valor_digitos.startswith(consulta_digitos):
                return True

    return False


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
            "menu_hamburguesa": (By.CSS_SELECTOR, "button.simple-sidenav__toggle"),
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

        def seleccionar_autocomplete(nombre: str, etiqueta: str | tuple[str, ...], texto: str):
            if not texto:
                return

            variantes = _extraer_variantes(texto)
            consultas = _construir_consultas(variantes, texto)
            if not consultas:
                consultas = variantes or [texto]

            for consulta in consultas:
                for intento in range(3):
                    etiquetas_busqueda = (
                        (etiqueta,) if isinstance(etiqueta, str) else etiqueta
                    )
                    campo = None
                    ultima_exc: RuntimeError | None = None
                    for etiqueta_actual in etiquetas_busqueda:
                        try:
                            campo = _buscar_autocomplete_por_texto(
                                driver, etiqueta_actual
                            )
                            if campo:
                                break
                        except RuntimeError as exc:
                            ultima_exc = exc

                    if campo is None:
                        if ultima_exc is not None:
                            logger.error("%s: %s", nombre, ultima_exc)
                        else:
                            logger.error(
                                "%s: no se encontró un campo visible para %s",
                                nombre,
                                etiqueta,
                            )
                        return

                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block: 'center'});", campo
                        )
                    except Exception:
                        pass

                    try:
                        WebDriverWait(driver, 5).until(
                            lambda d: campo.is_displayed() and campo.is_enabled()
                        )
                    except StaleElementReferenceException:
                        time.sleep(0.2)
                        continue

                    try:
                        campo.click()
                    except Exception:
                        driver.execute_script("arguments[0].focus();", campo)

                    campo.send_keys(Keys.CONTROL, "a")
                    campo.send_keys(Keys.DELETE)
                    time.sleep(0.1)

                    if consulta:
                        campo.send_keys(consulta)
                    else:
                        campo.send_keys(Keys.ARROW_DOWN)

                    time.sleep(0.2)
                    opciones = _esperar_opciones_visibles(driver)

                    if opciones:
                        if not _seleccionar_opcion_visible(opciones, variantes):
                            try:
                                opciones[0].click()
                            except Exception:
                                campo.send_keys(Keys.ENTER)
                        _esperar_cierre_opciones(driver)
                    else:
                        campo.send_keys(Keys.ENTER)

                    time.sleep(0.2)
                    try:
                        valor_final = (campo.get_attribute("value") or "").strip()
                    except StaleElementReferenceException:
                        time.sleep(0.2)
                        continue

                    if _valor_coincide(valor_final, variantes, consultas):
                        campo.send_keys(Keys.TAB)
                        time.sleep(0.1)
                        return

                    # Intentar una vez más con la misma consulta si el elemento se volvió inestable
                    if intento < 2:
                        time.sleep(0.2)
                        continue
                # probar con la siguiente consulta disponible

            logger.warning(
                "%s: no se pudo confirmar la selección para '%s'", nombre, texto
            )

        driver.get(
            "https://cas.telconet.ec/cas/login?service="
            "https://sites.telconet.ec/naf/compras/sso/check"
        )
        limpiar_y_escribir("usuario", elements["usuario"], user)
        limpiar_y_escribir("contrasena", elements["contrasena"], pwd)
        try:
            hacer_click("iniciar_sesion", elements["iniciar_sesion"])
        except RuntimeError:
            try:
                campo_pwd = esperar_clickable("contrasena", elements["contrasena"])
                campo_pwd.send_keys(Keys.RETURN)
            except RuntimeError:
                try:
                    driver.execute_script(
                        "const f=document.querySelector('form'); if(f) f.submit();"
                    )
                except Exception:
                    raise

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
            raise RuntimeError("No se pudo localizar 'lista_accesos'")

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

        seleccionar_autocomplete(
            "solicitante",
            ("solicitante", "solicita", "solicitante:"),
            solicitante,
        )
        seleccionar_autocomplete(
            "autoriza",
            ("autoriza", "autoriza:", "autoriza por", "autoriza por:"),
            autoriza,
        )

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
                base_nombre = _nombre_archivo(numero, proveedor)
                if base_nombre:
                    archivo_descargado = _renombrar_descarga(archivo_descargado, base_nombre)
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
