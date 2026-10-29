from types import SimpleNamespace

import pytest
import requests

from compras_tn.infrastructure.delivery import fingerprint
from compras_tn.infrastructure.seafile import SeafileRemote


def remote_with_file(monkeypatch, path, *, exists=True, identical=True):
    remote = SeafileRemote(SimpleNamespace(), 'https://telcodrive.test', 'secret', 'repo')
    monkeypatch.setattr(remote, 'list_dir', lambda _: [{'name': path.name}] if exists else [])
    monkeypatch.setattr(remote, 'content_hash', lambda _: fingerprint(path) if identical else 'different')
    return remote


def test_identical_file_never_posts(tmp_path, monkeypatch):
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'PDF')
    remote = remote_with_file(monkeypatch, path)
    assert remote.upload_verified(path, '/BD_TN/ENERO/12345') == 'identical'


def test_different_content_does_not_overwrite(tmp_path, monkeypatch):
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'PDF')
    remote = remote_with_file(monkeypatch, path, identical=False)
    with pytest.raises(ValueError, match='Conflicto'):
        remote.upload_verified(path, '/BD_TN/ENERO/12345')


def test_timeout_after_upload_is_verified_before_retry(tmp_path, monkeypatch):
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'PDF')
    remote = remote_with_file(monkeypatch, path, exists=False)
    monkeypatch.setattr(remote, 'request', lambda *_args, **_kw:
                        SimpleNamespace(json=lambda: 'https://telcodrive.test/upload'))
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout('timeout')
    remote.session.post = post
    assert remote.upload_verified(path, '/BD_TN/ENERO/12345') == 'uploaded'
    assert len(calls) == 1
    assert calls[0]['data']['replace'] == '0'


def test_external_link_is_rejected():
    remote = SeafileRemote(None, 'https://telcodrive.test', 'secret', 'repo')
    with pytest.raises(ValueError):
        remote.check_link('http://other.test/upload')
