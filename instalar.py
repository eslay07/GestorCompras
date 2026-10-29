"""Instalador sin administrador: extraiga el ZIP completo y use Python 3.12 o 3.13."""
import ctypes
import sys
from pathlib import Path

try:
    root = Path(__file__).resolve().parent
    if sys.version_info[:2] not in {(3, 12), (3, 13)}:
        raise RuntimeError("Abra este archivo con Python 3.12 o 3.13; en equipos corporativos use el Python aprobado de Microsoft Store.")
    source = root / "instalar_datos"
    if not source.is_dir():
        source = root / ".installer-build/store/instalar_datos"
    sys.path.insert(0, str(source))
    from instalador import main
    raise SystemExit(main())
except Exception as exc:
    ctypes.windll.user32.MessageBoxW(None, f"No se pudo iniciar instalar.py:\n{type(exc).__name__}: {exc}\nExtraiga el ZIP completo antes de ejecutar.", "instalador", 0x10)
    raise
