"""Build an offline, single-file Windows installer from explicit allowlisted inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path


def pack(target, sources):
    total = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for source, name in sources:
            archive.write(source, name)
            total += source.stat().st_size
    return total


def files(root, prefix="", exclude=()):
    for file in sorted(root.rglob("*")):
        if file.is_file() and not any(part in {"__pycache__", ".git", *exclude} for part in file.relative_to(root).parts) and file.suffix != ".pyc":
            yield file, (Path(prefix) / file.relative_to(root)).as_posix()


def build(project, output, runtime, wheels, browser):
    from compras_tn.infrastructure.portable import export_profile
    from compras_tn.paths import AppPaths
    output.mkdir(parents=True, exist_ok=True)
    requirements = []
    development = {"mypy", "pytest", "pytest-cov", "pytest-qt", "ruff"}
    for line in (project / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if line and line.split("==")[0].casefold() not in development:
            requirements.append(line)
    require_path = output / "installer-requirements.txt"
    require_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
    app = []
    for folder in ("src", "alembic", "tools/installer"):
        app.extend(files(project / folder, "app/" + folder))
    for name in ("alembic.ini", "pyproject.toml", "README.md", "COTIZACIONES_Y_ADJUNTOS.md", "launch.py", "run.py", "COMPRAS 3.0.pyw"):
        app.append((project / name, "app/" + name))
    app.append((require_path, "app/installer-requirements.txt"))
    expanded = pack(output / "application.zip", app)
    runtime_files = []
    for folder in ("DLLs", "Lib"):
        runtime_files.extend(files(runtime / folder, folder, ("site-packages",)))
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        runtime_files.append((runtime / name, name))
    expanded += pack(output / "python.zip", runtime_files)
    expanded += pack(output / "wheels.zip", [(wheel, wheel.name) for wheel in sorted(wheels.glob("*.whl"))])
    import shutil
    for name in ("chrome.zip", "chromedriver.zip"):
        shutil.copy2(browser / name, output / name)
        with zipfile.ZipFile(browser / name) as archive:
            expanded += sum(item.file_size for item in archive.infolist())
    profile = {"format": 1, "tables": {}, "settings": []}
    (output / "profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    names = ["application.zip", "python.zip", "wheels.zip", "chrome.zip", "chromedriver.zip", "profile.json"]
    hashes = {}
    for name in names:
        digest = hashlib.sha256()
        with (output / name).open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        hashes[name] = digest.hexdigest()
    version = re.search(r'version = "([^"]+)"', (project / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    manifest = {"format": 1, "version": version, "built": datetime.now(UTC).isoformat(), "build_id": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16], "expanded_bytes": expanded, "files": hashes}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Paquete preparado. Proveedores:", len(profile["tables"]["suppliers"]), "Archivos:", len(app), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--browser", type=Path, required=True)
    args = parser.parse_args()
    build(args.project.resolve(), args.output.resolve(), args.runtime.resolve(), args.wheels.resolve(), args.browser.resolve())
