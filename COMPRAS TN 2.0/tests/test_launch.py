from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace


def load_launcher():
    path = Path(__file__).resolve().parents[1] / 'launch.py'
    spec = importlib.util.spec_from_file_location('project_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_double_click_selects_pythonw_with_installed_dependencies(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'isolated-local'))
    executable = tmp_path / '.venvs/compras-tn/Scripts/pythonw.exe'
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(launcher.Path, 'home', lambda: tmp_path)
    monkeypatch.setattr(sys, 'prefix', sys.base_prefix)
    monkeypatch.setattr(sys, 'executable', 'C:/Python/pythonw.exe')
    monkeypatch.setattr(sys, 'argv', ['COMPRAS 3.0.pyw', '--example'])
    monkeypatch.setenv('PYTHONPATH', 'broken-global-packages')
    calls = []
    monkeypatch.setattr(launcher.subprocess, 'call', lambda command, **kwargs: calls.append((command, kwargs)) or 0)
    assert launcher.main() == 0
    command, kwargs = calls[0]
    assert command[0] == str(executable)
    assert Path(command[1]).name == 'run.py'
    assert command[2:] == ['--example']
    assert 'PYTHONPATH' not in kwargs['env']


def test_activated_environment_starts_app_without_relaunch(tmp_path, monkeypatch):
    launcher = load_launcher()
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'isolated-local'))
    monkeypatch.setattr(sys, 'prefix', str(tmp_path / 'active-venv'))
    monkeypatch.setitem(sys.modules, 'compras_tn.__main__', SimpleNamespace(main=lambda: 7))
    monkeypatch.setattr(launcher.subprocess, 'call', lambda *a, **k: (_ for _ in ()).throw(AssertionError('Unexpected relaunch')))
    assert launcher.main() == 7