"""Build the offline script installer without a downloaded Python executable."""
import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from build import files, pack


def build(root):
    project = root / "COMPRAS TN 2.0"
    folder = root / ".installer-build/store/instalar_datos"
    output = folder / "payload"
    output.mkdir(parents=True, exist_ok=True)
    previous = root / ".installer-build/payload"
    # Public builds never read production data or package supplier catalogs.
    (previous / "profile.json").parent.mkdir(parents=True, exist_ok=True)
    (previous / "profile.json").write_text(json.dumps({"format": 1, "tables": {}, "settings": []}), encoding="utf-8")
    app = []
    for name in ("src", "alembic", "tools/installer"):
        app.extend(files(project / name, "app/" + name))
    for name in ("alembic.ini", "pyproject.toml", "README.md", "COTIZACIONES_Y_ADJUNTOS.md", "launch.py", "run.py", "COMPRAS 3.0.pyw"):
        app.append((project / name, "app/" + name))
    development = {"mypy", "pytest", "pytest-cov", "pytest-qt", "ruff"}
    requirements = [line for line in (project / "requirements.lock").read_text(encoding="utf-8").splitlines() if line and line.split("==")[0].casefold() not in development]
    require_path = output / "installer-requirements.txt"
    require_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    from email.parser import Parser
    wheels_by_python = {"3.12": "wheels312.zip", "3.13": "wheels.zip"}
    wheel_sources = {"3.12": root / ".installer-build/wheels", "3.13": root / ".installer-build/wheels313"}
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    for python_version, source in wheel_sources.items():
        available = {}
        for wheel in source.glob("*.whl"):
            with zipfile.ZipFile(wheel) as archive:
                name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
                metadata = Parser().parsestr(archive.read(name).decode("utf-8"))
                available[normalize(metadata["Name"])] = metadata["Version"]
        for line in requirements:
            name, version = line.split("==", 1)
            if available.get(normalize(name)) != version:
                raise RuntimeError(f"Actualice los paquetes Python {python_version}: {line}")
    app.append((require_path, "app/installer-requirements.txt"))
    expanded = pack(output / "application.zip", app)
    for python_version, source in wheel_sources.items():
        expanded += pack(output / wheels_by_python[python_version], [(p, p.name) for p in sorted(source.glob("*.whl"))])
    for name in ("chrome.zip", "chromedriver.zip", "profile.json"):
        shutil.copy2(previous / name, output / name)
        if name.endswith(".zip"):
            with zipfile.ZipFile(output / name) as archive:
                expanded += sum(p.file_size for p in archive.infolist())
    names = ("application.zip", "wheels312.zip", "wheels.zip", "chrome.zip", "chromedriver.zip", "profile.json")
    hashes = {name: hashlib.file_digest((output / name).open("rb"), "sha256").hexdigest() for name in names}
    version = re.search(r'version = "([^"]+)"', (project / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    manifest = {"format": 1, "python_mode": "store313", "wheels_by_python": wheels_by_python, "version": version, "built": datetime.now(UTC).isoformat(), "build_id": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16], "expanded_bytes": expanded, "files": hashes}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for name in ("core.py", "instalador.py"):
        shutil.copy2(project / "tools/installer" / name, folder / name)
    with zipfile.ZipFile(root / "Instalador_Python313.zip", "w", zipfile.ZIP_STORED) as archive:
        archive.write(root / "instalar.py", "instalar.py")
        archive.write(root / "INSTALAR_PYTHON313.md", "LEEME.md")
        for path, name in files(folder, "instalar_datos"):
            archive.write(path, name)
    package = root / "Instalador_Python313.zip"
    with package.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    package.with_suffix(".zip.sha256").write_text(checksum + "  " + package.name + "\n", encoding="utf-8")
    print("Paquete listo:", package)


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[3])
