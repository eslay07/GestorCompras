import importlib
import sys
import types

import pytest


class DummyText:
    def __init__(self):
        self.messages = []

    def insert(self, index, text):  # pragma: no cover - almacenamiento sencillo
        self.messages.append(text)

    def see(self, index):  # pragma: no cover - sin efecto en pruebas
        pass

    def after(self, delay, callback):
        callback()


class DummyLabel:
    def __init__(self):
        self.text = ""

    def config(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs["text"]


class DummyConfig:
    def __init__(self):
        self.usuario = "user@telconet.ec"
        self.password = "secret"
        self.carpeta_destino_local = "dest"
        self.carpeta_analizar = "analizar"
        self.seafile_url = "https://seafile"
        self.seafile_repo_id = "repo"
        self.correo_reporte = "report@telconet.ec"
        self.headless = True

    def validate(self):  # pragma: no cover - sin lógica de validación
        return True


@pytest.fixture
def ui_module(monkeypatch):
    fake_pdf = types.ModuleType("PyPDF2")
    fake_pdf.PdfReader = object
    sys.modules["PyPDF2"] = fake_pdf
    for mod in [
        "descargas_oc.mover_pdf",
        "descargas_oc.selenium_modulo",
        "descargas_oc.ui",
    ]:
        sys.modules.pop(mod, None)
    ui_mod = importlib.import_module("descargas_oc.ui")
    yield ui_mod
    sys.modules.pop("PyPDF2", None)


@pytest.fixture(autouse=True)
def reset_lock(ui_module):
    if ui_module.scanning_lock.locked():
        ui_module.scanning_lock.release()
    yield
    if ui_module.scanning_lock.locked():
        ui_module.scanning_lock.release()


def test_uidl_kept_pending_when_some_orders_fail(monkeypatch, ui_module):
    monkeypatch.setattr(ui_module, "Config", DummyConfig)
    monkeypatch.setattr(
        ui_module,
        "buscar_ocs",
        lambda cfg: (
            [
                {"uidl": "UID1", "numero": "1001"},
                {"uidl": "UID1", "numero": "1002"},
                {"uidl": "UID2", "numero": "2001"},
            ],
            "UID_LAST",
        ),
    )
    monkeypatch.setattr(
        ui_module,
        "descargar_oc",
        lambda ordenes, headless: (["1001", "2001"], ["1002"], ["OC 1002: error"]),
    )
    monkeypatch.setattr(ui_module, "enviar_reporte", lambda *args, **kwargs: True)

    calls = []

    def fake_registrar(uidls, ultimo):
        calls.append((uidls, ultimo))

    monkeypatch.setattr(ui_module, "registrar_procesados", fake_registrar)
    monkeypatch.setattr(ui_module, "cargar_ultimo_uidl", lambda: "PREV")
    monkeypatch.setattr(ui_module.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(ui_module.messagebox, "showinfo", lambda *a, **k: None)

    text = DummyText()
    label = DummyLabel()

    ui_module.realizar_escaneo(text, label)

    assert calls == [(["UID2"], None)]
    assert "PREV" in label.text
