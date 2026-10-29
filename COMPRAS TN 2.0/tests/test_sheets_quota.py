from collections import deque
from types import SimpleNamespace

import pytest
from gspread.exceptions import APIError
from gspread.http_client import HTTPClient

from compras_tn.infrastructure import sheets_transport as transport


def api_error(status, retry_after='0'):
    return APIError(SimpleNamespace(status_code=status, headers={'Retry-After':retry_after},
        json=lambda:{'error':{'code':status, 'message':'quota test', 'status':'RESOURCE_EXHAUSTED'}}))


@pytest.mark.parametrize('status', [429, 503])
def test_retry_api_error_repeats_http_only_without_regenerating(status, monkeypatch):
    calls, waits = [], []
    def request(self, method, endpoint, **kwargs):
        calls.append((method, endpoint, kwargs))
        if len(calls) == 1:
            raise api_error(status, '7')
        return 'ok'
    monkeypatch.setattr(HTTPClient, 'request', request)
    monkeypatch.setattr(transport, 'reserve_request', lambda *args:None)
    monkeypatch.setattr(transport, 'pause', lambda seconds, message:waits.append((seconds, message)))
    client = object.__new__(transport.QuotaHTTPClient)
    assert client.request('get', 'sheets/test', params={'ranges':['G1','O1']}) == 'ok'
    assert len(calls) == 2 and calls[0] == calls[1]
    assert waits[0][0] >= 7
    assert str(status) in waits[0][1]


def test_nonretryable_api_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(HTTPClient, 'request', lambda *args, **kwargs: (_ for _ in ()).throw(api_error(403)))
    monkeypatch.setattr(transport, 'reserve_request', lambda *args:None)
    monkeypatch.setattr(transport, 'pause', lambda *args:pytest.fail('Do not retry permission failures'))
    with pytest.raises(APIError):
        object.__new__(transport.QuotaHTTPClient).request('get', 'sheets/test')


def test_shared_quota_budget_waits_before_46th_read_with_separate_write_budget(monkeypatch):
    now, waits = [0.0], []
    monkeypatch.setattr(transport, '_windows', {'read':deque(), 'write':deque()})
    monkeypatch.setattr(transport.time, 'monotonic', lambda:now[0])
    def pause(seconds, message):
        waits.append(seconds)
        now[0] += seconds
    monkeypatch.setattr(transport, 'pause', pause)
    for _ in range(45):
        transport.reserve_request('get', 'sheets/test')
    transport.reserve_request('post', 'sheets/test:batchUpdate')
    assert not waits
    transport.reserve_request('get', 'sheets/test')
    assert waits == [61.0]
    assert len(transport._windows['read']) == 1


def test_quota_wait_is_cancellable_and_reports_progress():
    events = []
    with transport.sheets_context(lambda *args:events.append(args), lambda:True):
        with pytest.raises(RuntimeError, match='cancelada'):
            transport.pause(60, 'Esperando cuota')
    assert events[0][2] == 'Esperando cuota'


