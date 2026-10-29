"""Transactional per-user installation. Only standard-library dependencies."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def unpack(archive, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination) or ".." in Path(member.filename).parts:
                raise ValueError("El paquete contiene una ruta de extracción no válida.")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("El paquete contiene enlaces no permitidos.")
        source.extractall("\\\\?\\" + str(destination) if sys.platform == "win32" else destination)


def snapshot(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as original, closing(sqlite3.connect(destination)) as copy:
        original.backup(copy)
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("La copia de seguridad de la base está dañada.")


def install_binary_wheels(wheels, packages, requirements, log):
    """Offline recovery for Windows pip temporary-directory failures.

    The bundle contains only pre-resolved binary wheels; no build scripts run.
    CLI wrappers are unnecessary: this application launches modules directly.
    """
    from email.parser import Parser
    normalize = lambda name: re.sub(r"[-_.]+", "-", name).lower()
    archives = sorted(wheels.glob("*.whl"))
    available = {}
    for wheel in archives:
        with zipfile.ZipFile(wheel) as archive:
            metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
            metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
            available[normalize(metadata["Name"])] = metadata["Version"]
    for line in requirements.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, version = line.split("==", 1)
        if available.get(normalize(name)) != version:
            raise RuntimeError("Falta una librería de la versión requerida: " + line)
    for wheel in archives:
        log("Instalando librería local: " + wheel.name)
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                parts = Path(member.filename).parts
                if not parts or ".." in parts or Path(member.filename).is_absolute() or ((member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError("Ruta no válida dentro de la librería: " + wheel.name)
                if parts[0].endswith(".data") and len(parts) > 2:
                    scheme = parts[1]
                    prefix = {"purelib": (), "platlib": (), "scripts": ("Scripts",), "headers": ("include",), "data": ()}.get(scheme)
                    if prefix is None:
                        raise ValueError("Distribución wheel no compatible: " + scheme)
                    parts = (*prefix, *parts[2:])
                target = packages.joinpath(*parts).resolve()
                if not target.is_relative_to(packages.resolve()):
                    raise ValueError("Ruta de librería fuera de la instalación")
                extended = Path("\\\\?\\" + str(target)) if sys.platform == "win32" else target
                if member.is_dir():
                    extended.mkdir(parents=True, exist_ok=True)
                else:
                    extended.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, extended.open("wb") as destination:
                        shutil.copyfileobj(source, destination)


def atomic_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def data_location(local: Path, program: Path):
    pointer = program / "current.json"
    if pointer.is_file():
        return Path(json.loads(pointer.read_text(encoding="utf-8"))["data"]).resolve()
    override = os.environ.get("COMPRAS_TN_DATA_DIR")
    if override:
        return Path(override).resolve()
    candidates = {p.parent.resolve() for p in (local / "Packages").glob("PythonSoftwareFoundation.Python.*/LocalCache/Local/ComprasTN/2.0/compras_tn.db")}
    standard = local / "ComprasTN/2.0"
    if (standard / "compras_tn.db").is_file():
        candidates.add(standard.resolve())
    if len(candidates) > 1:
        raise RuntimeError("Hay varias bases COMPRAS TN. Defina COMPRAS_TN_DATA_DIR con la carpeta correcta antes de instalar; no se modificó ninguna.")
    return next(iter(candidates)) if candidates else standard.resolve()


class Installer:
    def __init__(self, bundle: Path, program: Path | None = None, log=print):
        self.bundle = bundle.resolve()
        self.local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")).resolve()
        self.program = (program or self.local / "ComprasTN/programa").resolve()
        self.log = log
        self.step = "Preparación"

    def run_command(self, arguments, cwd, env=None, timeout=600):
        self.log("Ejecutando: " + " ".join(str(value) for value in arguments))
        if getattr(sys, "frozen", False):
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        completed = subprocess.run([str(value) for value in arguments], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=0x08000000)
        if completed.stdout:
            self.log(completed.stdout.strip())
        if completed.returncode:
            raise RuntimeError(f"Proceso terminado con código {completed.returncode}.\n{completed.stdout[-8000:]}")
        return completed.stdout

    def verify(self):
        manifest = json.loads((self.bundle / "manifest.json").read_text(encoding="utf-8"))
        for name, expected in manifest["files"].items():
            path = (self.bundle / name).resolve()
            if not path.is_relative_to(self.bundle) or not path.is_file() or digest(path) != expected:
                raise RuntimeError(f"El paquete está incompleto o dañado: {name}. Extraiga nuevamente el paquete completo del instalador.")
        return manifest

    def install(self, smoke=True, shortcuts=True):
        if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
            raise RuntimeError("Este instalador requiere Windows de 64 bits (x64).")
        self.step = "Verificación del paquete"
        manifest = self.verify()
        if manifest.get("python_mode") == "store313" and f"{sys.version_info[0]}.{sys.version_info[1]}" not in manifest.get("wheels_by_python", {"3.13": "wheels.zip"}):
            raise RuntimeError("Este paquete requiere Python " + " o ".join(manifest.get("wheels_by_python", {"3.13": "wheels.zip"})) + ". No se descargará ni ejecutará otro Python.")
        if sys.getwindowsversion().major < 10:
            raise RuntimeError("Se necesita Windows 10 o posterior para esta versión.")
        self.program.mkdir(parents=True, exist_ok=True)
        pointer = self.program / "current.json"
        old_config = json.loads(pointer.read_text(encoding="utf-8")) if pointer.is_file() else None
        if old_config and old_config.get("built", "") > manifest["built"]:
            raise RuntimeError("La PC tiene una versión más nueva que este instalador. Use el paquete más reciente; no se aplicó una degradación.")
        data = data_location(self.local, self.program)
        data.mkdir(parents=True, exist_ok=True)
        # Same byte lock as the program, without importing its libraries.
        import msvcrt
        lock = (data / "application.lock").open("a+b")
        lock.seek(0, 2)
        if not lock.tell():
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            lock.close()
            raise RuntimeError("COMPRAS TN está abierto o hay otro instalador en curso. Ciérrelo y vuelva a intentar.") from None
        try:
            return self._install(manifest, data, pointer, old_config, smoke, shortcuts)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            lock.close()

    def _install(self, manifest, data, pointer, old_config, smoke, shortcuts):
        required = manifest["expanded_bytes"] * 2 + 500 * 1024 * 1024
        if shutil.disk_usage(self.program).free < required:
            raise RuntimeError(f"Espacio insuficiente. Se necesitan aproximadamente {required / 1024**3:.1f} GB libres en la unidad de instalación.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        backup = data / "installer-backups" / stamp
        backup.mkdir(parents=True)
        database = data / "compras_tn.db"
        self.step = "Respaldo de los datos existentes"
        if database.is_file():
            snapshot(database, backup / "compras_tn.db")
        if old_config:
            atomic_json(backup / "current.json", old_config)
        releases = self.program / "releases"
        releases.mkdir(exist_ok=True)
        release = releases / (manifest["build_id"][:8] + "-" + uuid.uuid4().hex[:8])
        self.step = "Extracción de Python y de la aplicación"
        self.log("Instalación por usuario, sin modificar PATH ni solicitar administrador.")
        unpack(self.bundle / "application.zip", release)
        store = manifest.get("python_mode") == "store313"
        if not store:
            unpack(self.bundle / "python.zip", release / "runtime")
        wheels = release / "wheels"
        wheel_archive = manifest.get("wheels_by_python", {}).get(f"{sys.version_info[0]}.{sys.version_info[1]}", "wheels.zip") if store else "wheels.zip"
        unpack(self.bundle / wheel_archive, wheels)
        unpack(self.bundle / "chrome.zip", release / "browser")
        unpack(self.bundle / "chromedriver.zip", release / "browser")
        runtime = release / "runtime"
        if store:
            packages = release / "packages"
            shutil.copy2(release / "app/tools/installer/bootstrap.py", release / "bootstrap.py")
        else:
            paths = [runtime, runtime / "Lib", runtime / "DLLs", runtime / "Lib/site-packages", release / "app/src"]
            (runtime / "python312._pth").write_text("\n".join("\\\\?\\" + str(path.resolve()) for path in paths) + "\nimport site\n", encoding="utf-8")
            packages = runtime / "Lib/site-packages"
        packages.mkdir(parents=True, exist_ok=True)
        pip_wheel = next(wheels.glob("pip-*.whl"))
        unpack(pip_wheel, packages)
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
            env.pop(key, None)
        env["PYTHONUTF8"] = "1"
        env["PATH"] = str(runtime) + os.pathsep + env.get("PATH", "")
        env["COMPRAS_TN_CHROME"] = str(release / "browser/chrome-win64/chrome.exe")
        env["COMPRAS_TN_CHROMEDRIVER"] = str(release / "browser/chromedriver-win64/chromedriver.exe")
        python = Path(sys.executable) if store else runtime / "python.exe"
        prefix = [python, "-I", "-X", "utf8", release / "bootstrap.py"] if store else [python]
        self.step = "Instalación de todas las librerías desde el paquete"
        if store:
            install_binary_wheels(wheels, packages, release / "app/installer-requirements.txt", self.log)
            self.step = "Verificación de dependencias directas y transitivas"
            self.run_command(prefix + ["--module", "pip", "check"], release, env)
        else:
            self.run_command(prefix + ["-m", "pip", "install", "--no-index", "--no-compile", "--disable-pip-version-check", "--no-warn-script-location", "--find-links", wheels, "--target", "\\\\?\\" + str(packages), "--upgrade", "-r", release / "app/installer-requirements.txt"], release, env)
        self.step = "Verificación de librerías, interfaz y navegador"
        helper = release / "app/tools/installer/deployment.py"
        if smoke:
            self.run_command(prefix + (["--script", helper] if store else [helper]) + ["--smoke"], release, env, timeout=180)
        self.step = "Actualización segura de configuraciones y proveedores"
        staged = backup / "prepared-data"
        staged.mkdir()
        if database.is_file():
            snapshot(database, staged / "compras_tn.db")
        seed = self.bundle / "profile.json"
        command = prefix + (["--script", helper] if store else [helper]) + ["--data", staged, "--project", release / "app", "--seed", seed]
        self.run_command(command, release, env)
        prepared = staged / "compras_tn.db"
        self.step = "Activación de la versión nueva"
        if database.is_file():
            with closing(sqlite3.connect(database, timeout=5)) as connection:
                busy = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
                if busy:
                    raise RuntimeError("La base sigue en uso por una versión anterior. Cierre todas las versiones de COMPRAS TN.")
                connection.execute("PRAGMA journal_mode=DELETE")
        try:
            os.replace(prepared, database)
            shutil.copy2(release / "app/tools/installer/launcher.py", self.program / "launcher.py")
            shutil.copy2(self.program / "launcher.py", self.program / "abrir.py")
            atomic_json(pointer, {"release": release.name, "built": manifest["built"], "build_id": manifest["build_id"], "data": str(data), "python_mode": "store313" if store else "portable312", "python": str(python), "python_version": platform.python_version()})
        except Exception:
            if (backup / "compras_tn.db").is_file():
                recovery = data / "installer-restore.tmp"
                snapshot(backup / "compras_tn.db", recovery)
                os.replace(recovery, database)
            if old_config:
                atomic_json(pointer, old_config)
            raise
        self.step = "Creación del acceso directo"
        if shortcuts:
            env["INSTALLER_LINK_TARGET"] = str(python if store else python.with_name("pythonw.exe"))
            env["INSTALLER_LAUNCHER"] = str(self.program / "launcher.py")
            env["INSTALLER_PROGRAM"] = str(self.program)
            script = '$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "COMPRAS TN.lnk")); $s.TargetPath=$env:INSTALLER_LINK_TARGET; $s.Arguments="`"$env:INSTALLER_LAUNCHER`""; $s.WorkingDirectory=$env:INSTALLER_PROGRAM; $s.Save()'
            try:
                self.run_command([Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], self.program, env, timeout=30)
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                self.log(f"AVISO: instalado, pero no se pudo crear el acceso directo: {exc}")
        self.log("INSTALADO CORRECTAMENTE\nPrograma: " + str(self.program) + "\nDatos conservados: " + str(data) + "\nRespaldo: " + str(backup))
        self.log("En una PC nueva debe ingresar las contraseñas y configurar las credenciales de Google. Revise las rutas de carpetas si cambian de equipo.")
        return {"program": str(self.program), "data": str(data), "backup": str(backup), "release": str(release)}
