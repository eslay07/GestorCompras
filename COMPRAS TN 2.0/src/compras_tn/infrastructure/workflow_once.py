"""Guard workflows by task and processed orders, preserving legacy history."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

from compras_tn.application.task_orders import task_orders
from compras_tn.domain.models import TaskRecord


class WorkflowOnce:
    def __init__(self, paths, workflow):
        self.path = paths.root / "workflow-starts.db"
        self.history = paths.database
        self.name = workflow.name
        self.mode = workflow.mode.value
        self.orders = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS starts(key TEXT PRIMARY KEY, task TEXT, workflow TEXT, mode TEXT, state TEXT, updated TEXT)")
            if 'orders_json' not in {row[1] for row in connection.execute('PRAGMA table_info(starts)')}:
                connection.execute('ALTER TABLE starts ADD COLUMN orders_json TEXT')

    def key(self, number):
        parts = [self.mode, self.name.casefold(), number]
        if self.orders.get(number):
            parts.append(sorted(self.orders[number]))
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()

    def _history_orders(self, number):
        covered, unknown = set(), False
        if self.history.is_file():
            with closing(sqlite3.connect(self.history.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
                tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if {"operation_runs", "operation_items"} <= tables:
                    rows = connection.execute("SELECT r.request_json FROM operation_items i JOIN operation_runs r ON r.id=i.run_id WHERE r.kind='actualizar_tareas' AND r.mode=? AND i.item_key=? AND i.status='succeeded' AND lower(json_extract(r.request_json,'$.options.workflow'))=lower(?)", (self.mode, number, self.name))
                    for (raw,) in rows:
                        items = json.loads(raw).get('items', [])
                        orders = set()
                        for item in items:
                            if str(item.get('task_number')) == number:
                                orders.update(row['order_number'] for row in task_orders(TaskRecord.model_validate(item)) if row['order_number'])
                        covered.update(orders)
                        unknown = unknown or not orders
        return covered, unknown

    def _coverage(self, number):
        covered, unknown = self._history_orders(number)
        with closing(sqlite3.connect(self.path)) as connection:
            rows = list(connection.execute('SELECT state, orders_json FROM starts WHERE task=? AND lower(workflow)=lower(?) AND mode=?', (number, self.name, self.mode)))
        active = any(state not in ('succeeded', 'failed', 'cancelled') for state, _ in rows)
        legacy = False
        for state, raw in rows:
            if state == 'succeeded':
                if raw:
                    covered.update(json.loads(raw))
                else:
                    legacy = True
        # An old task-only marker can be resolved using its audited request.
        return covered, active or unknown or (legacy and not covered)

    def pending_task(self, task):
        rows = task_orders(task)
        numbers = {row['order_number'] for row in rows if row['order_number']}
        if not numbers:
            return None if self.seen(task.task_number) else task
        covered, blocked = self._coverage(task.task_number)
        if blocked:
            return None
        remaining = [row for row in rows if row['order_number'] not in covered]
        if not any(row['order_number'] for row in remaining):
            return None
        numbers = sorted({row['order_number'] for row in remaining if row['order_number']})
        suppliers = list(dict.fromkeys(row['supplier'] for row in remaining if row['supplier']))
        self.orders[task.task_number] = numbers
        return task.model_copy(update={'order_number': ', '.join(numbers), 'supplier': ', '.join(suppliers),
            'payload': {**task.payload, 'orders': remaining, 'order_numbers': numbers, 'suppliers': suppliers}})

    def seen(self, number):
        covered, blocked = self._coverage(number)
        if blocked:
            return True
        if self.orders.get(number):
            return set(self.orders[number]) <= covered
        return bool(covered) or self._legacy_seen(number)

    def _legacy_seen(self, number):
        with closing(sqlite3.connect(self.path)) as connection:
            return bool(connection.execute("SELECT 1 FROM starts WHERE key=? AND state NOT IN ('failed','cancelled')", (self.key(number),)).fetchone())

    def claim(self, number):
        with closing(sqlite3.connect(self.path, timeout=30)) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            if self.orders.get(number):
                covered, blocked = self._coverage(number)
                if blocked or covered.intersection(self.orders[number]):
                    return False
            if connection.execute("SELECT 1 FROM starts WHERE task=? AND lower(workflow)=lower(?) AND mode=? AND state NOT IN ('succeeded','failed','cancelled')", (number, self.name, self.mode)).fetchone():
                return False
            cursor = connection.execute("INSERT INTO starts(key,task,workflow,mode,state,updated,orders_json) VALUES (?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET state=excluded.state, updated=excluded.updated WHERE starts.state IN ('failed','cancelled')", (self.key(number), number, self.name, self.mode, "started", datetime.now(UTC).isoformat(), json.dumps(self.orders[number]) if self.orders.get(number) else None))
            return cursor.rowcount == 1

    def finish(self, number, state):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE starts SET state=?, updated=? WHERE key=?", (state, datetime.now(UTC).isoformat(), self.key(number)))
