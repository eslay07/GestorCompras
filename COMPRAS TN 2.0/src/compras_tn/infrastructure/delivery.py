"""Durable, non-destructive delivery of prepared PDFs to a task folder."""
from __future__ import annotations

import builtins
import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import text

from compras_tn.application.ports import SettingsRepository
from compras_tn.domain.models import SessionCredentials
from compras_tn.infrastructure.db.database import Database

MONTHS = ('ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
          'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE')


def task_folder(name: str, number: str) -> bool:
    return bool(re.fullmatch(re.escape(number) + r'(?:\s*[-–—]\s*.+|\s+.+)?', name))


def fingerprint(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class DeliveryQueue:
    def __init__(self, database: Database, gateway: Any, settings: SettingsRepository) -> None:
        self.database, self.gateway, self.settings = database, gateway, settings

    def enqueue(self, path: Path, task: str, *, mismatch: bool = False, recheck: bool = False) -> int:
        repo = str(self.settings.get('downloads', 'seafile_repo_id', '')).strip()
        root = str(self.settings.get('downloads', 'seafile_parent_dir', '/BD_TN') or '/BD_TN')
        if not root.startswith('/') or '..' in PurePosixPath(root).parts:
            raise ValueError('La raíz remota debe ser una ruta absoluta sin ..')
        digest = fingerprint(path)
        identity = hashlib.sha256(
            f'{repo}|{root}|{task}|{path.name}|{digest}'.encode()
        ).hexdigest()
        message = 'El número de tarea falta o contradice el documento.' if mismatch or not task else ''
        with self.database.session() as session:
            session.execute(text('''INSERT INTO oc_transfers
                (identity,pdf_path,sha256,task_number,repo_id,root_dir,status,message)
                VALUES (:identity,:path,:digest,:task,:repo,:root,:status,:message)
                ON CONFLICT(identity) DO UPDATE SET pdf_path=excluded.pdf_path,
                status=CASE WHEN :recheck AND oc_transfers.status IN ('uploaded','identical')
                            THEN excluded.status ELSE oc_transfers.status END,
                message=CASE WHEN :recheck AND oc_transfers.status IN ('uploaded','identical')
                             THEN excluded.message ELSE oc_transfers.message END'''),
                dict(identity=identity, path=str(path.resolve()), digest=digest, task=task, repo=repo,
                     root=root, status='review' if message else 'pending', message=message, recheck=recheck))
            return int(session.execute(text('SELECT id FROM oc_transfers WHERE identity=:identity'),
                                       {'identity': identity}).scalar_one())

    def enqueue_supply(self, path: Path) -> int:
        """Abastecimiento uses a fixed folder and does not require a task."""
        return self.enqueue(path, "ABASTECIMIENTO", recheck=True)

    def list(self, pending_only: bool = True) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = 'SELECT * FROM oc_transfers'
            if pending_only:
                query += " WHERE status NOT IN ('uploaded','identical')"
            return [dict(row) for row in session.execute(text(query + ' ORDER BY id')).mappings()]

    def update(self, identifier: int, **values: Any) -> None:
        allowed = {'status', 'message', 'remote_dir', 'candidates', 'task_number'}
        if not values or not set(values) <= allowed:
            raise ValueError('Campos de transferencia inválidos')
        with self.database.session() as session:
            session.execute(text('UPDATE oc_transfers SET ' +
                ','.join(f'{key}=:{key}' for key in values) +
                ',updated_at=CURRENT_TIMESTAMP WHERE id=:id'), {**values, 'id': identifier})

    def deliver(self, identifier: int, credentials: SessionCredentials) -> dict[str, Any]:
        record = next(row for row in self.list(False) if row['id'] == identifier)
        if record['status'] in {'uploaded', 'identical'}:
            return record
        try:
            number = record['task_number']
            supply = number == 'ABASTECIMIENTO'
            if record['status'] == 'review' or (not supply and not re.fullmatch(r'\d{4,14}', number)):
                raise ValueError(record['message'] or 'Indique un número de tarea válido.')
            path = Path(record['pdf_path'])
            if fingerprint(path) != record['sha256']:
                raise ValueError('El PDF local cambió desde su preparación; revise el archivo antes de subir.')
            with self.gateway.connection(credentials, record['repo_id']) as remote:
                root = record['root_dir']
                if supply:
                    chosen = str(PurePosixPath(root) / 'ABASTECIMIENTO')
                    remote.ensure_dir(chosen)
                    self.update(identifier, remote_dir=chosen, status='uploading', message='Verificando destino')
                    status = remote.upload_verified(path, chosen)
                    self.update(identifier, status=status, message='Contenido remoto verificado', candidates='[]')
                    return next(row for row in self.list(False) if row['id'] == identifier)
                months = remote.list_dir(root)
                matches = []
                for month in months:
                    if month.get('type') != 'dir' or month['name'].upper() not in MONTHS:
                        continue
                    month_path = str(PurePosixPath(root) / month['name'])
                    for folder in remote.list_dir(month_path):
                        if folder.get('type') == 'dir' and task_folder(folder['name'], number):
                            matches.append(str(PurePosixPath(month_path) / folder['name']))
                chosen = record['remote_dir']
                if chosen and chosen not in matches:
                    raise ValueError('El destino seleccionado ya no corresponde a la tarea.')
                if len(matches) > 1 and not chosen:
                    self.update(identifier, status='conflict', candidates=json.dumps(matches),
                                message='Hay varias carpetas; seleccione un destino.')
                    return next(row for row in self.list(False) if row['id'] == identifier)
                if not matches:
                    month = MONTHS[datetime.now(timezone(timedelta(hours=-5))).month - 1]
                    actual = next((entry['name'] for entry in months
                                   if entry.get('type') == 'dir' and entry['name'].upper() == month), month)
                    month_path = str(PurePosixPath(root) / actual)
                    remote.ensure_dir(month_path)
                    chosen = str(PurePosixPath(month_path) / number)
                    remote.ensure_dir(chosen)
                chosen = chosen or matches[0]
                self.update(identifier, remote_dir=chosen, status='uploading', message='Verificando destino')
                status = remote.upload_verified(path, chosen)
                self.update(identifier, status=status, message='Contenido remoto verificado', candidates='[]')
        except Exception as exc:
            from compras_tn.security import sanitize_text
            self.update(identifier, status='review' if record['status'] == 'review' else 'pending',
                        message=sanitize_text(str(exc)))
        return next(row for row in self.list(False) if row['id'] == identifier)

    def retry(self, credentials: SessionCredentials, progress: Callable[[int, int, str], None] | None = None,
              cancelled: Callable[[], bool] | None = None) -> builtins.list[dict[str, Any]]:
        with self.gateway.batch():
            return self._retry(credentials, progress, cancelled)

    def _retry(self, credentials: SessionCredentials, progress: Callable[[int, int, str], None] | None = None,
               cancelled: Callable[[], bool] | None = None) -> builtins.list[dict[str, Any]]:
        rows = self.list()
        results = []
        for index, row in enumerate(rows):
            if cancelled and cancelled():
                break
            results.append(self.deliver(row['id'], credentials))
            if progress:
                progress(index + 1, len(rows), f"Telcodrive: tarea {row['task_number']}")
        return results
