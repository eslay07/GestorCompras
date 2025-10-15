"""Descarga de órdenes de compra de Abastecimiento vía Selenium."""
from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import undetected_chromedriver as uc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    TimeoutException,
    StaleElementReferenceException,
)

try:  # permitir la ejecución como script
    from .config import Config
    from .mover_pdf import mover_oc
    from .reporter import enviar_reporte
    from .selenium_modulo import (
    esperar_descarga_pdf,
    handle_sso_after_login,
    simulate_human_activity,
    instalar_ganchos_naf,
    wait_for_network_idle,
)
    from .logger import get_logger
    from .pdf_info import (
        actualizar_proveedores_desde_pdfs,
        limpiar_proveedor,
        nombre_archivo_orden,
        proveedor_desde_pdf,
    )
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
    from .logger import get_logger
#=======
#>>>>>>> master
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc
    from reporter import enviar_reporte
    from selenium_modulo import (
    esperar_descarga_pdf,
    handle_sso_after_login,
    simulate_human_activity,
    instalar_ganchos_naf,
    wait_for_network_idle,
)
    from logger import get_logger
    from pdf_info import (
        actualizar_proveedores_desde_pdfs,
        limpiar_proveedor,
        nombre_archivo_orden,
        proveedor_desde_pdf,
    )
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
    from logger import get_logger


logger = get_logger(__name__)
WAIT_TIMEOUT = 30


AUTOCOMPLETE_LABELS: dict[str, list[str]] = {
    "solicitante": ["solicitante", "solicita", "solicitante:"],
    "autoriza": ["autoriza", "autoriza:", "autoriza por"],
}

ICON_TEXTOS = {
    "keyboard_arrow_down",
    "keyboard_arrow_up",
    "keyboard_arrow_right",
    "keyboard_arrow_left",
    "picture_as_pdf",
    "save_alt",
}

PATRONES_NUMERO = (
    re.compile(r"orden\s*(?:de\s*compra\s*)?#?\s*(\d+)", re.IGNORECASE),
    re.compile(r"oc\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d{5,})"),
)


