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


def test_process_order_without_pdf(monkeypatch):
    """Se envía correo usando proveedor directo cuando no se adjunta PDF."""
    called = {}

    def fake_send(sess, subject, html, ctx, attachment_path=None, signature_path=None, cc_key=None):
        called['attachment'] = attachment_path
        called['cc_key'] = cc_key

    monkeypatch.setattr(despacho_logic, 'send_email_custom', fake_send)
    monkeypatch.setattr(despacho_logic, 'get_email_template_by_name', lambda n: (1, n, '<b>{{orden}}</b>', None))
    monkeypatch.setattr(despacho_logic, 'get_supplier_by_name', lambda n: (1, n, '123', 'to@x.com', ''))

    msg = despacho_logic.process_order({'address': 'from@x.com'}, 'OC1', include_pdf=False,
                                        template_name='F1', cc_key='EMAIL_CC_SEGUIMIENTO', provider_name='Prov')

    assert '✅' in msg
    assert called['attachment'] is None
    assert called['cc_key'] == 'EMAIL_CC_SEGUIMIENTO'
