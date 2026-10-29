from __future__ import annotations

import os
from pathlib import Path

import pytest

from compras_tn.infrastructure.db import Database, Repositories
from compras_tn.paths import AppPaths

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths.from_root(tmp_path / "appdata")
    paths.ensure()
    return paths


@pytest.fixture
def database(app_paths: AppPaths) -> Database:
    value = Database(app_paths.database, PROJECT_ROOT)
    value.upgrade()
    yield value
    value.close()


@pytest.fixture
def repositories(database: Database) -> Repositories:
    return Repositories(database)
