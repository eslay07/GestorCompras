"""Arranque sin dependencias: selecciona el entorno antes de cargar la interfaz."""
from pathlib import Path
import os
import json
import traceback
import subprocess
import sys


def main():
    project = Path(__file__).resolve().parent
    environment = Path.home() / ".venvs" / "compras-tn"
    executable = environment / "Scripts" / ("pythonw.exe" if Path(sys.executable).stem.lower() == "pythonw" else "python.exe")
    # El instalador crea su propio entorno; los lanzadores usan la versión instalada.
    installed = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ComprasTN/programa"
    pointer = installed / "current.json"
    if sys.prefix == sys.base_prefix and pointer.is_file():
        config = json.loads(pointer.read_text(encoding="utf-8"))
        if config.get("python_mode") == "store313" and (installed / "launcher.py").is_file():
            return subprocess.call([sys.executable, str(installed / "launcher.py"), *sys.argv[1:]])
    # Respeta un entorno virtual activado y no vuelve a lanzar el mismo entorno.
    if sys.prefix == sys.base_prefix and executable.is_file():
        env = os.environ.copy()
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONPATH", None)
        return subprocess.call([str(executable), str(project / "run.py"), *sys.argv[1:]], env=env)
    source = str(project / "src")
    if source not in sys.path:
        sys.path.insert(0, source)
    from compras_tn.__main__ import main as application_main
    return application_main()


def entry():
    try:
        result = main()
        if result:
            raise RuntimeError(f"COMPRAS TN terminó con código {result}. Revise el registro startup.log de la instalación.")
        return result
    except Exception:
        folder = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ComprasTN/diagnostics"
        folder.mkdir(parents=True, exist_ok=True)
        log = folder / "launch-error.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f"No se pudo iniciar COMPRAS TN. Ejecute instalar.py del ZIP actualizado para instalar o reparar el entorno.\nRegistro: {log}", "COMPRAS TN", 0x10)
        return 1
