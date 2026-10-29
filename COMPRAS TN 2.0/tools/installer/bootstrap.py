"""Load this release's libraries with the user-approved Store interpreter."""
import runpy
import site
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
# Nunca mezclar librerías incompletas del Python global con las de esta versión.
sys.path[:] = [p for p in sys.path if "site-packages" not in Path(p).parts and "dist-packages" not in Path(p).parts]
sys.path.insert(0, str(root / "packages"))
site.addsitedir(str(root / "packages"))
sys.path.insert(0, str(root / "app/src"))
kind, target = sys.argv[1:3]
sys.argv = [target, *sys.argv[3:]]
if kind == "--module":
    runpy.run_module(target, run_name="__main__", alter_sys=True)
elif kind == "--script":
    runpy.run_path(target, run_name="__main__")
else:
    raise ValueError("Modo de arranque desconocido")
