#!/usr/bin/env python3
"""Parche automático para endurecer el login de Telconet NAF.

Resumen de acciones:
- Inyecta un script anti detección vía CDP que camufla Selenium y monitorea la red.
- Cambia la creación del driver a ``undetected_chromedriver`` y mantiene las ChromeOptions endurecidas.
- Añade utilidades para esperar la red, forzar la redirección del ticket SSO y simular actividad humana.
- Refuerza el flujo de login y las búsquedas con reintentos y ``page_load_strategy = 'eager'``.

Uso:
    python update_sso_network_patch.py
El script crea copias ``.bak`` antes de modificar y muestra un resumen final.
"""
from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent


@dataclass
class PatchReport:
    path: Path
    applied: bool
    messages: List[str] = field(default_factory=list)

    def extend(self, *msgs: str) -> None:
        self.messages.extend(msg for msg in msgs if msg)


Transformer = Callable[[str], Tuple[str, List[str]]]


def create_backup(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".bak")
    if backup.exists():
        return
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")


def apply_transform(path: Path, transformer: Transformer) -> PatchReport:
    report = PatchReport(path=path, applied=False)
    if not path.exists():
        report.extend("Archivo no encontrado; se omite.")
        return report
    original = path.read_text(encoding="utf-8")
    updated, notes = transformer(original)
    if updated != original:
        create_backup(path)
        path.write_text(updated, encoding="utf-8")
        report.applied = True
    report.extend(*notes)
    return report


def ensure_page_load_strategy(content: str) -> Tuple[str, bool]:
    if "options.page_load_strategy" in content:
        return content, False
    replacement = "options = webdriver.ChromeOptions()\n"
    if replacement not in content:
        return content, False
    return content.replace(
        replacement,
        "options = webdriver.ChromeOptions()\n    options.page_load_strategy = \"eager\"\n",
        1,
    ), True


def ensure_uc_integration(content: str) -> Tuple[str, bool]:
    updated = content
    changed = False
    import_line = "import undetected_chromedriver as uc"
    if import_line not in updated:
        inserted = False
        target = "from selenium import webdriver"
        if target in updated:
            updated = updated.replace(target, f"{import_line}\n{target}", 1)
            inserted = True
        else:
            for anchor in (
                "import time\n",
                "import sys\n",
                "import subprocess\n",
                "from pathlib import Path\n",
            ):
                if anchor in updated:
                    updated = updated.replace(anchor, anchor + import_line + "\n", 1)
                    inserted = True
                    break
        if not inserted:
            prefix = "" if updated.startswith("\n") else "\n"
            updated = f"{import_line}{prefix}{updated}"
        changed = True

    if "webdriver.Chrome(" in updated and "uc.Chrome(" not in updated:
        updated = updated.replace("webdriver.Chrome(", "uc.Chrome(")
        changed = True

    return updated, changed


def inject_stealth_and_helpers(content: str) -> Tuple[str, bool]:
    marker = "# --- parche naf anti-automatizacion ---"
    if marker in content:
        return content, False
    helper_block = textwrap.dedent(
        """

        __MARKER__
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
        """
    ).replace("__MARKER__", marker)
    anchor = "def descargar_oc("
    if anchor not in content:
        return content, False
    return content.replace(anchor, helper_block + "\n" + anchor, 1), True


