"""Stable desktop entry point: resolves the currently active release."""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    config = json.loads((root / "current.json").read_text(encoding="utf-8"))
    release = root / "releases" / config["release"]
    if not release.resolve().is_relative_to((root / "releases").resolve()):
        raise ValueError("La ubicación de la versión activa no es válida.")
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["COMPRAS_TN_DATA_DIR"] = config["data"]
    env["COMPRAS_TN_CHROME"] = str(release / "browser/chrome-win64/chrome.exe")
    env["COMPRAS_TN_CHROMEDRIVER"] = str(release / "browser/chromedriver-win64/chromedriver.exe")
    env["PATH"] = str(release / "runtime") + os.pathsep + env.get("PATH", "")
    command = ([config["python"], "-I", "-X", "utf8", str(release / "bootstrap.py"), "--module", "compras_tn"]
               if config.get("python_mode") == "store313"
               else [str(release / "runtime/pythonw.exe"), "-m", "compras_tn"])
    if "--check-startup" in sys.argv[1:]:
        helper = str(release / "app/tools/installer/deployment.py")
        command = ([config["python"], "-I", "-X", "utf8", str(release / "bootstrap.py"), "--script", helper, "--smoke"]
                   if config.get("python_mode") == "store313"
                   else [str(release / "runtime/python.exe"), helper, "--smoke"])
    log = root / "startup.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.call(command, cwd=release / "app", env=env, stdout=stream, stderr=stream)
    if result:
        raise RuntimeError(f"El programa terminó con código {result}. Revise {log} o vuelva a ejecutar instalar.py para reparar las librerías.")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f"No se pudo abrir COMPRAS TN:\n{exc}\nVuelva a ejecutar instalar.py para reparar.", "COMPRAS TN", 0x10)
        sys.exit(1)
