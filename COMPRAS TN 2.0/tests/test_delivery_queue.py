from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from compras_tn.infrastructure.automation.downloads import SeleniumOrderDownloadGateway
from compras_tn.infrastructure.delivery import MONTHS, DeliveryQueue, task_folder


class Remote:
    def __init__(self):
        self.dirs = {'/BD_TN': [{'type': 'dir', 'name': 'ENERO'}],
                     '/BD_TN/ENERO': [{'type': 'dir', 'name': '123456 - Nodo'}]}
        self.uploads = []
        self.files = {}
    def list_dir(self, path):
        return self.dirs.get(path, [])
    def ensure_dir(self, path):
        from pathlib import PurePosixPath
        parent, name = str(PurePosixPath(path).parent), PurePosixPath(path).name
        if path not in self.dirs:
            self.dirs.setdefault(parent, []).append({'type': 'dir', 'name': name})
            self.dirs[path] = []
    def upload_verified(self, path, folder):
        key = (path.name, folder)
        if self.files.get(key) == path.read_bytes():
            return 'identical'
        self.files[key] = path.read_bytes()
        self.uploads.append(key)
        return 'uploaded'


class Gateway:
    def __init__(self):
        self.remote = Remote()
    @contextmanager
    def connection(self, *_):
        yield self.remote
    @contextmanager
    def batch(self):
        yield


@pytest.fixture
def queue(database, repositories):
    repositories.set('downloads', 'seafile_repo_id', '')
    repositories.set('downloads', 'seafile_parent_dir', '/BD_TN')
    return DeliveryQueue(database, Gateway(), repositories)


def test_task_folder_exact_boundary():
    assert task_folder('123456 - NODO', '123456')
    assert task_folder('123456', '123456')
    assert not task_folder('1234567 - NODO', '123456')
    assert not task_folder('OTRA 123456', '123456')


def test_old_month_and_restart_do_not_upload_twice(queue, tmp_path):
    path = tmp_path / '374100 - PROVEEDOR.pdf'
    path.write_bytes(b'%PDF-test')
    identifier = queue.enqueue(path, '123456')
    assert queue.deliver(identifier, None)['status'] == 'uploaded'
    assert queue.gateway.remote.uploads[0][1] == '/BD_TN/ENERO/123456 - Nodo'
    assert queue.enqueue(path, '123456') == identifier
    resumed = DeliveryQueue(queue.database, queue.gateway, queue.settings)
    resumed.deliver(identifier, None)
    assert len(queue.gateway.remote.uploads) == 1
    assert path.exists()


def test_multiple_folders_require_selection(queue, tmp_path):
    queue.gateway.remote.dirs['/BD_TN/ENERO'].append({'type': 'dir', 'name': '123456 - Otra'})
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'test')
    identifier = queue.enqueue(path, '123456')
    assert queue.deliver(identifier, None)['status'] == 'conflict'
    assert not queue.gateway.remote.uploads
    queue.update(identifier, remote_dir='/BD_TN/ENERO/123456 - Otra', status='pending')
    assert queue.deliver(identifier, None)['status'] == 'uploaded'


def test_missing_task_stays_local(queue, tmp_path):
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'test')
    identifier = queue.enqueue(path, '')
    assert queue.deliver(identifier, None)['status'] == 'review'
    assert not queue.gateway.remote.uploads


def test_new_folder_contains_only_number(queue, tmp_path):
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'test')
    identifier = queue.enqueue(path, '987654')
    result = queue.deliver(identifier, None)
    assert result['status'] == 'uploaded'
    assert result['remote_dir'].split('/')[-1] == '987654'
    assert result['remote_dir'].split('/')[-2] in MONTHS


def test_failure_can_retry_without_downloading(queue, tmp_path, monkeypatch):
    path = tmp_path / 'oc.pdf'
    path.write_bytes(b'test')
    identifier = queue.enqueue(path, '123456')
    original = queue.gateway.remote.upload_verified
    def fail(*_):
        raise TimeoutError('Sin conexión')
    monkeypatch.setattr(queue.gateway.remote, 'upload_verified', fail)
    assert queue.deliver(identifier, None)['status'] == 'pending'
    monkeypatch.setattr(queue.gateway.remote, 'upload_verified', original)
    assert queue.retry(None)[0]['status'] == 'uploaded'


def test_multitask_download_is_copied_to_each_month_task_folder(repositories, tmp_path):
    root = tmp_path / "BD_TN"
    first = root / "Septiembre" / "19558554854 - Quito"
    second = root / "Septiembre" / "19558554855"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    source = tmp_path / "373627 - PROVEEDOR.pdf"
    source.write_bytes(b"same-order")
    repositories.set("downloads", "carpeta_analizar", str(root))
    gateway = SeleniumOrderDownloadGateway(
        repositories,
        SimpleNamespace(invalidate_inventory=lambda: None),
    )

    destinations = gateway._organize_for_tasks(
        source, "bienes", ["19558554854", "19558554855"]
    )

    assert [item["task_number"] for item in destinations] == [
        "19558554854",
        "19558554855",
    ]
    assert {item["month"] for item in destinations} == {"Septiembre"}
    assert all(Path(item["pdf_path"]).read_bytes() == b"same-order" for item in destinations)
    assert not source.exists()


def test_supply_upload_creates_fixed_folder_without_task(queue, tmp_path):
    path = tmp_path / "375135 - PROVEEDOR.pdf"
    path.write_bytes(b"%PDF-supply")
    identifier = queue.enqueue_supply(path)
    result = queue.deliver(identifier, None)
    assert result["status"] == "uploaded"
    assert result["remote_dir"] == "/BD_TN/ABASTECIMIENTO"
    assert queue.gateway.remote.uploads == [(path.name, "/BD_TN/ABASTECIMIENTO")]
    assert path.exists()
    assert queue.enqueue_supply(path) == identifier
    DeliveryQueue(queue.database, queue.gateway, queue.settings).deliver(identifier, None)
    assert len(queue.gateway.remote.uploads) == 1


def test_supply_upload_failure_keeps_pdf_pending(queue, tmp_path, monkeypatch):
    path = tmp_path / "375135 - PROVEEDOR.pdf"
    path.write_bytes(b"%PDF-supply")
    identifier = queue.enqueue_supply(path)
    def fail(*args):
        raise OSError("Servidor desconectado")
    monkeypatch.setattr(queue.gateway.remote, "upload_verified", fail)
    assert queue.deliver(identifier, None)["status"] == "pending"
    assert path.exists()


def test_supply_redownload_rechecks_deleted_remote_file(queue, tmp_path):
    path = tmp_path / "123456 - PROVEEDOR.pdf"
    path.write_bytes(b"%PDF-supply")
    identifier = queue.enqueue_supply(path)
    assert queue.deliver(identifier, None)["status"] == "uploaded"
    queue.gateway.remote.files.clear()
    assert queue.enqueue_supply(path) == identifier
    assert queue.deliver(identifier, None)["status"] == "uploaded"
    assert len(queue.gateway.remote.uploads) == 2
