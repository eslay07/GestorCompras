from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from alembic import command


class Database:
    def __init__(self, path: Path, project_root: Path | None = None):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.project_root = (project_root or Path(__file__).resolve().parents[4]).resolve()
        self.engine: Engine = create_engine(
            f"sqlite:///{self.path.as_posix()}",
            future=True,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = connection.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        self.sessions = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    def upgrade(self) -> None:
        # SQLite's backup API includes committed WAL pages; copying only the
        # .db file can silently lose data while the app is running.
        import sqlite3
        from datetime import datetime

        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        check_config = Config(str(self.project_root / 'alembic.ini'))
        check_config.set_main_option('script_location', str(self.project_root / 'alembic'))
        head = ScriptDirectory.from_config(check_config).get_current_head()
        with self.engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if current == head:
            return
        if self.path.exists() and self.path.stat().st_size and current:
            backup = self.path.with_name(
                self.path.name + datetime.now().strftime('.%Y%m%d-%H%M%S-%f.bak')
            )
            with sqlite3.connect(str(self.path)) as source:
                with sqlite3.connect(str(backup)) as target:
                    source.backup(target)
        config = Config(str(self.project_root / "alembic.ini"))
        config.set_main_option("script_location", str(self.project_root / "alembic"))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.path.as_posix()}")
        command.upgrade(config, "head")

    def close(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
