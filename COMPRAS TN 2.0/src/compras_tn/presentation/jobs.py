from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QMessageBox

from compras_tn.domain.models import JobStatus, OperationResult, utc_now
from compras_tn.security import sanitize_text

LOGGER = logging.getLogger(__name__)


class JobSignals(QObject):
    started = Signal(str)
    progress = Signal(str, int, int, str)
    finished = Signal(str, object, bool)
    failed = Signal(str, str)
    confirmation = Signal(str, str, object)


class ManagedJob(QRunnable):
    def __init__(
        self,
        job_id: str,
        callback: Callable[[Callable[[int, int, str], None], Callable[[], bool]], Any],
        signals: JobSignals,
        cancel_event: threading.Event,
    ):
        super().__init__()
        # El administrador conserva la propiedad hasta recibir la señal final;
        # evita carreras de autoeliminación al cancelar trabajos en cola.
        self.setAutoDelete(False)
        self.job_id = job_id
        self.callback = callback
        self.signals = signals
        self.cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        if self.cancel_event.is_set():
            self.signals.finished.emit(self.job_id, self._cancelled_result(), True)
            return
        self.signals.started.emit(self.job_id)
        try:
            def progress(current, total, text):
                self.signals.progress.emit(self.job_id, max(0, current), max(0, total), sanitize_text(text))

            def confirm_cycle(message):
                answer = {'event': threading.Event(), 'approved': False}
                self.signals.confirmation.emit(self.job_id, sanitize_text(message), answer)
                while not answer['event'].wait(0.1):
                    if self.cancel_event.is_set():
                        return False
                return answer['approved'] and not self.cancel_event.is_set()

            progress.confirm_cycle = confirm_cycle
            result = self.callback(progress, self.cancel_event.is_set)
            cancelled_at_finish = self.cancel_event.is_set()
            self.signals.finished.emit(self.job_id, result, cancelled_at_finish)
        except BaseException as exc:
            # No se registra el texto de la excepción: algunas librerías
            # incluyen credenciales en él. La ubicación y el tipo bastan para
            # el diagnóstico técnico; la UI recibe un mensaje saneado.
            frames = traceback.extract_tb(exc.__traceback__)
            location = " -> ".join(
                f"{frame.name}:{frame.lineno}" for frame in frames[-6:]
            )
            LOGGER.error(
                "Trabajo %s terminó con %s (%s)",
                self.job_id,
                type(exc).__name__,
                location or "sin traza",
            )
            message = sanitize_text(str(exc)).strip() or type(exc).__name__
            self.signals.failed.emit(self.job_id, message)

    @staticmethod
    def _cancelled_result() -> OperationResult:
        return OperationResult(
            status=JobStatus.CANCELLED,
            finished_at=utc_now(),
            message="Trabajo cancelado antes de iniciar.",
        )


