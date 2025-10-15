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

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

try:  # allow running as script
    from .seafile_client import SeafileClient
except ImportError:  # pragma: no cover
    from seafile_client import SeafileClient

try:  # allow running as script
    from .config import Config
    from .mover_pdf import mover_oc, sanitize_filename
    from .organizador_bienes import organizar as organizar_bienes
    from .pdf_info import actualizar_proveedores_desde_pdfs
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc, sanitize_filename
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




# --- parche naf anti-automatizacion ---
def instalar_ganchos_naf(driver) -> None:
    'Instala ajustes anti detección antes de cada navegación.'
    if driver is None:
        return
    if getattr(driver, "_naf_stealth", False):
        return
    script = '''
        (() => {
            if (window.__nafStealthInstalled) {
                return;
            }
            window.__nafStealthInstalled = true;

            const patchProperty = (object, property, value) => {
                try {
                    Object.defineProperty(object, property, {
                        get: () => value,
                        configurable: true,
                    });
                } catch (err) {}
            };

            patchProperty(navigator, 'webdriver', undefined);

            try {
                const ua = navigator.userAgent
                    .replace(/HeadlessChrome\//gi, 'Chrome/')
                    .replace(/\(Headless\)/gi, '')
                    .replace(/Chrome\/\d+/i, (match) => match.replace(/\d+/, '122'));
                patchProperty(navigator, 'userAgent', ua);
                patchProperty(navigator, 'appVersion', ua);
            } catch (err) {}

            patchProperty(navigator, 'vendor', 'Google Inc.');
            patchProperty(navigator, 'platform', 'Win32');
            patchProperty(navigator, 'languages', ['es-EC', 'es', 'en-US']);
            patchProperty(navigator, 'maxTouchPoints', 1);
            patchProperty(navigator, 'hardwareConcurrency', 8);
            patchProperty(navigator, 'deviceMemory', 8);

            try {
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [{ name: 'PDF Viewer' }, { name: 'Chrome PDF Plugin' }],
                    configurable: true,
                });
            } catch (err) {}

            if (!window.chrome) {
                window.chrome = { runtime: {} };
            } else if (!window.chrome.runtime) {
                window.chrome.runtime = {};
            }

            try {
                if (navigator.permissions && navigator.permissions.query) {
                    const originalQuery = navigator.permissions.query.bind(navigator.permissions);
                    navigator.permissions.query = (parameters) => {
                        if (parameters && parameters.name === 'notifications') {
                            const permission = (typeof Notification !== 'undefined' && Notification.permission) || 'default';
                            return Promise.resolve({ state: permission });
                        }
                        return originalQuery(parameters);
                    };
                }
            } catch (err) {}

            try {
                if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
                    const originalHighEntropy = navigator.userAgentData.getHighEntropyValues.bind(navigator.userAgentData);
                    navigator.userAgentData.getHighEntropyValues = (hints) => originalHighEntropy(hints).then((values) => ({
                        ...values,
                        platform: 'Windows',
                        architecture: 'x86',
                        bitness: '64',
                        model: '',
                    }));
                } else if (!navigator.userAgentData) {
                    const data = {
                        brands: [
                            { brand: 'Chromium', version: '122' },
                            { brand: 'Google Chrome', version: '122' },
                            { brand: 'Not A(Brand)', version: '24' },
                        ],
                        mobile: false,
                        platform: 'Windows',
                        getHighEntropyValues: () => Promise.resolve({
                            platform: 'Windows',
                            architecture: 'x86',
                            bitness: '64',
                            model: '',
                            uaFullVersion: '122.0.6261.111',
                        }),
                    };
                    patchProperty(navigator, 'userAgentData', data);
                }
            } catch (err) {}

            try {
                const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
                if (connection) {
                    const clone = Object.assign({}, connection, { downlink: 10, effectiveType: '4g', rtt: 50 });
                    patchProperty(navigator, 'connection', clone);
                }
            } catch (err) {}

            try {
                const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function (parameter) {
                    if (parameter === 37445) {
                        return 'Intel Open Source Technology Center';
                    }
                    if (parameter === 37446) {
                        return 'Intel(R) UHD Graphics 630';
                    }
                    return originalGetParameter.call(this, parameter);
                };
            } catch (err) {}

            try {
                const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function (...args) {
                    const context = this.getContext('2d');
                    if (context) {
                        context.fillStyle = '#ffffff';
                        context.globalAlpha = 0.01;
                        context.fillRect(0, 0, 1, 1);
                    }
                    return origToDataURL.apply(this, args);
                };
            } catch (err) {}

            window.__webdriverActiveRequests = 0;
            const updatePending = (delta) => {
                const current = window.__webdriverActiveRequests || 0;
                window.__webdriverActiveRequests = Math.max(0, current + delta);
            };

            if (!window.__nafFetchPatched && window.fetch) {
                const origFetch = window.fetch;
                window.fetch = (...args) => {
                    updatePending(1);
                    return origFetch(...args).then(
                        (value) => { updatePending(-1); return value; },
                        (error) => { updatePending(-1); throw error; },
                    );
                };
                window.__nafFetchPatched = true;
            }

            if (!window.__nafXHRPatched && window.XMLHttpRequest) {
                const proto = XMLHttpRequest.prototype;
                const origSend = proto.send;
                proto.send = function (...args) {
                    try {
                        updatePending(1);
                        this.addEventListener('loadend', () => updatePending(-1), { once: true });
                    } catch (err) {}
                    return origSend.apply(this, args);
                };
                window.__nafXHRPatched = true;
            }
        })();
    '''
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": script},
        )
    except Exception:
        try:
            driver.execute_script(script)
        except Exception:
            pass
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    try:
        version = driver.execute_cdp_cmd("Browser.getVersion", {})
    except Exception:
        version = {}
    try:
        user_agent = version.get("userAgent", "")
        if user_agent:
            if "HeadlessChrome" in user_agent:
                user_agent = user_agent.replace("HeadlessChrome", "Chrome")
            override = {
                "userAgent": user_agent,
                "platform": "Windows NT 10.0; Win64; x64",
                "acceptLanguage": "es-EC,es;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            driver.execute_cdp_cmd("Network.setUserAgentOverride", override)
    except Exception:
        pass
    driver._naf_stealth = True


def wait_for_network_idle(driver, timeout: float = 25.0, quiet_period: float = 1.5) -> bool:
    'Espera a que la pestaña quede sin solicitudes activas.'
    if driver is None:
        return False
    limite = time.monotonic() + timeout
    objetivo_quieto = time.monotonic() + quiet_period
    while time.monotonic() < limite:
        try:
            pending = driver.execute_script("return window.__webdriverActiveRequests || 0;")
        except Exception:
            pending = 0
        try:
            ready = driver.execute_script("return document.readyState")
        except Exception:
            ready = "loading"
        if pending == 0 and ready in {"interactive", "complete"}:
            if time.monotonic() >= objetivo_quieto:
                return True
        else:
            objetivo_quieto = time.monotonic() + quiet_period
        time.sleep(0.5)
    raise TimeoutError("La página no alcanzó estado inactivo a tiempo")


def _esperar_documento_completo(driver, timeout: float = 20.0) -> bool:
    '''Refuerzo para esperar a ``document.readyState == "complete"``.'''
    if driver is None:
        return False
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def handle_sso_after_login(
    driver,
    timeout: float = 60.0,
    idle_timeout: float = 30.0,
    dashboard_url: str = "https://sites.telconet.ec/naf/compras/",
) -> bool:
    'Forza la redirección SSO y valida que el portal cargue sin esperas artificiales.'
    if driver is None:
        return False
    limite = time.monotonic() + timeout
    inicio = time.monotonic()
    ultimo_ticket = None
    forced_dashboard = False
    while time.monotonic() < limite:
        try:
            actual = driver.current_url or ""
        except Exception:
            actual = ""

        if "/sso/check" in actual:
            instalar_ganchos_naf(driver)
            if "ticket=" in actual and actual != ultimo_ticket:
                ultimo_ticket = actual
                try:
                    driver.get(actual)
                except Exception:
                    try:
                        driver.execute_script(
                            "window.location.replace(arguments[0]);",
                            actual,
                        )
                    except Exception:
                        pass
                try:
                    wait_for_network_idle(driver, timeout=idle_timeout)
                except TimeoutError:
                    _esperar_documento_completo(driver, timeout=idle_timeout)
                forced_dashboard = False
                continue
            if (
                "ticket=" not in actual
                and not forced_dashboard
                and time.monotonic() - inicio > 8
            ):
                try:
                    driver.get(dashboard_url)
                    forced_dashboard = True
                    instalar_ganchos_naf(driver)
                    continue
                except Exception:
                    pass

        if "naf/compras" in actual and "ticket=" not in actual:
            try:
                wait_for_network_idle(driver, timeout=idle_timeout)
            except TimeoutError:
                _esperar_documento_completo(driver, timeout=idle_timeout)
            return True

        if (
            not forced_dashboard
            and "naf/compras" not in actual
            and time.monotonic() - inicio > 15
        ):
            try:
                driver.get(dashboard_url)
                forced_dashboard = True
                instalar_ganchos_naf(driver)
                continue
            except Exception:
                pass

        time.sleep(0.5)

    try:
        driver.get(dashboard_url)
        instalar_ganchos_naf(driver)
        wait_for_network_idle(driver, timeout=min(idle_timeout, 20.0))
        return True
    except Exception:
        return False


def simulate_human_activity(driver, etiqueta: str = 'post_login', min_interval: float = 2.0) -> None:
    'Envía eventos ligeros para reducir heurísticas anti bot.'
    if driver is None:
        return
    marca = f"_naf_sim_{etiqueta}"
    ahora = time.monotonic()
    ultimo = getattr(driver, marca, 0.0)
    if ahora - ultimo < min_interval:
        return
    script = '''
        (() => {
            const target = document.body || document.documentElement;
            if (!target) {
                return;
            }
            const baseX = Math.floor(window.innerWidth / 2) + Math.floor(Math.random() * 40) - 20;
            const baseY = Math.floor(window.innerHeight / 2) + Math.floor(Math.random() * 40) - 20;
            ['mousemove', 'mouseover'].forEach((type) => {
                const evt = new MouseEvent(type, {
                    bubbles: true,
                    cancelable: true,
                    clientX: baseX,
                    clientY: baseY,
                });
                target.dispatchEvent(evt);
            });
            const focusable = document.querySelector('input, button, a, select, textarea');
            if (focusable && focusable.focus) {
                focusable.focus({ preventScroll: true });
            }
            const keyboardTarget = document.activeElement || target;
            const keyEvt = new KeyboardEvent('keydown', {
                key: 'Tab',
                code: 'Tab',
                bubbles: true,
            });
            keyboardTarget.dispatchEvent(keyEvt);
        })();
    '''
    try:
        driver.execute_script(script)
    except Exception:
        pass
    setattr(driver, marca, ahora)

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

    user = username if username is not None else cfg.usuario
    if user:
        user = user.split("@")[0]
    pwd = password if password is not None else cfg.password

    cliente = SeafileClient(cfg.seafile_url, cfg.usuario, cfg.password)
    repo_id = cfg.seafile_repo_id
    subfolder = cfg.seafile_subfolder or "/"

    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
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
    instalar_ganchos_naf(driver)
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
        handle_sso_after_login(driver, timeout=60.0, idle_timeout=30.0)
        try:
            wait_for_network_idle(driver, timeout=30.0)
        except TimeoutError:
            _esperar_documento_completo(driver, timeout=30.0)
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
            raise RuntimeError("Fallo al localizar 'lista_accesos'")
        simulate_human_activity(driver)
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
                time.sleep(0.5)
                simulate_human_activity(driver)
                for intento_busqueda in range(3):
                    _click("btnbuscarorden", elements["btnbuscarorden"])
                    try:
                        wait_for_network_idle(driver, timeout=25.0)
                        break
                    except TimeoutError:
                        if intento_busqueda == 2:
                            raise RuntimeError("La búsqueda de la OC no respondió a tiempo")
                        time.sleep(2)

                for _ in range(5):
                    if not driver.find_elements(*elements["toast"]):
                        break
                    time.sleep(1)
                boton_descarga = _find("descargar_orden", elements["descargar_orden"])
                existentes = {
                    pdf: pdf.stat().st_mtime for pdf in download_dir.glob("*.pdf")
                }
                try:
                    boton_descarga.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", boton_descarga)

                archivo = esperar_descarga_pdf(download_dir, existentes)
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
#=======
#<<<<<<< codex/fix-email-scanning-for-descarga-normal
#>>>>>>> master
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
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
#=======
#=======
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
                    prov_clean = sanitize_filename(proveedor)
                    nuevo_nombre = download_dir / f"{numero} - {prov_clean}.pdf"
                    try:
                        archivo.rename(nuevo_nombre)
                        archivo = nuevo_nombre
                    except Exception:
                        prov_clean = sanitize_filename(proveedor, max_len=20)
                        nuevo_nombre = download_dir / f"{numero} - {prov_clean}.pdf"
                        try:
                            archivo.rename(nuevo_nombre)
                            archivo = nuevo_nombre
                        except Exception:
                            pass
#>>>>>>> master
#>>>>>>> master
                try:
                    cliente.upload_file(
                        repo_id, str(archivo), parent_dir=subfolder
                    )
                except Exception as e:
                    errores.append(f"OC {numero}: fallo subida {e}")
            except Exception as exc:  # pragma: no cover - runtime issues
                errores.append(f"OC {numero}: {exc}")
    finally:
        driver.quit()

    if ordenes:
        actualizar_proveedores_desde_pdfs(ordenes, download_dir)

    numeros = [oc.get("numero") for oc in ordenes]
    subidos, faltantes, errores_mov = mover_oc(cfg, ordenes)
    if getattr(cfg, "compra_bienes", False):
        organizar_bienes(cfg.carpeta_analizar, cfg.carpeta_analizar)
    errores.extend(errores_mov)
    faltantes.extend(n for n in numeros if any(n in e for e in errores))
    # evitar números repetidos al reportar faltantes
    faltantes = list(dict.fromkeys(faltantes))
    return subidos, faltantes, errores


if __name__ == "__main__":  # pragma: no cover
    descargar_oc([])

