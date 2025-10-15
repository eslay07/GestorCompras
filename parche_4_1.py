#!/usr/bin/env python3
"""Parche 4.1 - Automatiza la actualización del login de Telcos.

Este script busca el archivo ``reasignacion_gui.py`` dentro del árbol de
 directorios donde se ejecuta y aplica las modificaciones necesarias para
 utilizar el nuevo flujo de autenticación con esperas explícitas.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

TARGET_FILENAME = "reasignacion_gui.py"
LOGIN_URL_CONSTANT = 'LOGIN_URL = "https://sites.telconet.ec/naf/compras/sso/check"'

HELPER_FUNCTIONS_BLOCK = '''

def wait_for_document_ready(driver, timeout=60):
    """Espera a que el documento actual termine de cargarse por completo."""

    def _document_complete(drv):
        try:
            return drv.execute_script("return document.readyState") == "complete"
        except Exception:
            return False

    WebDriverWait(driver, timeout).until(_document_complete)


def wait_for_first_element(driver, locators, timeout=30):
    """Espera el primer locator disponible y devuelve el elemento clickeable."""

    last_exception: Optional[TimeoutException] = None
    for locator in locators:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
        except TimeoutException as exc:
            last_exception = exc
    if last_exception is not None:
        raise last_exception
    raise TimeoutException("No se proporcionaron localizadores para la espera.")
'''

NEW_LOGIN_FUNCTION = """
def login_telcos(driver, username, password):
    driver.get(LOGIN_URL)
    wait_for_document_ready(driver, timeout=60)

    try:
        user_input = wait_for_first_element(
            driver,
            [
                (By.NAME, "username"),
                (By.ID, "username"),
                (By.NAME, "UserName"),
                (By.ID, "UserName"),
                (By.NAME, "josso_username"),
            ],
            timeout=40,
        )
    except TimeoutException as exc:
        raise Exception(
            "No se pudo cargar el formulario de usuario en Telcos."
        ) from exc

    user_input.clear()
    user_input.send_keys(username)

    try:
        password_input = wait_for_first_element(
            driver,
            [
                (By.NAME, "password"),
                (By.ID, "password"),
                (By.NAME, "Password"),
                (By.ID, "Password"),
                (By.NAME, "josso_password"),
            ],
            timeout=40,
        )
    except TimeoutException as exc:
        raise Exception(
            "No se pudo cargar el campo de contraseña en Telcos."
        ) from exc

    password_input.clear()
    password_input.send_keys(password)
    password_input.send_keys(Keys.RETURN)

    try:
        wait_for_document_ready(driver, timeout=90)
        WebDriverWait(driver, 90).until(
            EC.presence_of_element_located((By.ID, 'spanTareasPersonales'))
        )
    except TimeoutException as exc:
        raise Exception(
            "La plataforma Telcos tardó demasiado en cargar después del inicio de sesión."
        ) from exc
"""


class PatchError(Exception):
    """Error específico del parche."""


def find_target_files(root: Path) -> Iterable[Path]:
    for path in root.rglob(TARGET_FILENAME):
        if path.is_file():
            yield path


def apply_patch_to_file(path: Path) -> bool:
    original_content = path.read_text(encoding="utf-8")

    if LOGIN_URL_CONSTANT in original_content:
        return False  # Ya aplicado.

    updated = original_content

    # Agregar import Optional.
    if "from typing import Optional" not in updated:
        updated = updated.replace(
            "import logging\n\nlogging.basicConfig",
            "import logging\nfrom typing import Optional\n\nlogging.basicConfig",
            1,
        )

    # Agregar TimeoutException.
    if "from selenium.common.exceptions import TimeoutException" not in updated:
        updated = updated.replace(
            "from selenium.webdriver.common.action_chains import ActionChains",
            "from selenium.webdriver.common.action_chains import ActionChains\nfrom selenium.common.exceptions import TimeoutException",
            1,
        )

    # Insertar constante LOGIN_URL.
    if LOGIN_URL_CONSTANT not in updated:
        updated = updated.replace(
            "logger = logging.getLogger(__name__)\n\n",
            f"logger = logging.getLogger(__name__)\n\n{LOGIN_URL_CONSTANT}\n\n",
            1,
        )

    # Insertar funciones auxiliares.
    if "def wait_for_document_ready(" not in updated:
        updated = updated.replace(
            "\ndef login_telcos",
            f"{HELPER_FUNCTIONS_BLOCK}\n\ndef login_telcos",
            1,
        )

    # Reemplazar cuerpo de login_telcos.
    if "def login_telcos" in updated:
        marker = "def login_telcos(driver, username, password):"
        start = updated.find(marker)
        if start == -1:
            raise PatchError("No se encontró la definición de login_telcos.")
        after = updated.find("\ndef ", start + len(marker))
        if after == -1:
            raise PatchError("No se encontró el final de login_telcos.")
        updated = updated[:start] + NEW_LOGIN_FUNCTION + "\n" + updated[after + 1:]

    if updated == original_content:
        raise PatchError("No se aplicaron cambios; verifique el formato del archivo.")

    path.write_text(updated, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aplica el Parche 4.1 a GestorCompras.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Directorio raíz desde donde buscar los archivos a parchear.",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"El directorio especificado no existe: {root}", file=sys.stderr)
        return 1

    modified_files = []
    for file_path in find_target_files(root):
        try:
            if apply_patch_to_file(file_path):
                modified_files.append(file_path)
                print(f"Aplicado Parche 4.1 a {file_path}")
        except PatchError as exc:
            print(f"No se pudo parchear {file_path}: {exc}", file=sys.stderr)

    if not modified_files:
        print("No se aplicaron cambios; es posible que el parche ya esté instalado o que no se encontraran archivos compatibles.")
        return 0

    print("Parche 4.1 aplicado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
