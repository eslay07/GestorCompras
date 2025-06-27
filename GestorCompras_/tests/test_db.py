import os
import tempfile

import pytest

from gestorcompras.services import db


def setup_temp_db(monkeypatch):
    tmp_dir = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmp_dir.name, 'test.db')
    monkeypatch.setattr(db, 'DB_PATH', db_path, raising=False)
    monkeypatch.setattr(db, 'DB_DIR', tmp_dir.name, raising=False)
    db.init_db()
    return tmp_dir


def test_get_suppliers_returns_inserted_suppliers(monkeypatch):
    tmp = setup_temp_db(monkeypatch)
    try:
        db.add_supplier('Prov', '123', 'a@b.com', 'c@d.com')
        suppliers = db.get_suppliers()
        assert suppliers == [(1, 'Prov', '123', 'a@b.com', 'c@d.com')]
    finally:
        tmp.cleanup()
