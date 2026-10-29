from __future__ import annotations

import sys
from typing import cast

from PySide6.QtWidgets import QApplication, QMessageBox

from compras_tn.bootstrap import build_container
from compras_tn.infrastructure.instance import DataLease
from compras_tn.logging_config import configure_logging
from compras_tn.paths import AppPaths
from compras_tn.presentation.main_window import MainWindow
from compras_tn.presentation.theme import STYLE


def main() -> int:
    app = cast(QApplication | None, QApplication.instance()) or QApplication(sys.argv)
    app.setApplicationName("COMPRAS TN 2.0")
    app.setOrganizationName("Telconet")
    app.setStyleSheet(STYLE)
    paths = AppPaths.default()
    configure_logging(paths)
    container = None
    lease = None
    try:
        lease = DataLease(paths.root)
        container = build_container(app_paths=paths)
        window = MainWindow(container)
        window.show()
        return app.exec()
    except Exception as exc:
        QMessageBox.critical(None, "COMPRAS TN 2.0", f"No se pudo iniciar la aplicación:\n{exc}")
        return 1
    finally:
        if container is not None:
            container.services.logout()
            container.database.close()
        if lease is not None:
            lease.close()


if __name__ == "__main__":
    raise SystemExit(main())
