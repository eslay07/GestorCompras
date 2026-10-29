from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from compras_tn.paths import AppPaths
from compras_tn.security import sanitize_text


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Formatear y reemplazar evita que un mensaje completo se pierda y, a la
        # vez, impide que los argumentos originales lleguen al archivo.
        record.msg = sanitize_text(record.getMessage())
        record.args = ()
        return True


def configure_logging(paths: AppPaths) -> None:
    paths.ensure()
    handler = RotatingFileHandler(
        paths.logs / "compras_tn.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.addFilter(SecretFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
