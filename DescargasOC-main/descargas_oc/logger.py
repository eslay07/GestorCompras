import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'

BASE_DIR = Path(__file__).resolve().parents[1]
log_file = BASE_DIR / 'data' / 'descargasoc.log'
log_file.parent.mkdir(exist_ok=True)

level = logging.DEBUG if os.getenv('DEBUG') == '1' else logging.INFO

logging.basicConfig(
    level=level,
    format=_LOG_FORMAT,
    handlers=[
        RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5),
        logging.StreamHandler()
    ]
)

def get_logger(name: str = __name__):
    return logging.getLogger(name)