def _renombrar_pdf_descargado(pdf: Path, numero: str, proveedor: str) -> Path:
    """Renombra el PDF descargado usando número y proveedor."""

    base_actual = re.sub(r"\s+", " ", pdf.stem).strip()
    preferido = base_actual or (numero or "").strip()
    nombre_deseado = nombre_archivo_orden(preferido, proveedor, pdf.suffix or ".pdf")
    destino = pdf.with_name(nombre_deseado)
    if destino == pdf:
        return pdf

    base, ext = os.path.splitext(nombre_deseado)
    if destino.exists():
        i = 1
        while True:
            candidato = pdf.with_name(f"{base} ({i}){ext}")
            if not candidato.exists():
                destino = candidato
                break
            i += 1

    try:
        pdf.rename(destino)
        logger.info("Archivo %s renombrado a %s", pdf.name, destino.name)
        return destino
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning(
            "No se pudo renombrar '%s' a '%s': %s", pdf.name, destino.name, exc
        )
        return pdf


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto para comparaciones flexibles."""

    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_acentos.lower().strip()


def _texto_es_icono(texto: str) -> bool:
    if not texto:
        return False
    normalizado = _normalizar_texto(texto).replace(" ", "_")
    return normalizado in ICON_TEXTOS


def _numero_desde_texto(texto: str) -> str:
    if not texto:
        return ""
    for patron in PATRONES_NUMERO:
        coincidencia = patron.search(texto)
        if coincidencia:
            numero = re.sub(r"\D", "", coincidencia.group(1))
            if numero:
                numero_normalizado = numero.lstrip("0")
                return numero_normalizado or numero
    return ""


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
    """Genera el nombre base del PDF utilizando número y proveedor."""

    numero_limpio = (numero or "").strip()
    proveedor_limpio = re.sub(r"\s+", " ", (proveedor or "").strip())
    proveedor_limpio = re.sub(r"[^\w\- ]", "_", proveedor_limpio).strip()

    partes: list[str] = []
    if numero_limpio:
        partes.append(numero_limpio)
    if proveedor_limpio:
        partes.append(proveedor_limpio)
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


def _extraer_datos_orden(btn, indice: int) -> tuple[str, str]:
    """Obtiene el número y proveedor asociados a un botón de descarga."""

    fila = None
    for xpath in (
        "./ancestor::mat-row[1]",
        "./ancestor::*[@role='row'][1]",
        "./ancestor::tr[1]",
    ):
        try:
            fila = btn.find_element(By.XPATH, xpath)
            if fila is not None:
                break
        except Exception:
            continue

    numero = ""
    proveedor = ""

    textos: list[str] = []
    if fila is not None:
        vistos: set[str] = set()

        def _agregar(texto: str):
            texto = (texto or "").strip()
            if not texto:
                return
            if texto in vistos:
                return
            vistos.add(texto)
            textos.append(texto)

        try:
            fila_texto = fila.text or ""
        except Exception:
            fila_texto = ""
        for parte in fila_texto.splitlines():
            _agregar(parte)

    if fila is not None:
        textos: list[str] = []
        for locator in (".//mat-cell", ".//td"):
            try:
                celdas = fila.find_elements(By.XPATH, locator)
            except Exception:
                continue
            for celda in celdas:
                try:
                    texto = celda.text or ""
                except Exception:
                    texto = ""
                for parte in texto.splitlines():
                    _agregar(parte)

        try:
            spans = fila.find_elements(By.XPATH, ".//span")
        except Exception:
            spans = []
        for span in spans:
            try:
                texto = span.text or ""
            except Exception:
                texto = ""
            for parte in texto.splitlines():
                _agregar(parte)

    numero_texto = ""
    for texto in textos:
        if _texto_es_icono(texto):
            continue
        numero_candidato = _numero_desde_texto(texto)
        if numero_candidato:
            numero = numero_candidato
            numero_texto = texto
            break
        if textos:
            numero = textos[0]
            if len(textos) > 1:
                proveedor = textos[1]

        if not numero or not proveedor:
            try:
                spans = fila.find_elements(By.XPATH, ".//span")
            except Exception:
                spans = []
            span_textos: list[str] = []
            for span in spans:
                try:
                    texto = span.text.strip()
                except Exception:
                    texto = ""
                if texto:
                    span_textos.append(texto)
            if not numero and span_textos:
                numero = span_textos[0]
            if not proveedor and span_textos:
                for texto in span_textos:
                    if texto != numero:
                        proveedor = texto
                        break

    if not numero:
        numero = str(indice + 1)

    for texto in textos:
        if texto == numero_texto:
            continue
        if _texto_es_icono(texto):
            continue
        if _numero_desde_texto(texto) == numero:
            continue
        if not re.search(r"[a-zA-ZÁÉÍÓÚÜÑ]", texto):
            continue
        proveedor = texto
        break

    proveedor = limpiar_proveedor(proveedor)

    return numero, proveedor


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

const esVisible = (el) => {
  if (!el) {
    return false;
  }
  try {
    return el.offsetParent !== null && !el.disabled;
  } catch (e) {
    return false;
  }
};

const contenedores = Array.from(document.querySelectorAll([
  'mat-form-field',
  '.mat-form-field',
  'ng-select',
  '.ng-select',
  '.ng-select-container',
  'div.form-group',
  "div[class*='col']"
].join(',')));

for (const campo of contenedores) {
  if (!esVisible(campo)) {
    continue;
  }
  const texto = normalizar(campo.innerText);
  if (!texto || !texto.includes(needle)) {
    continue;
  }
  const input = campo.querySelector('input[aria-autocomplete="list"]');
  if (esVisible(input)) {
    return input;
  }
}

const inputs = Array.from(document.querySelectorAll('input[aria-autocomplete="list"]'));

const contextoInput = (input) => {
  const partes = [];

  if (input.id) {
    const labelFor = document.querySelector(`label[for='${input.id}']`);
    if (labelFor) {
      partes.push(labelFor.innerText || '');
    }
  }

  let nodo = input.parentElement;
  let profundidad = 0;
  while (nodo && profundidad < 5) {
    const label = nodo.querySelector ? nodo.querySelector('label, .ng-select-label, .mat-form-field-label') : null;
    if (label) {
      partes.push(label.innerText || '');
    }
    if (nodo.previousElementSibling) {
      partes.push(nodo.previousElementSibling.innerText || '');
    }
    nodo = nodo.parentElement;
    profundidad += 1;
  }

  return normalizar(partes.join(' '));
};

for (const input of inputs) {
  if (!esVisible(input)) {
    continue;
  }
  const contexto = contextoInput(input);
  if (contexto && contexto.includes(needle)) {
    return input;
  }
}

return null;
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
#=======
#>>>>>>> master


def descargar_abastecimiento(
    fecha_desde: str,
    fecha_hasta: str,
    solicitante: str,
    autoriza: str,
    username: str | None = None,
    password: str | None = None,
    download_dir: str | None = None,
    headless: bool | None = None,
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

    headless_flag = (
        bool(cfg.abastecimiento_headless)
        if headless is None
        else bool(headless)
    )

    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
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
    if headless_flag:
        options.add_argument("--headless=new")

    driver = uc.Chrome(options=options)
    instalar_ganchos_naf(driver)
    try:
        try:
            driver.execute_cdp_cmd(
                "Page.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": str(destino)},
            )
        except Exception:  # pragma: no cover - depende de Chrome
            pass

        elements = {
            "usuario": (By.CSS_SELECTOR, "input#username"),
            "contrasena": (By.CSS_SELECTOR, "input#password"),
            "iniciar_sesion": (
                By.CSS_SELECTOR,
                "input.btn.btn-block.btn-submit[name='submit']",
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
            ultimo_error: TimeoutException | None = None
            for condicion in (EC.element_to_be_clickable, EC.presence_of_element_located):
                try:
                    condicion_eval = condicion(locator)
                    elemento = WebDriverWait(driver, timeout).until(condicion_eval)
                    if elemento:
                        return elemento
                except TimeoutException as exc:
                    ultimo_error = exc
            logger.error("No se encontró el elemento '%s'", nombre)
            raise RuntimeError(f"No se pudo localizar '{nombre}'") from ultimo_error

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
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", elemento)
            return elemento

        def _hay_toast_visible() -> bool:
            for elemento in driver.find_elements(*elements["toast"]):
                try:
                    if elemento.is_displayed():
                        return True
                except StaleElementReferenceException:
                    continue
            return False

        def esperar_toast():
            try:
                # Esperar a que aparezca un toast (si corresponde)
                WebDriverWait(driver, 3).until(lambda _d: _hay_toast_visible())
            except TimeoutException:
                pass

            try:
                WebDriverWait(driver, 10).until(lambda _d: not _hay_toast_visible())
            except TimeoutException:
                pass

            time.sleep(0.5)

        def _autocompletes_visibles():
            campos = []
            for campo in driver.find_elements(By.CSS_SELECTOR, "input[aria-autocomplete='list']"):
                try:
                    if campo.is_displayed() and campo.is_enabled():
                        campos.append(campo)
                except StaleElementReferenceException:
                    continue
            return campos

        def _obtener_por_indice(indice: int):
            def _resolver(_driver):
                visibles = _autocompletes_visibles()
                if len(visibles) > indice:
                    return visibles[indice]
                return False

            return WebDriverWait(driver, WAIT_TIMEOUT).until(_resolver)

        def obtener_autocomplete(nombre: str, indice: int):
            etiquetas = AUTOCOMPLETE_LABELS.get(nombre, [])
            for etiqueta in etiquetas:
                try:
                    campo = _buscar_autocomplete_por_texto(driver, etiqueta)
                    if campo:
                        return campo, ("label", etiqueta)
                except RuntimeError:
                    continue

            try:
                campo = _obtener_por_indice(indice)
                return campo, ("index", indice)
            except TimeoutException as exc:
                logger.error("%s: no se encontró un campo visible", nombre)
                raise RuntimeError(f"No se pudo localizar '{nombre}'") from exc

        def _es_campo_autocomplete(elemento) -> bool:
            try:
                if elemento.tag_name.lower() != "input":
                    return False
            except Exception:
                return False
            try:
                return (elemento.get_attribute("aria-autocomplete") or "").lower() == "list"
            except Exception:
                return False

        def _enviar_tabs(cantidad: int, espera: float = 0.2):
            for _ in range(max(0, cantidad)):
                try:
                    activo = driver.switch_to.active_element
                except Exception:
                    activo = None
                if activo is not None:
                    try:
                        activo.send_keys(Keys.TAB)
                    except Exception as exc:
                        logger.debug("No se pudo enviar TAB directo: %s", exc)
                        try:
                            driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab'}));", activo)
                            driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key: 'Tab'}));", activo)
                        except Exception:
                            pass
                time.sleep(espera)

        def completar_autocomplete(
            nombre: str,
            indice: int,
            texto: str,
            *,
            usar_activo: bool = False,
            avanzar_tab: bool = True,
        ):
            if not texto:
                logger.warning("%s sin valor configurado; se omite", nombre.capitalize())
                return

            campo = None
            origen_info = ("index", indice)

            if usar_activo:
                try:
                    activo = driver.switch_to.active_element
                except Exception:
                    activo = None
                if activo is not None and _es_campo_autocomplete(activo):
                    campo = activo
                    origen_info = ("active", None)

            if campo is None:
                campo, origen_info = obtener_autocomplete(nombre, indice)

            def refrescar_campo():
                nonlocal campo, origen_info
                try:
                    if campo.is_displayed() and campo.is_enabled():
                        return campo
                except StaleElementReferenceException:
                    pass

                if origen_info[0] == "label":
                    try:
                        nuevo = _buscar_autocomplete_por_texto(driver, origen_info[1])
                        if nuevo:
                            campo = nuevo
                            return campo
                    except RuntimeError:
                        pass

                try:
                    nuevo = _obtener_por_indice(indice)
                    campo = nuevo
                    origen_info = ("index", indice)
                except Exception:
                    pass
                return campo

            campo = refrescar_campo()

            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
            except Exception:
                pass

            campo = refrescar_campo()
            try:
                campo.click()
            except Exception:
                driver.execute_script("arguments[0].focus();", campo)

            campo = refrescar_campo()
            campo.send_keys(Keys.CONTROL, "a")
            campo.send_keys(Keys.DELETE)
            time.sleep(0.1)

            campo = refrescar_campo()
            campo.send_keys(texto)
            time.sleep(2)

            campo = refrescar_campo()
            try:
                campo.send_keys(Keys.ENTER)
            except Exception as exc:
                logger.debug("%s: no se pudo enviar Enter directamente: %s", nombre, exc)

            _esperar_cierre_opciones(driver)
            time.sleep(0.2)

            logger.info("%s ingresado: %s", nombre.capitalize(), texto)

            if avanzar_tab:
                try:
                    campo = refrescar_campo()
                    campo.send_keys(Keys.TAB)
                except StaleElementReferenceException:
                    pass

        driver.get(
            "https://cas.telconet.ec/cas/login?service="
            "https://sites.telconet.ec/naf/compras/sso/check"
        )
        try:
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located(elements["usuario"])
            )
        except TimeoutException as exc:
            logger.error("No se encontró el elemento '%s'", "usuario")
            raise RuntimeError("No se pudo localizar 'usuario'") from exc
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
        handle_sso_after_login(driver, timeout=60.0, idle_timeout=30.0)
        try:
            wait_for_network_idle(driver, timeout=30.0)
        except TimeoutError:
            limite_ready = time.monotonic() + 20
            while time.monotonic() < limite_ready:
                try:
                    if driver.execute_script("return document.readyState") == "complete":
                        break
                except Exception:
                    break
                time.sleep(0.5)
        simulate_human_activity(driver)
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

        simulate_human_activity(driver)
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
        campo_fecha_desde = limpiar_y_escribir(
            "fecha_desde", elements["fecha_desde"], fecha_desde_fmt
        )
        campo_fecha_desde.send_keys(Keys.TAB)

        campo_fecha_hasta = limpiar_y_escribir(
            "fecha_hasta", elements["fecha_hasta"], fecha_hasta_fmt
        )
        campo_fecha_hasta.send_keys(Keys.TAB)
        _enviar_tabs(1)

        completar_autocomplete(
            "solicitante", 0, solicitante, usar_activo=True, avanzar_tab=False
        )
        _enviar_tabs(1)

        completar_autocomplete(
            "autoriza", 1, autoriza, usar_activo=True, avanzar_tab=False
        )

        simulate_human_activity(driver)
        for intento_busqueda in range(3):
            hacer_click("btnbuscarorden", elements["btnbuscarorden"])
            try:
                wait_for_network_idle(driver, timeout=25.0)
                break
            except TimeoutError:
                if intento_busqueda == 2:
                    raise RuntimeError("La búsqueda de órdenes no respondió a tiempo")
                time.sleep(2)
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

                if origen_info[0] == "label":
                    try:
                        nuevo = _buscar_autocomplete_por_texto(driver, origen_info[1])
                        if nuevo:
                            campo = nuevo
                            return campo
                    except RuntimeError:
                        pass

                try:
                    nuevo = _obtener_por_indice(indice)
                    campo = nuevo
                    origen_info = ("index", indice)
                except Exception:
                    pass
                return campo

            campo = refrescar_campo()

            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", campo)
            except Exception:
                pass

            campo = refrescar_campo()
            try:
                campo.click()
            except Exception:
                driver.execute_script("arguments[0].focus();", campo)

            campo = refrescar_campo()
            campo.send_keys(Keys.CONTROL, "a")
            campo.send_keys(Keys.DELETE)
            time.sleep(0.1)

            campo = refrescar_campo()
            campo.send_keys(texto)
            time.sleep(2)

            campo = refrescar_campo()
            try:
                campo.send_keys(Keys.ENTER)
            except Exception as exc:
                logger.debug("%s: no se pudo enviar Enter directamente: %s", nombre, exc)

            _esperar_cierre_opciones(driver)
            time.sleep(0.2)

            logger.info("%s ingresado: %s", nombre.capitalize(), texto)

            if avanzar_tab:
                try:
                    campo = refrescar_campo()
                    campo.send_keys(Keys.TAB)
                except StaleElementReferenceException:
                    pass

        driver.get(
            "https://cas.telconet.ec/cas/login?service="
            "https://sites.telconet.ec/naf/compras/sso/check"
        )
        try:
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located(elements["usuario"])
            )
        except TimeoutException as exc:
            logger.error("No se encontró el elemento '%s'", "usuario")
            raise RuntimeError("No se pudo localizar 'usuario'") from exc
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
        handle_sso_after_login(driver, timeout=60.0, idle_timeout=30.0)
        try:
            wait_for_network_idle(driver, timeout=30.0)
        except TimeoutError:
            limite_ready = time.monotonic() + 20
            while time.monotonic() < limite_ready:
                try:
                    if driver.execute_script("return document.readyState") == "complete":
                        break
                except Exception:
                    break
                time.sleep(0.5)
        simulate_human_activity(driver)
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

        simulate_human_activity(driver)
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
        campo_fecha_desde = limpiar_y_escribir(
            "fecha_desde", elements["fecha_desde"], fecha_desde_fmt
        )
        campo_fecha_desde.send_keys(Keys.TAB)

        campo_fecha_hasta = limpiar_y_escribir(
            "fecha_hasta", elements["fecha_hasta"], fecha_hasta_fmt
        )
        campo_fecha_hasta.send_keys(Keys.TAB)
        _enviar_tabs(1)

        completar_autocomplete(
            "solicitante", 0, solicitante, usar_activo=True, avanzar_tab=False
        )
        _enviar_tabs(1)

        completar_autocomplete(
            "autoriza", 1, autoriza, usar_activo=True, avanzar_tab=False
        )

        simulate_human_activity(driver)
        for intento_busqueda in range(3):
            hacer_click("btnbuscarorden", elements["btnbuscarorden"])
            try:
                wait_for_network_idle(driver, timeout=25.0)
                break
            except TimeoutError:
                if intento_busqueda == 2:
                    raise RuntimeError("La búsqueda de órdenes no respondió a tiempo")
                time.sleep(2)
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
#=======
            row = btn.find_element(By.XPATH, "./ancestor::tr")
            celdas = row.find_elements(By.TAG_NAME, "td")
            numero = celdas[0].text.strip() if celdas else str(idx)
            proveedor = celdas[1].text.strip() if len(celdas) > 1 else ""
        except Exception:
            numero = str(idx)
            proveedor = ""
        existentes = {pdf: pdf.stat().st_mtime for pdf in destino.glob("*.pdf")}
        try:
            btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", btn)
        archivo_descargado = esperar_descarga_pdf(destino, existentes)
        ordenes.append({"numero": numero, "proveedor": proveedor})
        for _ in range(5):
            if not driver.find_elements(*elements["toast"]):
#>>>>>>> master
                break
            btn = botones[idx]
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            except Exception:
                pass
            time.sleep(0.2)
            numero, proveedor = _extraer_datos_orden(btn, idx)

            orden = {
                "numero": numero,
                "proveedor": proveedor,
                "categoria": "abastecimiento",
            }
            ordenes.append(orden)
            ordenes.append(
                {"numero": numero, "proveedor": proveedor, "categoria": "abastecimiento"}
            )
            existentes = {pdf: pdf.stat().st_mtime for pdf in destino.glob("*.pdf")}
            try:
                btn.click()
            except (ElementClickInterceptedException, StaleElementReferenceException):
                driver.execute_script("arguments[0].click();", btn)
            try:
                archivo_descargado = esperar_descarga_pdf(destino, existentes)
                ruta_descargada = Path(archivo_descargado)
                numero_archivo = _numero_desde_texto(ruta_descargada.stem)
                if numero_archivo:
                    orden["numero"] = numero_archivo
                    numero = numero_archivo
                logger.info("OC %s descargada en %s", numero, archivo_descargado)
                proveedor_pdf = proveedor_desde_pdf(archivo_descargado)
                if proveedor_pdf:
                    orden["proveedor"] = proveedor_pdf
                _renombrar_pdf_descargado(
                    ruta_descargada,
                    str(numero),
                    orden.get("proveedor", ""),
                )
                base_nombre = _nombre_archivo(numero, proveedor)
                if base_nombre:
                    archivo_descargado = _renombrar_descarga(archivo_descargado, base_nombre)
                logger.info("OC %s descargada en %s", numero, archivo_descargado)
            except Exception as exc:
                logger.error("No se pudo descargar la OC %s: %s", numero, exc)
            esperar_toast()
            time.sleep(0.5)

        if ordenes:
            actualizar_proveedores_desde_pdfs(ordenes, destino)

        logger.info("Total de órdenes detectadas: %s", len(ordenes))
    finally:
        driver.quit()

    subidos, faltantes, errores_mov = mover_oc(cfg, ordenes)
    for err in errores_mov:
        logger.error("Mover OC: %s", err)
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
    subidos, faltantes, errores_mov = mover_oc(cfg, ordenes)
    for err in errores_mov:
        logger.error("Mover OC: %s", err)
#=======
    subidos, faltantes, _errores_mov = mover_oc(cfg, ordenes)
#>>>>>>> master
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
