from gestorcompras.logic import despacho_logic
from gestorcompras.services import db


def test_obtener_resumen_orden(monkeypatch):
    # patch funciones que buscan pdf y extraen info
    monkeypatch.setattr(despacho_logic, 'buscar_archivo_mas_reciente', lambda o: ('/tmp/file.pdf', 'FOO'))
    monkeypatch.setattr(despacho_logic, 'extraer_info_de_pdf', lambda p: ('123', '555'))
    monkeypatch.setattr(despacho_logic, 'get_suppliers', lambda: [(1, 'Prov', '123', 'a@b.com', 'b@b.com')])

    info, error = despacho_logic.obtener_resumen_orden('OC1')
    assert error is None
    assert info['orden'] == 'OC1'
    assert info['tarea'] == '555'
    assert info['folder_name'] == 'FOO'
    assert info['emails'] == ['a@b.com', 'b@b.com']
    assert info['pdf_path'] == '/tmp/file.pdf'