def patch_selenium_modulo(text: str) -> Tuple[str, List[str]]:
    notes: List[str] = []
    updated = text

    updated_tmp, changed = ensure_uc_integration(updated)
    if changed:
        updated = updated_tmp
        notes.append(
            "Se actualizó el módulo para usar undetected_chromedriver y su import correspondiente."
        )

    updated, changed = inject_stealth_and_helpers(updated)
    if changed:
        notes.append("Se añadieron utilidades anti detección y de espera de red.")

    updated, changed = ensure_page_load_strategy(updated)
    if changed:
        notes.append("Se fuerza page_load_strategy='eager' en ChromeOptions.")

    if "instalar_ganchos_naf(driver)\n" not in updated:
        for needle in (
            "    driver = uc.Chrome(options=options)\n",
            "    driver = webdriver.Chrome(options=options)\n",
        ):
            if needle in updated:
                updated = updated.replace(
                    needle,
                    f"{needle}    instalar_ganchos_naf(driver)\n",
                    1,
                )
                notes.append(
                    "Se instala el script anti detección justo tras crear el driver."
                )
                break

    handle_snippet = "        time.sleep(2)\n        for _ in range(3):"
    if (
        "handle_sso_after_login(driver, timeout=60.0, idle_timeout=30.0)" not in updated
        and handle_snippet in updated
    ):
        replacement = (
            "        time.sleep(2)\n"
            "        handle_sso_after_login(driver, timeout=60.0, idle_timeout=30.0)\n"
            "        try:\n"
            "            wait_for_network_idle(driver, timeout=30.0)\n"
            "        except TimeoutError:\n"
            "            _esperar_documento_completo(driver, timeout=30.0)\n"
            "        simulate_human_activity(driver)\n"
            "        for _ in range(3):"
        )
        updated = updated.replace(handle_snippet, replacement, 1)
        notes.append(
            "Se invoca handle_sso_after_login con esperas reforzadas tras enviar el login."
        )

    lista_marker = "        _click(\"lista_accesos\", elements[\"lista_accesos\"])\n"
    if "simulate_human_activity(driver)\n        _click(\"lista_accesos" not in updated and lista_marker in updated:
        updated = updated.replace(
            lista_marker,
            "        simulate_human_activity(driver)\n" + lista_marker,
            1,
        )
        notes.append("Se simula actividad humana antes de abrir el menú principal.")

    buscar_block = (
        "                time.sleep(2)\n"
        "                _click(\"btnbuscarorden\", elements[\"btnbuscarorden\"])\n\n"
        "                for _ in range(5):\n"
        "                    if not driver.find_elements(*elements[\"toast\"]):\n"
        "                        break\n"
        "                    time.sleep(2)\n"
        "                boton_descarga = _find(\"descargar_orden\", elements[\"descargar_orden\"])\n"
    )
    if "wait_for_network_idle" not in updated or "intento_busqueda" not in updated:
        if buscar_block in updated:
            nuevo_block = (
                "                time.sleep(0.5)\n"
                "                simulate_human_activity(driver)\n"
                "                for intento_busqueda in range(3):\n"
                "                    _click(\"btnbuscarorden\", elements[\"btnbuscarorden\"])\n"
                "                    try:\n"
                "                        wait_for_network_idle(driver, timeout=25.0)\n"
                "                        break\n"
                "                    except TimeoutError:\n"
                "                        if intento_busqueda == 2:\n"
                "                            raise RuntimeError(\"La búsqueda de la OC no respondió a tiempo\")\n"
                "                        time.sleep(2)\n\n"
                "                for _ in range(5):\n"
                "                    if not driver.find_elements(*elements[\"toast\"]):\n"
                "                        break\n"
                "                    time.sleep(1)\n"
                "                boton_descarga = _find(\"descargar_orden\", elements[\"descargar_orden\"])\n"
            )
            updated = updated.replace(buscar_block, nuevo_block, 1)
            notes.append("Se refuerza la búsqueda de OC con reintentos y espera de red.")

    return updated, notes


def ensure_import_block(text: str, search: str, replacement: str) -> Tuple[str, bool]:
    if replacement.strip() in text:
        return text, False
    if search not in text:
        return text, False
    return text.replace(search, replacement, 1), True


