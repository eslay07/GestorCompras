"""Utilidades Selenium compartidas para clics robustos.

Los portales donde opera el sistema (Telcos, OC, etc.) usan botones cuyo texto
clickeable vive dentro de un ``<span>`` anidado. Cuando hay overlays o
animaciones de modal el clic directo puede ser interceptado. Estas utilidades
centralizan una estrategia de "intento con varios locators + fallback a JS".
"""
from __future__ import annotations

from typing import Iterable, Tuple, Any

from gestorcompras.services.telcos_automation import wait_clickable_or_error


def click_with_fallback(
    driver,
    locators: Iterable[Tuple[str, str]],
    descripcion: str,
    timeout: int = 15,
    retries: int = 1,
    parent_window: Any = None,
):
    """Intenta hacer clic probando varios locators en orden.

    Para cada locator espera que sea clickeable y ejecuta ``.click()``. Si el
    clic nativo es interceptado (overlays, animaciones, spans internos) cae al
    clic vía JavaScript. Si ningún locator funciona, lanza una excepción con el
    último error encontrado.
    """
    last_error: Exception | None = None
    for locator in locators:
        try:
            elem = wait_clickable_or_error(
                driver, locator, parent_window, descripcion, timeout=timeout, retries=retries
            )
            try:
                elem.click()
            except Exception:
                driver.execute_script("arguments[0].click();", elem)
            return elem
        except Exception as exc:
            last_error = exc
    raise Exception(f"No se pudo hacer clic en {descripcion}") from last_error


def click_robust(driver, element):
    """Hace clic sobre un elemento ya localizado con fallback a JS.

    Útil cuando ya se obtuvo el elemento con ``WebDriverWait`` o ``ActionChains``
    y sólo se necesita la semántica de click con fallback.
    """
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return element


def retry_task(
    fn,
    args: tuple = (),
    kwargs: dict | None = None,
    max_attempts: int = 2,
    log=None,
    on_retry=None,
):
    """Ejecuta ``fn(*args, **kwargs)`` hasta ``max_attempts`` veces.

    Entre reintentos espera 2 segundos y llama a ``on_retry(attempt)`` si se
    proporcionó (útil para reabrir un panel o restablecer el estado del driver).
    Si todos los intentos fallan re-lanza la última excepción. Acepta un
    callable ``log(msg)`` para reportar cada fallo no definitivo.
    """
    import time

    kwargs = kwargs or {}
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                if log:
                    log(f"Intento {attempt}/{max_attempts} fallido: {exc}. Reintentando en 2 s…")
                if on_retry:
                    try:
                        on_retry(attempt)
                    except Exception:
                        pass
                time.sleep(2)
    raise last_exc  # type: ignore[misc]


__all__ = ["click_with_fallback", "click_robust", "retry_task"]
