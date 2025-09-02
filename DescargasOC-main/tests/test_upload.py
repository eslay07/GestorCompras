import requests
import requests_mock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'descargas_oc'))
from seafile_client import SeafileClient


def test_upload_with_mock(tmp_path):
    file_path = tmp_path / 'f.txt'
    file_path.write_text('data')
    with requests_mock.Mocker() as m:
        m.post('http://srv/api2/auth-token/', json={'token': 'abc'})
        repo_id = '11111111-2222-3333-4444-555555555555'
        m.get(f'http://srv/api2/repos/{repo_id}/upload-link/?p=/', text='"http://link"')
        m.post('http://link', text='ok')
        cli = SeafileClient('http://srv', 'u', 'p')
        resp = cli.upload_file(repo_id, str(file_path))
    assert resp == 'ok'