def patch_selenium_abastecimiento(text: str) -> Tuple[str, List[str]]:
    notes: List[str] = []
    updated = text

    updated_tmp, changed = ensure_uc_integration(updated)
    if changed:
        updated = updated_tmp
        notes.append(
            "Se cambió la creación del driver a undetected_chromedriver en Abastecimiento."
        )

    multi_import = textwrap.dedent(
        """
    from .selenium_modulo import (
        esperar_descarga_pdf,
        handle_sso_after_login,
        simulate_human_activity,
        instalar_ganchos_naf,
        wait_for_network_idle,
    )
    """
    ).strip("\n")

    simple_import = "from .selenium_modulo import esperar_descarga_pdf"
    updated, changed = ensure_import_block(updated, simple_import, multi_import)
    if changed:
        notes.append("Se amplían las importaciones del módulo Selenium común.")

    simple_import_alt = "from selenium_modulo import esperar_descarga_pdf"
    multi_import_alt = textwrap.dedent(
        """
    from selenium_modulo import (
        esperar_descarga_pdf,
        handle_sso_after_login,
        simulate_human_activity,
        instalar_ganchos_naf,
        wait_for_network_idle,
    )
    """
    ).strip("\n")
    updated, changed = ensure_import_block(updated, simple_import_alt, multi_import_alt)
    if changed:
        notes.append("Se amplían las importaciones para ejecución directa.")

    insertion_variants = [
        (
            "    simulate_human_activity,\n    wait_for_network_idle,",
            "    simulate_human_activity,\n    instalar_ganchos_naf,\n    wait_for_network_idle,",
        ),
        (
            "    simulate_human_activity,\n    wait_for_network_idle",
            "    simulate_human_activity,\n    instalar_ganchos_naf,\n    wait_for_network_idle",
        ),
    ]
    added_import = False
    for search, replacement in insertion_variants:
        while search in updated:
            updated = updated.replace(search, replacement, 1)
            added_import = True
    if added_import:
        notes.append("Se añade instalar_ganchos_naf a las importaciones de utilidades.")

    updated_tmp, changed = ensure_page_load_strategy(updated)
    if changed:
        updated = updated_tmp
        notes.append("Se establece page_load_strategy='eager' en las ChromeOptions de Abastecimiento.")

    if "instalar_ganchos_naf(driver)\n" not in updated:
        for needle in (
            "    driver = uc.Chrome(options=options)\n",
            "    driver = webdriver.Chrome(options=options)\n",
        ):
            if needle in updated:
                updated = updated.replace(
                    needle,
                    f"{needle}    instalar_ganchos_naf(driver)\n",
                    1,
                )
                notes.append(
                    "Se instala el script anti detección justo tras crear el driver de Abastecimiento."
                )
                break

    anchor = "        time.sleep(2)\n        for _ in range(3):"
    reemplazos_handle = 0
    while anchor in updated:
        replacement = (
            "        time.sleep(2)\n"
            "        handle_sso_after_login(driver, timeout=60.0, idle_timeout=30.0)\n"
            "        try:\n"
            "            wait_for_network_idle(driver, timeout=30.0)\n"
            "        except TimeoutError:\n"
            "            limite_ready = time.monotonic() + 20\n"
            "            while time.monotonic() < limite_ready:\n"
            "                try:\n"
            "                    if driver.execute_script(\"return document.readyState\") == \"complete\":\n"
            "                        break\n"
            "                except Exception:\n"
            "                    break\n"
            "                time.sleep(0.5)\n"
            "        simulate_human_activity(driver)\n"
            "        for _ in range(3):"
        )
        updated = updated.replace(anchor, replacement, 1)
        reemplazos_handle += 1
    if reemplazos_handle:
        notes.append("Se invoca handle_sso_after_login en el flujo de Abastecimiento.")

    menu_anchor = "        hacer_click(\"lista_accesos\", elements[\"lista_accesos\"])\n"
    replacements_menu = 0
    search_pos = 0
    insert_line = "        simulate_human_activity(driver)\n"
    while True:
        idx = updated.find(menu_anchor, search_pos)
        if idx == -1:
            break
        prev_line_start = updated.rfind('\n', 0, idx) + 1
        prev_line = updated[prev_line_start:idx]
        if 'simulate_human_activity(driver)' not in prev_line:
            updated = updated[:idx] + insert_line + updated[idx:]
            search_pos = idx + len(insert_line) + len(menu_anchor)
            replacements_menu += 1
        else:
            search_pos = idx + len(menu_anchor)
    if replacements_menu:
        notes.append("Se simula actividad humana antes de abrir los menús principales.")

    dedupe_block = (
        "        simulate_human_activity(driver)\n"
        "        simulate_human_activity(driver)\n"
    )
    while dedupe_block in updated:
        updated = updated.replace(dedupe_block, "        simulate_human_activity(driver)\n")

    buscar_anchor = (
        "        hacer_click(\"btnbuscarorden\", elements[\"btnbuscarorden\"])\n"
        "        esperar_toast()\n"
    )
    if buscar_anchor in updated:
        reemplazos = 0
        nuevo = (
            "        simulate_human_activity(driver)\n"
            "        for intento_busqueda in range(3):\n"
            "            hacer_click(\"btnbuscarorden\", elements[\"btnbuscarorden\"])\n"
            "            try:\n"
            "                wait_for_network_idle(driver, timeout=25.0)\n"
            "                break\n"
            "            except TimeoutError:\n"
            "                if intento_busqueda == 2:\n"
            "                    raise RuntimeError(\"La búsqueda de órdenes no respondió a tiempo\")\n"
            "                time.sleep(2)\n"
            "        esperar_toast()\n"
        )
        while buscar_anchor in updated:
            updated = updated.replace(buscar_anchor, nuevo, 1)
            reemplazos += 1
        if reemplazos:
            notes.append("Se endurece la búsqueda tras login con espera de red y reintentos.")

    return updated, notes


