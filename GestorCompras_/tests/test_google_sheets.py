import types
import sys

sys.modules.setdefault('gspread', types.SimpleNamespace())
sys.modules.setdefault('google.oauth2.service_account', types.SimpleNamespace(Credentials=types.SimpleNamespace(from_service_account_file=lambda *a, **k: None)))

from gestorcompras.services import google_sheets

class DummyWS:
    def __init__(self, data):
        self._data = data
    def get_all_values(self):
        return self._data

class DummyClient:
    def __init__(self, data):
        self.data = data
    def open_by_key(self, key):
        class Wrapper:
            def __init__(self, d):
                self.d = d
            def worksheet(self, name):
                return DummyWS(self.d)
        return Wrapper(self.data)


def test_read_report_filters_aprobadas(monkeypatch):
    data = [
        ["Hoja", "Tarea", "Artículo", "Orden de Compra", "Proveedor", "Estado Aprobación"],
        ["H1", "123", "Item", "OC1", "Prov", "Aprobado"],
        ["H1", "124", "Item2", "OC2", "Prov", "Pendiente"],
    ]
    monkeypatch.setattr(google_sheets, "get_client", lambda path: DummyClient(data))
    rows = google_sheets.read_report("creds", "sheet", "hoja")
    assert rows == [
        {
            "Hoja": "H1",
            "Tarea": "123",
            "Artículo": "Item",
            "Orden de Compra": "OC1",
            "Proveedor": "Prov",
            "Estado Aprobación": "Aprobado",
        }
    ]