class JobManager(QObject):
    job_started = Signal(str)
    job_progress = Signal(str, int, int, str)
    job_finished = Signal(str, object)
    job_failed = Signal(str, str)
    job_state_changed = Signal(str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(10)
        self._signals = JobSignals(self)
        self._signals.started.connect(self._started)
        self._signals.progress.connect(self.job_progress)
        self._signals.finished.connect(self._complete)
        self._signals.failed.connect(self._fail)
        self._signals.confirmation.connect(self._confirm_cycle)
        self._cancellations: dict[str, threading.Event] = {}
        self._jobs: dict[str, ManagedJob] = {}
        self._queued: OrderedDict[str, ManagedJob] = OrderedDict()
        self._allocations: dict[str, tuple[str, ...]] = {}
        self._states: OrderedDict[str, str] = OrderedDict()
        self._capacities = {"selenium": 1, "scan": 1, "email": 4, "default": 4}
        self._usage = {name: 0 for name in self._capacities}

    def submit(
        self,
        kind: str,
        callback: Callable[[Callable[[int, int, str], None], Callable[[], bool]], Any],
    ) -> str:
        job_id = uuid.uuid4().hex
        event = threading.Event()
        resources = {
            "scan_selenium": ("scan", "selenium"),
        }.get(kind, (kind if kind in self._capacities else "default",))
        job = ManagedJob(job_id, callback, self._signals, event)
        self._cancellations[job_id] = event
        self._jobs[job_id] = job
        self._queued[job_id] = job
        self._allocations[job_id] = resources
        self._set_state(job_id, "queued")
        self._dispatch()
        return job_id

    @Slot(str, str, object)
    def _confirm_cycle(self, job_id, message, answer):
        event = self._cancellations.get(job_id)
        try:
            if event is None or event.is_set():
                return
            dialog = QMessageBox(QApplication.activeWindow())
            dialog.setWindowTitle("Pasos anteriores pendientes")
            dialog.setIcon(QMessageBox.Warning)
            dialog.setText(message)
            proceed = dialog.addButton("Sí, continuar de todas formas", QMessageBox.AcceptRole)
            cancel = dialog.addButton("Cancelar", QMessageBox.RejectRole)
            dialog.setDefaultButton(cancel)
            dialog.setEscapeButton(cancel)
            timer = QTimer(dialog)
            timer.timeout.connect(lambda: dialog.reject() if event.is_set() else None)
            timer.start(100)
            dialog.exec()
            answer['approved'] = dialog.clickedButton() == proceed and not event.is_set()
        finally:
            answer['event'].set()

    def cancel(self, job_id: str) -> None:
        event = self._cancellations.get(job_id)
        if event is None:
            return
        event.set()
        if job_id in self._queued:
            self._complete(job_id, ManagedJob._cancelled_result(), True)

    @Slot(str, object, bool)
    def _complete(self, job_id: str, result: object, cancelled_at_finish: bool) -> None:
        if job_id not in self._jobs:
            return
        status = getattr(result, "status", None)
        if status is None:
            state = "cancelled" if cancelled_at_finish else "succeeded"
        else:
            state = str(getattr(status, "value", status))
        self._set_state(job_id, state)
        self._release_and_cleanup(job_id)
        self.job_finished.emit(job_id, result)
        self._dispatch()

    @Slot(str, str)
    def _fail(self, job_id: str, message: str) -> None:
        if job_id not in self._jobs:
            return
        self._set_state(job_id, "failed")
        self._release_and_cleanup(job_id)
        self.job_failed.emit(job_id, sanitize_text(message))
        self._dispatch()

    @Slot(str)
    def _started(self, job_id: str) -> None:
        if job_id not in self._jobs:
            return
        self._set_state(job_id, "running")
        self.job_started.emit(job_id)

    def _dispatch(self) -> None:
        for job_id, job in list(self._queued.items()):
            resources = self._allocations[job_id]
            if not all(self._usage[name] < self._capacities[name] for name in resources):
                continue
            self._queued.pop(job_id, None)
            for name in resources:
                self._usage[name] += 1
            self.pool.start(job)

    def _release_and_cleanup(self, job_id: str) -> None:
        was_dispatched = job_id not in self._queued
        self._queued.pop(job_id, None)
        resources = self._allocations.pop(job_id, ())
        if was_dispatched:
            for name in resources:
                self._usage[name] = max(0, self._usage[name] - 1)
        self._cancellations.pop(job_id, None)
        self._jobs.pop(job_id, None)

    def _set_state(self, job_id: str, state: str) -> None:
        self._states.pop(job_id, None)
        self._states[job_id] = state
        while len(self._states) > 1_000:
            self._states.popitem(last=False)
        self.job_state_changed.emit(job_id, state)

    def has_running_jobs(self) -> bool:
        """Incluye trabajos en cola; se conserva el nombre por compatibilidad."""
        return bool(self._jobs)

    def active_count(self) -> int:
        return len(self._jobs)

    def cancel_all(self) -> None:
        for job_id in list(self._jobs):
            self.cancel(job_id)

    def state(self, job_id: str) -> str:
        return self._states.get(job_id, "")
