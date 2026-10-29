import importlib.util
import json
import sqlite3
import shutil
import subprocess
import sys
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from compras_tn.domain.models import Supplier
from compras_tn.infrastructure.instance import DataLease
from compras_tn.infrastructure.portable import export_profile, merge_profile


def core_module():
    path = Path(__file__).resolve().parents[1] / "tools/installer/core.py"
    spec = importlib.util.spec_from_file_location("installer_core", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_store_installer_rejects_other_python_before_changing_data(tmp_path, monkeypatch):
    module = core_module()
    installer = module.Installer(tmp_path, tmp_path / "program")
    monkeypatch.setattr(installer, "verify", lambda: {"python_mode": "store313"})
    monkeypatch.setattr(module.sys, "version_info", (3, 12, 14))
    with pytest.raises(RuntimeError, match="Python 3.13"):
        installer.install()
    assert not installer.program.exists()


def test_store_launcher_uses_approved_interpreter_and_isolated_release(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools/installer/launcher.py"
    spec = importlib.util.spec_from_file_location("installer_launcher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "__file__", str(tmp_path / "abrir.py"))
    (tmp_path / "current.json").write_text(json.dumps({"release": "test", "data": "my-data", "python_mode": "store313", "python": "approved-store-python"}))
    calls = []
    monkeypatch.setattr(module.subprocess, "call", lambda args, **kwargs: calls.append((args, kwargs)) or 0)
    module.main()
    assert calls[0][0] == ["approved-store-python", "-I", "-X", "utf8", str(tmp_path / "releases/test/bootstrap.py"), "--module", "compras_tn"]
    assert calls[0][1]["env"]["COMPRAS_TN_DATA_DIR"] == "my-data"


def test_bootstrap_prefers_release_libraries_over_machine_packages(tmp_path):
    source = Path(__file__).resolve().parents[1] / "tools/installer/bootstrap.py"
    shutil.copy2(source, tmp_path / "bootstrap.py")
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages/pip.py").write_text("print('RELEASE-PIP')")
    output = subprocess.check_output([sys.executable, "-I", str(tmp_path / "bootstrap.py"), "--module", "pip"], text=True)
    assert output.strip() == "RELEASE-PIP"


def test_offline_wheels_validate_versions_and_relocate_library_data(tmp_path):
    module = core_module()
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    with zipfile.ZipFile(wheels / "demo.whl", "w") as archive:
        archive.writestr("demo-1.dist-info/METADATA", "Name: Demo\nVersion: 1\n")
        archive.writestr("demo.py", "VALUE = 1")
        archive.writestr("demo-1.data/purelib/extra.py", "VALUE = 2")
        archive.writestr("demo-1.data/scripts/demo.py", "print(1)")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("Demo==2\n")
    packages = tmp_path / "packages"
    with pytest.raises(RuntimeError, match="Demo==2"):
        module.install_binary_wheels(wheels, packages, requirements, lambda value: None)
    assert not packages.exists()
    requirements.write_text("Demo==1\n")
    module.install_binary_wheels(wheels, packages, requirements, lambda value: None)
    assert (packages / "extra.py").read_text() == "VALUE = 2"
    assert (packages / "Scripts/demo.py").is_file()


def test_offline_wheels_reject_escaping_members(tmp_path):
    module = core_module()
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    with zipfile.ZipFile(wheels / "demo.whl", "w") as archive:
        archive.writestr("demo-1.dist-info/METADATA", "Name: Demo\nVersion: 1\n")
        archive.writestr("../outside.py", "malicious")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("Demo==1\n")
    with pytest.raises(ValueError, match="Ruta no válida"):
        module.install_binary_wheels(wheels, tmp_path / "packages", requirements, lambda value: None)
    assert not (tmp_path / "outside.py").exists()


def test_profile_keeps_supplier_addresses_without_credentials_or_mail_history(database, repositories):
    repositories.save(Supplier(name="CEFEIND", ruc="0012345678901", email_primary="ventas@example.com", email_secondary="otro@example.com", nickname="CEFEIND"))
    repositories.set("email", "smtp_server", "smtp.example.com")
    with closing(sqlite3.connect(database.path)) as connection, connection:
        connection.execute("INSERT INTO settings VALUES (?,?,?,?)", ("email", "smtp_password", json.dumps("TOP-SECRET"), "2026-10-13"))
    repositories.set("google", "google_creds", "secret-service-account.json")
    repositories.set("quotation_headers", "account", {"Subject": "PRIVATE-MAIL"})
    repositories.set("documents", "types", [{"id": "custom", "name": "Certificado", "words": ["certificado"], "password": "TOP-SECRET"}])
    profile = export_profile(database.path)
    encoded = json.dumps(profile)
    assert "TOP-SECRET" not in encoded and "PRIVATE-MAIL" not in encoded
    assert "secret-service-account" not in encoded
    assert profile["tables"]["suppliers"][0]["email_primary"] == "ventas@example.com"
    assert profile["tables"]["suppliers"][0]["email_secondary"] == "otro@example.com"
    assert set(profile["tables"]) <= {"suppliers", "assignments", "email_templates", "workflow_definitions"}


def test_merge_is_idempotent_and_keeps_existing_computer_settings_and_suppliers(database, repositories):
    repositories.save(Supplier(name="MI PROVEEDOR", ruc="0012345678901", email_primary="local@example.com"))
    repositories.set("email", "smtp_server", "local.example.com")
    profile = {"format": 1, "tables": {"suppliers": [{"name": "OTRO NOMBRE", "ruc": "0012345678901", "email_primary": "source@example.com"}, {"name": "NUEVO", "ruc": "0022345678901", "email_primary": "new@example.com"}]}, "settings": [{"namespace": "email", "key": "smtp_server", "value": "source.example.com"}, {"namespace": "quotations", "key": "root", "value": "E:/BD_TN"}]}
    merge_profile(database.path, profile)
    again = merge_profile(database.path, profile)
    assert again["added"] == 0
    assert len(repositories.list()) == 2
    supplier = next(item for item in repositories.list() if item.ruc == "0012345678901")
    assert supplier.name == "MI PROVEEDOR" and supplier.email_primary == "local@example.com"
    assert repositories.get("email", "smtp_server") == "local.example.com"
    assert repositories.get("quotations", "root") == "E:/BD_TN"




def test_unpack_rejects_path_traversal(tmp_path):
    core = core_module()
    archive = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../outside.txt", "bad")
    with pytest.raises(ValueError):
        core.unpack(archive, tmp_path / "safe")
    assert not (tmp_path / "outside.txt").exists()


def test_backup_captures_uncheckpointed_wal(tmp_path):
    core = core_module()
    database = tmp_path / "live.db"
    with closing(sqlite3.connect(database)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE suppliers(name TEXT)")
        writer.execute("INSERT INTO suppliers VALUES ('KEEP ME')")
        writer.commit()
        core.snapshot(database, tmp_path / "backup.db")
    with closing(sqlite3.connect(tmp_path / "backup.db")) as restored:
        assert restored.execute("SELECT name FROM suppliers").fetchone()[0] == "KEEP ME"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows byte lease")
def test_active_application_blocks_installer_lease(tmp_path):
    lease = DataLease(tmp_path)
    try:
        with pytest.raises(RuntimeError):
            DataLease(tmp_path)
    finally:
        lease.close()
    DataLease(tmp_path).close()


def test_ambiguous_data_locations_are_not_chosen_automatically(tmp_path, monkeypatch):
    core = core_module()
    monkeypatch.delenv("COMPRAS_TN_DATA_DIR", raising=False)
    for folder in ("ComprasTN/2.0", "Packages/PythonSoftwareFoundation.Python.3.13/LocalCache/Local/ComprasTN/2.0"):
        directory = tmp_path / folder
        directory.mkdir(parents=True)
        (directory / "compras_tn.db").touch()
    with pytest.raises(RuntimeError, match="varias bases"):
        core.data_location(tmp_path, tmp_path / "program")


def test_portable_types_merge_and_legacy_boolean_conversion(database, repositories):
    repositories.set("documents", "types", [{"id": "existing", "name": "Mi tipo", "words": ["mi tipo"]}])
    profile = {"format": 1, "tables": {}, "settings": [{"namespace": "documents", "key": "types", "value": [{"id": "existing", "name": "Renombrado", "words": ["otro"]}, {"id": "new", "name": "Nuevo", "words": ["nuevo"]}]}, {"namespace": "automation", "key": "actua_headless", "value": "False"}]}
    merge_profile(database.path, profile)
    merge_profile(database.path, profile)
    assert repositories.get("automation", "actua_headless") is False
    assert [row["name"] for row in repositories.get("documents", "types")] == ["Mi tipo", "Nuevo"]


def test_legacy_supplier_without_email_remains_readable(database, repositories):
    profile = {"format": 1, "settings": [], "tables": {"suppliers": [{"ruc": "0012345678901", "name": "Sin correo", "email_primary": ""}]}}
    merge_profile(database.path, profile)
    assert repositories.list()[0].name == "Sin correo"
    assert repositories.list()[0].email_primary == ""


def test_installer_window_stays_open_after_success_and_retry_error(tmp_path, monkeypatch):
    import tkinter as tk
    from tkinter import messagebox, ttk
    folder = Path(__file__).resolve().parents[1] / "tools/installer"
    monkeypatch.syspath_prepend(str(folder))
    spec = importlib.util.spec_from_file_location("installer_gui_test", folder / "instalador.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    errors = []
    monkeypatch.setattr(messagebox, "showerror", lambda title, detail, **kwargs: errors.append(detail))
    attempts = []
    def install(_self, **kwargs):
        attempts.append(1)
        if len(attempts) == 2:
            raise RuntimeError("ERROR EXACTO DE PRUEBA")
        return {"program": "test"}
    monkeypatch.setattr(module.Installer, "install", install)
    original_open = Path.open
    def controlled_open(path, *args, **kwargs):
        if len(attempts) >= 2 and path.suffix == ".log":
            raise OSError("DISCO LLENO SIMULADO")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", controlled_open)
    original = tk.Tk
    observed = []
    def children(widget):
        for child in widget.winfo_children():
            yield child
            yield from children(child)
    def root():
        window = original()
        window.withdraw()
        def begin():
            next(child for child in children(window) if isinstance(child, ttk.Button) and child.cget("text") == "Instalar / actualizar").invoke()
        def verify():
            values = [str(window.getvar(child.cget("textvariable"))) for child in children(window) if isinstance(child, ttk.Label) and child.cget("textvariable")]
            observed.extend(values)
            observed.append(window.winfo_exists())
            window.destroy()
        def verify_success():
            observed.extend(str(window.getvar(child.cget("textvariable"))) for child in children(window) if isinstance(child, ttk.Label) and child.cget("textvariable"))
        window.after(20, begin)
        window.after(250, verify_success)
        window.after(350, begin)
        window.after(800, verify)
        return window
    monkeypatch.setattr(tk, "Tk", root)
    module.gui(tmp_path)
    assert observed[-1] == 1
    assert errors and "ERROR EXACTO DE PRUEBA" in errors[0]
    assert "INSTALADO CORRECTAMENTE" in observed


def test_workflow_policy_is_migrated_without_duplicate_imports(database, repositories, tmp_path):
    from compras_tn.domain.models import WorkflowDefinition
    from compras_tn.infrastructure.db import Database, Repositories
    repositories.save_workflow(WorkflowDefinition(name='Carga ordenes', stop_on_error=False))
    profile=export_profile(database.path)
    target=Database(tmp_path/'target.db', Path(__file__).resolve().parents[1])
    target.upgrade()
    try:
        dest=Repositories(target)
        dest.save_workflow(WorkflowDefinition(name='Carga ordenes', stop_on_error=True))
        merge_profile(target.path, profile)
        merge_profile(target.path, profile)
        flows=dest.list_workflows()
        assert len(flows)==2
        assert {f.stop_on_error for f in flows}=={False,True}
    finally:
        target.close()

def test_installer_accepts_matching_python_wheel_set_before_lock(tmp_path, monkeypatch):
    module = core_module()
    installer = module.Installer(tmp_path, tmp_path / 'program')
    monkeypatch.setattr(installer, 'verify', lambda: {'python_mode': 'store313', 'wheels_by_python': {'3.12': 'wheels312.zip', '3.13': 'wheels.zip'}, 'built': '2026'})
    monkeypatch.setattr(module.sys, 'version_info', (3, 12, 14))
    def selected(*args):
        raise RuntimeError('MATCHING-PYTHON-SELECTED')
    monkeypatch.setattr(module, 'data_location', selected)
    with pytest.raises(RuntimeError, match='MATCHING-PYTHON-SELECTED'):
        installer.install()


def test_installed_launcher_reports_child_failure(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'tools/installer/launcher.py'
    spec = importlib.util.spec_from_file_location('installer_launcher_failure', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '__file__', str(tmp_path / 'abrir.py'))
    (tmp_path / 'current.json').write_text(json.dumps({'release': 'test', 'data': 'test-data', 'python_mode': 'store313', 'python': 'approved-python'}))
    monkeypatch.setattr(module.subprocess, 'call', lambda *args, **kwargs: 1)
    with pytest.raises(RuntimeError, match='startup.log'):
        module.main()
    assert (tmp_path / 'startup.log').exists()
