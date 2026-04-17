"""Tests para el repositorio de correos escaneados de Actua. Tareas."""
import pytest

from gestorcompras.services import db
from gestorcompras.data import actua_correos_repo


@pytest.fixture(autouse=True)
def _clean_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()
    yield


def _sample(msg_id="msg-001", task="123456"):
    return {
        "message_id": msg_id,
        "raw_hash": f"hash-{msg_id}",
        "task_number": task,
        "asunto": "Test subject",
        "from": "sender@test.com",
        "body": "Test body",
    }


def test_upsert_insert():
    record_id = actua_correos_repo.upsert(_sample())
    assert record_id is not None and record_id > 0


def test_upsert_dedupe_by_message_id():
    id1 = actua_correos_repo.upsert(_sample("msg-dup"))
    id2 = actua_correos_repo.upsert(_sample("msg-dup"))
    assert id1 == id2


def test_upsert_dedupe_by_raw_hash():
    item1 = {"raw_hash": "hash-dup", "task_number": "111", "asunto": "A", "from": "x"}
    item2 = {"raw_hash": "hash-dup", "task_number": "111", "asunto": "B", "from": "y"}
    id1 = actua_correos_repo.upsert(item1)
    id2 = actua_correos_repo.upsert(item2)
    assert id1 == id2


def test_list_by_task():
    actua_correos_repo.upsert(_sample("m1", "T100"))
    actua_correos_repo.upsert(_sample("m2", "T200"))
    results = actua_correos_repo.list_by_task("T100")
    assert len(results) == 1
    assert results[0]["task_number"] == "T100"


def test_list_recent():
    actua_correos_repo.upsert(_sample("m1"))
    actua_correos_repo.upsert(_sample("m2"))
    results = actua_correos_repo.list_recent(limit=10)
    assert len(results) == 2


def test_delete():
    actua_correos_repo.upsert(_sample("del-me"))
    assert actua_correos_repo.delete("del-me") is True
    assert actua_correos_repo.delete("del-me") is False


def test_clear():
    actua_correos_repo.upsert(_sample("c1"))
    actua_correos_repo.upsert(_sample("c2"))
    count = actua_correos_repo.clear()
    assert count == 2
    assert actua_correos_repo.list_recent() == []


def test_upsert_requires_id_or_hash():
    with pytest.raises(ValueError, match="message_id o raw_hash"):
        actua_correos_repo.upsert({"task_number": "123"})
