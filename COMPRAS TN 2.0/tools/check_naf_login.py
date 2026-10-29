"""Read-only live login check. Credentials are entered in memory, never saved.

Run with Python 3.12 and the application's dependencies. It opens the target
module using the production browser factory but never fills/saves an order.
"""
from __future__ import annotations

import getpass
import json
import logging
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from compras_tn.domain.models import SessionCredentials
from compras_tn.infrastructure.automation.downloads import OrderPortalPage, _safe_int
from compras_tn.infrastructure.automation.purchase_orders import SeleniumPurchaseOrderGateway
from compras_tn.paths import AppPaths
from compras_tn.security import sanitize_text


class ReadOnlySettings:
    def __init__(self, database: Path):
        self.database = database

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.database.as_uri() + '?mode=ro', uri=True) as connection:
            row = connection.execute('SELECT value_json FROM settings WHERE namespace=? AND key=?', (namespace, key)).fetchone()
        return json.loads(row[0]) if row else default


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    paths = AppPaths.default()
    print(f'Base productiva (solo lectura): {paths.database}', flush=True)
    username = input('Usuario: ').strip()
    password = getpass.getpass('Contraseña temporal (no se guarda): ')
    credentials = SessionCredentials(username=username, email=f'{username.split("@")[0]}@telconet.ec', password=password)
    settings = ReadOnlySettings(paths.database)
    failures = 0
    with tempfile.TemporaryDirectory(prefix='compras-naf-login-') as folder:
        temporary = AppPaths.from_root(Path(folder))
        gateway = SeleniumPurchaseOrderGateway(settings, temporary)
        for module in ('descargas', 'descargas_abastecimiento', 'carga_automatica'):
            driver = gateway._create_driver(True)
            try:
                if module == 'carga_automatica':
                    page = gateway._page(driver)
                    page.headless = True
                else:
                    page = OrderPortalPage(driver, Path(folder),
                        element_timeout=_safe_int(settings.get('downloads', 'element_timeout', 45), 45, 10, 180),
                        login_timeout=_safe_int(settings.get('downloads', 'login_timeout', 100), 100, 20, 300),
                        diagnostics_folder=temporary.diagnostics,
                        login_attempts=_safe_int(settings.get('downloads', 'login_retries', 3), 3, 1, 3),
                        auth_module=module,
                        headless=True)
                print(f'{module}: Chrome oculto; validando login y pantalla objetivo', flush=True)
                try:
                    page.login_and_open_orders(credentials)
                    print(f'{module}: LOGIN Y PANTALLA VERIFICADOS. Sin descargar, Guardar ni escribir en Sheets.', flush=True)
                except Exception as exc:
                    print(sanitize_text(f'{module}: {type(exc).__name__}: {exc}', (password,)), flush=True)
                    failures += 1
            finally:
                driver.quit()
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
