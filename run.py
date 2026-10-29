"""Inicia COMPRAS TN desde la raíz con su entorno de dependencias."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "COMPRAS TN 2.0"))
from launch import entry

if __name__ == "__main__":
    raise SystemExit(entry())