def patch_requirements(text: str) -> Tuple[str, List[str]]:
    lines = text.splitlines()
    stripped = [line.strip() for line in lines]
    objetivo = "undetected-chromedriver"
    if objetivo in stripped:
        return text, []

    notes = ["Se añadió undetected-chromedriver a requirements.txt."]

    try:
        idx = stripped.index("selenium")
        insert_at = idx + 1
    except ValueError:
        insert_at = len(lines)

    lines.insert(insert_at, objetivo)

    if lines and lines[-1] != "":
        lines.append("")

    return "\n".join(lines), notes


def run_patch(root: Path) -> List[PatchReport]:
    reports: List[PatchReport] = []
    modulo = root / "DescargasOC-main" / "descargas_oc" / "selenium_modulo.py"
    reports.append(apply_transform(modulo, patch_selenium_modulo))

    abastecimiento = root / "DescargasOC-main" / "descargas_oc" / "selenium_abastecimiento.py"
    reports.append(apply_transform(abastecimiento, patch_selenium_abastecimiento))

    requirements = root / "requirements.txt"
    reports.append(apply_transform(requirements, patch_requirements))

    return reports


def smoke_test_patch(root: Path = ROOT) -> Tuple[bool, List[str]]:
    mensajes: List[str] = []
    modulo = root / "DescargasOC-main" / "descargas_oc" / "selenium_modulo.py"
    if not modulo.exists():
        return False, ["selenium_modulo.py no está presente tras el parche."]
    contenido = modulo.read_text(encoding="utf-8")
    if "handle_sso_after_login" not in contenido:
        mensajes.append("No se detectó handle_sso_after_login en selenium_modulo.py")
    if "Page.addScriptToEvaluateOnNewDocument" not in contenido:
        mensajes.append("El bloque de inyección CDP no está presente en selenium_modulo.py")
    if "uc.Chrome" not in contenido:
        mensajes.append(
            "selenium_modulo.py no usa undetected_chromedriver tras aplicar el parche"
        )

    login_refs: List[Path] = []
    objetivo = "https://cas.telconet.ec/cas/login?service="
    for path in (root / "DescargasOC-main" / "descargas_oc").glob("**/*.py"):
        try:
            data = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if objetivo in data and "handle_sso_after_login(driver, timeout=60.0" in data:
            login_refs.append(path)
    if not login_refs:
        mensajes.append("Ningún flujo con cas.telconet.ec contiene la llamada a handle_sso_after_login.")

    return not mensajes, mensajes


def main(argv: Sequence[str] | None = None) -> int:
    reports = run_patch(ROOT)
    print("Archivos procesados:")
    for rep in reports:
        estado = "APLICADO" if rep.applied else "sin cambios"
        print(f"- {rep.path.relative_to(ROOT)} -> {estado}")
        for msg in rep.messages:
            print(f"    * {msg}")
    ok, mensajes = smoke_test_patch(ROOT)
    print("\nSmoke test:")
    if ok:
        print("- OK: firmas esenciales detectadas.")
    else:
        for msg in mensajes:
            print(f"- {msg}")
    print("\nEjecución finalizada.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