def test_persistent_429_has_bounded_retries(monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        raise api_error(429)
    monkeypatch.setattr(HTTPClient, 'request', request)
    monkeypatch.setattr(transport, 'reserve_request', lambda *args:None)
    monkeypatch.setattr(transport, 'pause', lambda *args:None)
    with pytest.raises(APIError):
        object.__new__(transport.QuotaHTTPClient).request('get', 'sheets/test')
    assert len(calls) == 8


def test_writeback_and_approvers_use_constant_reads_for_fifty_rows(monkeypatch):
    from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
    rows = [['', '', '166698853', '', '', '', '', '', 'S/N', 'GTN', 'PERSONA', 'PROYECTO']]
    rows += [['', f'A{i}', f'MATERIAL {i}', 1, 'PROVEEDOR', 2, ''] for i in range(50)]
    draft, = GoogleSheetsGateway.parse_purchase_order_rows(rows, start_row=7346)
    cells, reads, writes = {}, [], []
    class Worksheet:
        col_count = 15
        def get(self, name, **kwargs):
            reads.append(('get', name))
            assert name.startswith('A7346:L')
            result = []
            for index, raw in enumerate(rows, 7346):
                row = list(raw) + [''] * max(0, 12-len(raw))
                row[6] = cells.get(f'G{index}', row[6])
                result.append(row)
            return result
        def batch_get(self, names, **kwargs):
            reads.append(('batch_get', tuple(names)))
            return [[[cells.get(name, '')]] for name in names]
        def batch_update(self, updates, **kwargs):
            writes.append(updates)
            for update in updates:
                cells[update['range']] = update['values'][0][0]
    gateway = GoogleSheetsGateway(SimpleNamespace(get=lambda *args: args[-1]))
    monkeypatch.setattr(gateway, '_worksheet', lambda *args, **kwargs:Worksheet())
    gateway.record_purchase_order(draft, '378517')
    assert len(reads) == 4  # data + all G before/after + independent data confirmation
    before = len(reads)
    gateway.record_approvers(draft, '378517', ['PERSONA UNO'])
    assert len(reads)-before == 6
    assert len(writes) == 2
    assert cells['G7347'] == cells['G7396'] == '378517'
    assert cells['O7347'] == cells['O7396'] == 'PERSONA UNO'


def test_worksheet_metadata_is_reused_only_within_batch(monkeypatch):
    from compras_tn.infrastructure import google_sheets as sheets
    gateway = sheets.GoogleSheetsGateway(SimpleNamespace(get=lambda namespace, key, default=None:
        {'google_creds':'test.json','google_sheet_id':'sheet-test'}.get(key,default)))
    calls = []
    monkeypatch.setattr(sheets.Credentials, 'from_service_account_file', lambda *args, **kwargs:object())
    def authorize(credentials, **kwargs):
        calls.append(kwargs['http_client'])
        return SimpleNamespace(set_timeout=lambda timeout:None,
            open_by_key=lambda key:SimpleNamespace(worksheet=lambda name:object()))
    monkeypatch.setattr(sheets.gspread, 'authorize', authorize)
    with gateway.batch():
        assert gateway._worksheet('GENERAL') is gateway._worksheet('GENERAL')
        assert len(calls) == 1
    gateway._worksheet('GENERAL')
    assert len(calls) == 2
    assert all(client is transport.QuotaHTTPClient for client in calls)


def test_approval_429_retry_does_not_resend_approval_or_generate_an_order(repositories,tmp_path,monkeypatch):
    from test_application_services import _facade
    from test_purchase_order_preload import _draft
    facade,*_ = _facade(repositories,tmp_path)
    client=object.__new__(transport.QuotaHTTPClient)
    requests, sent, synchronized = [], [], []
    def request(self, method, endpoint, **kwargs):
        requests.append(1)
        if len(requests)==1:
            raise api_error(429)
        return 'ok'
    monkeypatch.setattr(HTTPClient,'request',request)
    monkeypatch.setattr(transport,'reserve_request',lambda *args:None)
    monkeypatch.setattr(transport,'pause',lambda *args:None)
    def record(draft,number,names):
        assert client.request('get','sheets/test')=='ok'
        synchronized.append((number,names))
    facade.sheets=SimpleNamespace(record_approvers=record)
    def send(number,stage,state):
        sent.append(number)
        stage('read',['APROBADOR'])
        return ['APROBADOR']
    facade._approve_saved_oc(_draft(),'378517',SimpleNamespace(send_and_read_approval=send))
    assert sent==['378517']
    assert len(requests)==2
    assert synchronized==[('378517',['APROBADOR'])]
    receipt=repositories.get('oc_approvals',facade._oc_scope()+'378517',{})
    assert receipt['state']=='synced'


def test_writeback_does_not_restart_an_exhausted_transport_retry_budget(monkeypatch):
    from compras_tn.infrastructure.google_sheets import GoogleSheetsGateway
    from test_purchase_order_preload import _draft
    gateway=GoogleSheetsGateway(SimpleNamespace(get=lambda *args:args[-1]))
    error=api_error(429)
    error.sheets_retries_exhausted=True
    calls=[]
    def attempt(*args):
        calls.append(1)
        raise error
    monkeypatch.setattr(gateway,'_record_purchase_order_attempt',attempt)
    with pytest.raises(APIError):
        gateway.record_purchase_order(_draft(),'378517')
    assert len(calls)==1
