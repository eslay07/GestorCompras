"""Executed by the installer-selected Python with this release's libraries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from compras_tn.infrastructure.db import Database
from compras_tn.infrastructure.portable import merge_profile
from compras_tn.paths import AppPaths


def prepare(data: Path, project: Path, seed: Path):
    paths = AppPaths.from_root(data)
    paths.ensure()
    database = Database(paths.database, project)
    try:
        database.upgrade()
        print("Perfil incluido:", merge_profile(paths.database, json.loads(seed.read_text(encoding="utf-8"))), flush=True)
        with database.engine.connect() as connection:
            from sqlalchemy import text
            if connection.execute(text("PRAGMA integrity_check")).scalar() != "ok":
                raise RuntimeError("La comprobación de integridad de la base no fue satisfactoria.")
            print("Proveedores disponibles:", connection.execute(text("SELECT count(*) FROM suppliers")).scalar(), flush=True)
    finally:
        database.close()


def smoke():
    import google.auth
    import gspread
    import jinja2
    import openpyxl
    import pandas
    import pdfplumber
    import pydantic
    import requests
    import selenium
    import sqlalchemy
    from PySide6.QtWidgets import QApplication

    import alembic
    app = QApplication([])
    import tempfile
    from compras_tn.bootstrap import build_container
    from compras_tn.presentation.main_window import MainWindow
    with tempfile.TemporaryDirectory(prefix="compras-tn-install-check-") as temporary:
        container = build_container(app_paths=AppPaths.from_root(Path(temporary)))
        try:
            window = MainWindow(container)
            window.show()
            app.processEvents()
            if not window.isVisible():
                raise RuntimeError("No se pudo abrir la ventana principal.")
            window.close()
            app.processEvents()
        finally:
            container.services.logout()
            container.database.close()
    print("Arranque completo de COMPRAS TN: OK", flush=True)
    print("Librerías y componentes gráficos: OK", flush=True)
    from compras_tn.infrastructure.automation.browser import create_corporate_browser
    browser = create_corporate_browser(Path.cwd(), True)
    try:
        browser.get("data:text/html,<title>ComprasTN instalado</title>")
        if browser.title != "ComprasTN instalado":
            raise RuntimeError("El navegador no completó la verificación local.")
        print("Navegador y controlador: OK", flush=True)
    finally:
        browser.quit()
    # Keep the imports explicit: missing native dependencies must fail installation.
    assert all((alembic, google.auth, gspread, jinja2, openpyxl, pandas, pdfplumber, pydantic, requests, selenium, sqlalchemy))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--seed", type=Path)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.smoke:
        smoke()
    else:
        prepare(args.data, args.project, args.seed)
