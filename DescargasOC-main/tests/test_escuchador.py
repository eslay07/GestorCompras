import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from descargas_oc import escuchador  # noqa: E402


def _setup_temp_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(escuchador, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(escuchador, 'PROCESADOS_FILE', tmp_path / 'procesados.txt')
    monkeypatch.setattr(escuchador, 'LAST_UIDL_FILE', tmp_path / 'last_uidl.txt')
    monkeypatch.setattr(escuchador, 'ORDENES_TMP', tmp_path / 'ordenes_tmp.json')


class DummyPOP:
    def __init__(self, uidl_value: str):
        self.uidl_value = uidl_value

    def user(self, _):
        return b'+OK'

    def pass_(self, _):
        return b'+OK'

    def uidl(self):
        return b'+OK', [f'1 {self.uidl_value}'.encode()], None

    def quit(self):
        return b'+OK'


@pytest.fixture
def cfg():
    return SimpleNamespace(
        pop_server='server',
        pop_port=995,
        usuario='usuario@telconet.ec',
        password='secreto',
        batch_size=5,
        max_threads=1,
    )


def test_valid_sender_without_data_not_marked_processed(tmp_path, monkeypatch, cfg):
    _setup_temp_paths(tmp_path, monkeypatch)
    uidl_value = 'UID123'

    raw_email = (
        'Subject: Aviso\r\n'
        'From: "NAF" <naf@telconet.ec>\r\n'
        '\r\n'
        'Mensaje sin información de orden\r\n'
    ).encode('utf-8')

    monkeypatch.setattr(escuchador, '_descargar_mensaje', lambda num, c: (uidl_value, raw_email))

    def fake_pop(server, port):  # noqa: ARG001 - firmas compatibles
        return DummyPOP(uidl_value)

    monkeypatch.setattr(escuchador.poplib, 'POP3_SSL', fake_pop)

    ordenes, ultimo = escuchador.buscar_ocs(cfg)

    assert ordenes == []
    assert ultimo == uidl_value
    assert not escuchador.PROCESADOS_FILE.exists()


def test_valid_order_detected_from_default_sender(tmp_path, monkeypatch, cfg):
    _setup_temp_paths(tmp_path, monkeypatch)
    uidl_value = 'UID456'

    raw_email = (
        'Subject: SISTEMA NAF: Notificacion AUTORIZACION ORDEN COMPRA No 12345\r\n'
        'From: Notificaciones NAF <naf@telconet.ec>\r\n'
        '\r\n'
        'Fecha Autorizacion: 05/06/2024\r\n'
        'Fecha Orden: 06/06/2024\r\n'
        'Proveedor Ejemplo\r\n'
    ).encode('utf-8')

    monkeypatch.setattr(escuchador, '_descargar_mensaje', lambda num, c: (uidl_value, raw_email))

    def fake_pop(server, port):  # noqa: ARG001 - firmas compatibles
        return DummyPOP(uidl_value)

    monkeypatch.setattr(escuchador.poplib, 'POP3_SSL', fake_pop)

    ordenes, ultimo = escuchador.buscar_ocs(cfg)

    assert len(ordenes) == 1
    assert ordenes[0]['numero'] == '12345'
    assert ultimo == uidl_value
    assert escuchador.ORDENES_TMP.exists()


def test_invalid_sender_is_marked_processed(tmp_path, monkeypatch, cfg):
    _setup_temp_paths(tmp_path, monkeypatch)
    uidl_value = 'UID789'

    raw_email = (
        'Subject: SISTEMA NAF: Notificacion AUTORIZACION ORDEN COMPRA No 99999\r\n'
        'From: Alerta <otro@dominio.com>\r\n'
        '\r\n'
        'Fecha Autorizacion: 01/02/2024\r\n'
    ).encode('utf-8')

    monkeypatch.setattr(escuchador, '_descargar_mensaje', lambda num, c: (uidl_value, raw_email))

    def fake_pop(server, port):  # noqa: ARG001 - firmas compatibles
        return DummyPOP(uidl_value)

    monkeypatch.setattr(escuchador.poplib, 'POP3_SSL', fake_pop)

    ordenes, _ = escuchador.buscar_ocs(cfg)

    assert ordenes == []
    assert escuchador.PROCESADOS_FILE.exists()
    assert escuchador.PROCESADOS_FILE.read_text().strip() == uidl_value


def test_additional_sender_from_config(tmp_path, monkeypatch, cfg):
    _setup_temp_paths(tmp_path, monkeypatch)
    cfg.remitente_adicional = 'otro@dominio.com;extra@dominio.com'
    uidl_value = 'UID999'

    raw_email = (
        'Subject: SISTEMA NAF: Notificacion AUTORIZACION ORDEN COMPRA No 55555\r\n'
        'From: Equipo <OTRO@DOMINIO.COM>\r\n'
        '\r\n'
        'Fecha Autorizacion: 10/11/2024\r\n'
    ).encode('utf-8')

    monkeypatch.setattr(escuchador, '_descargar_mensaje', lambda num, c: (uidl_value, raw_email))

    def fake_pop(server, port):  # noqa: ARG001 - firmas compatibles
        return DummyPOP(uidl_value)

    monkeypatch.setattr(escuchador.poplib, 'POP3_SSL', fake_pop)

    ordenes, _ = escuchador.buscar_ocs(cfg)

    assert len(ordenes) == 1
    assert ordenes[0]['numero'] == '55555'
    assert not escuchador.PROCESADOS_FILE.exists()


def test_reply_to_header_counts_as_valid_sender(tmp_path, monkeypatch, cfg):
    _setup_temp_paths(tmp_path, monkeypatch)
    uidl_value = 'UID444'

    raw_email = (
        'Subject: SISTEMA NAF: Notificacion AUTORIZACION ORDEN COMPRA No 77777\r\n'
        'From: Plataforma <notificaciones@telconet.ec>\r\n'
        'Reply-To: naf@telconet.ec\r\n'
        '\r\n'
        'Fecha Autorizacion: 03/04/2024\r\n'
    ).encode('utf-8')

    monkeypatch.setattr(escuchador, '_descargar_mensaje', lambda num, c: (uidl_value, raw_email))

    def fake_pop(server, port):  # noqa: ARG001
        return DummyPOP(uidl_value)

    monkeypatch.setattr(escuchador.poplib, 'POP3_SSL', fake_pop)

    ordenes, _ = escuchador.buscar_ocs(cfg)

    assert len(ordenes) == 1
    assert ordenes[0]['numero'] == '77777'
    assert not escuchador.PROCESADOS_FILE.exists()


def test_extracts_provider_from_html_body():
    asunto = 'SISTEMA NAF: Notificacion AUTORIZACION ORDEN COMPRA No 140144463'
    cuerpo = (
        '<p><strong>Proveedor:</strong> '
        '<strong>004465 - SALAZAR RUIZ MARCELO VLADIMIR</strong> '
        'con <strong>Fecha de Vencimiento:</strong> 16/10/2025</p>'
        '<br><p><strong>Observacion:</strong> '
        'TAREA #140144463//PEDIDO:S/N//DETALLE</p>'
    )

    numero, _, _, proveedor, tarea = escuchador.extraer_datos(asunto, cuerpo)

    assert numero == '140144463'
    assert proveedor == '004465 - SALAZAR RUIZ MARCELO VLADIMIR'
    assert tarea == '140144463'
