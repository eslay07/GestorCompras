from __future__ import annotations

import builtins
import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import delete, or_, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from compras_tn.domain.models import (
    Assignment,
    EmailTemplate,
    FlowStep,
    JobStatus,
    ItemStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    PurchaseMode,
    Supplier,
    TaskRecord,
    WorkflowDefinition,
    utc_now,
)
from compras_tn.infrastructure.db.database import Database
from compras_tn.infrastructure.db.models import (
    AssignmentRow,
    EmailTemplateRow,
    OperationItemRow,
    OperationRunRow,
    SettingRow,
    SupplierRow,
    TaskInboxRow,
    WorkflowRow,
)
from compras_tn.security import is_sensitive_key, sanitize_data, sanitize_text


class Repositories:
    """Fachada de repositorios; es el único acceso usado por los casos de uso."""

    def __init__(self, database: Database):
        self.database = database

    def list(self, search: str = "") -> list[Supplier]:
        with self.database.session() as session:
            query = select(SupplierRow).order_by(SupplierRow.name)
            term = search.strip()
            if term:
                like = f"%{term}%"
                query = query.where(
                    or_(
                        SupplierRow.name.ilike(like),
                        SupplierRow.nickname.ilike(like),
                        SupplierRow.nickname_2.ilike(like),
                        SupplierRow.nickname_3.ilike(like),
                        SupplierRow.ruc.ilike(like),
                        SupplierRow.email_primary.ilike(like),
                        SupplierRow.email_secondary.ilike(like),
                    )
                )
            rows = session.scalars(query).all()
            return [self._supplier(row) for row in rows]

    def find_by_ruc(self, ruc: str) -> Supplier | None:
        with self.database.session() as session:
            row = session.scalar(select(SupplierRow).where(SupplierRow.ruc == str(ruc)))
            return self._supplier(row) if row else None

    def find_by_nickname(self, nickname: str) -> Supplier | None:
        key = self._normalized_supplier_value(nickname)
        if not key:
            return None
        matches = [
            item
            for item in self.list()
            if key in self._supplier_nickname_keys(item)
        ]
        return matches[0] if len(matches) == 1 else None

    def save(self, supplier: Supplier) -> Supplier:
        now = utc_now()
        with self.database.session() as session:
            row = session.get(SupplierRow, supplier.id) if supplier.id else None
            if row is None:
                row = session.scalar(select(SupplierRow).where(SupplierRow.ruc == supplier.ruc))
            nicknames = [supplier.nickname, supplier.nickname_2, supplier.nickname_3]
            nickname_keys = [
                self._normalized_supplier_value(value) for value in nicknames if value.strip()
            ]
            if len(nickname_keys) != len(set(nickname_keys)):
                raise ValueError("Los tres sobrenombres del proveedor deben ser diferentes.")
            duplicate = next(
                (
                    candidate
                    for candidate in session.scalars(select(SupplierRow)).all()
                    if candidate.id != getattr(row, "id", None)
                    and set(nickname_keys)
                    & {
                        self._normalized_supplier_value(candidate.nickname),
                        self._normalized_supplier_value(candidate.nickname_2),
                        self._normalized_supplier_value(candidate.nickname_3),
                    }
                ),
                None,
            )
            if duplicate is not None:
                raise ValueError(
                    "Uno de los sobrenombres ya pertenece "
                    f"al proveedor {duplicate.name}."
                )
            if row is None:
                row = SupplierRow(created_at=now, updated_at=now)
                session.add(row)
            row.name = supplier.name
            row.nickname = supplier.nickname
            row.nickname_2 = supplier.nickname_2
            row.nickname_3 = supplier.nickname_3
            row.ruc = supplier.ruc
            row.email_primary = supplier.email_primary
            row.email_secondary = supplier.email_secondary
            row.updated_at = now
            session.flush()
            return self._supplier(row)

    def delete(self, supplier_id: int) -> None:
        with self.database.session() as session:
            session.execute(delete(SupplierRow).where(SupplierRow.id == supplier_id))

    def get(self, namespace: str, key: str, default: Any = None) -> Any:
        with self.database.session() as session:
            row = session.get(SettingRow, (namespace, key))
            if row is None:
                return default
            try:
                return json.loads(row.value_json)
            except json.JSONDecodeError:
                return default

    def set(self, namespace: str, key: str, value: Any) -> None:
        self.set_many({(namespace, key): value})

    def set_many(self, values: Mapping[tuple[str, str], Any]) -> None:
        for _namespace, key in values:
            if is_sensitive_key(key):
                raise ValueError(f"La preferencia '{key}' es sensible y no puede almacenarse.")
        with self.database.session() as session:
            now = utc_now()
            for (namespace, key), value in values.items():
                row = session.get(SettingRow, (namespace, key))
                if row is None:
                    row = SettingRow(
                        namespace=namespace,
                        key=key,
                        value_json="null",
                        updated_at=now,
                    )
                    session.add(row)
                row.value_json = json.dumps(sanitize_data(value), ensure_ascii=False)
                row.updated_at = now

    def list_namespace(self, namespace: str) -> dict[str, Any]:
        with self.database.session() as session:
            rows = session.scalars(
                select(SettingRow).where(SettingRow.namespace == namespace).order_by(SettingRow.key)
            ).all()
            result: dict[str, Any] = {}
            for row in rows:
                try:
                    result[row.key] = json.loads(row.value_json)
                except json.JSONDecodeError:
                    result[row.key] = None
            return result

    def list_assignments(self) -> builtins.list[Assignment]:
        with self.database.session() as session:
            rows = session.scalars(select(AssignmentRow).order_by(AssignmentRow.subdepartment)).all()
            return [Assignment(subdepartment=r.subdepartment, department=r.department, person=r.person) for r in rows]

    def save_assignment(self, item: Assignment) -> Assignment:
        with self.database.session() as session:
            row = session.get(AssignmentRow, item.subdepartment)
            if row is None:
                row = AssignmentRow(subdepartment=item.subdepartment, updated_at=utc_now())
                session.add(row)
            row.department = item.department
            row.person = item.person
            row.updated_at = utc_now()
        return item

    def delete_assignment(self, subdepartment: str) -> None:
        with self.database.session() as session:
            session.execute(delete(AssignmentRow).where(AssignmentRow.subdepartment == subdepartment))

    def list_templates(self) -> builtins.list[EmailTemplate]:
        with self.database.session() as session:
            rows = session.scalars(select(EmailTemplateRow).order_by(EmailTemplateRow.name)).all()
            return [EmailTemplate(id=r.id, name=r.name, html=r.html, signature_path=r.signature_path) for r in rows]

    def save_template(self, item: EmailTemplate) -> EmailTemplate:
        with self.database.session() as session:
            row = session.get(EmailTemplateRow, item.id) if item.id else None
            if row is None:
                row = session.scalar(select(EmailTemplateRow).where(EmailTemplateRow.name == item.name))
            if row is None:
                row = EmailTemplateRow(updated_at=utc_now())
                session.add(row)
            row.name = item.name
            row.html = item.html
            row.signature_path = item.signature_path
            row.updated_at = utc_now()
            session.flush()
            return EmailTemplate(id=row.id, name=row.name, html=row.html, signature_path=row.signature_path)

    def delete_template(self, template_id: int) -> None:
        with self.database.session() as session:
            session.execute(delete(EmailTemplateRow).where(EmailTemplateRow.id == template_id))

    def list_workflows(self, mode: str | None = None) -> builtins.list[WorkflowDefinition]:
        with self.database.session() as session:
            query = select(WorkflowRow).order_by(WorkflowRow.name)
            if mode:
                query = query.where(WorkflowRow.mode == mode)
            return [self._workflow(row) for row in session.scalars(query).all()]

    def save_workflow(self, item: WorkflowDefinition) -> WorkflowDefinition:
        with self.database.session() as session:
            row = session.get(WorkflowRow, item.id) if item.id else None
            if row is None:
                row = session.scalar(select(WorkflowRow).where(WorkflowRow.name == item.name))
            if row is None:
                row = WorkflowRow(updated_at=utc_now())
                session.add(row)
            row.name = item.name
            row.mode = item.mode.value
            row.version = item.version
            row.enabled = item.enabled
            row.stop_on_error = item.stop_on_error
            row.steps_json = json.dumps([s.model_dump() for s in item.steps], ensure_ascii=False)
            row.updated_at = utc_now()
            session.flush()
            return self._workflow(row)

    def delete_workflow(self, workflow_id: int) -> None:
        with self.database.session() as session:
            session.execute(delete(WorkflowRow).where(WorkflowRow.id == workflow_id))

    def enqueue(self, tasks: Sequence[TaskRecord]) -> int:
        from compras_tn.application.task_orders import task_orders, normalize_orders
        inserted = 0
        with self.database.session() as session:
            for task in tasks:
                payload = sanitize_data(task.model_dump(mode="json"))
                if task.origin == "manual":
                    existing = session.scalar(select(TaskInboxRow).where(
                        TaskInboxRow.origin == "manual", TaskInboxRow.task_number == task.task_number,
                        TaskInboxRow.mode == task.purchase_mode.value, TaskInboxRow.status == "pending",
                    ))
                    if existing is not None:
                        previous = json.loads(existing.payload_json)
                        payload["order_number"] = task.order_number or previous.get("order_number", "")
                        payload["supplier"] = task.supplier or previous.get("supplier", "")
                        payload["payload"] = {**previous.get("payload", {}), **payload.get("payload", {})}
                        if (task.order_number or task.supplier) and "orders" not in task.payload:
                            legacy = {**payload, "payload": {k: v for k, v in payload["payload"].items()
                                if k not in {"orders", "order_numbers", "suppliers"}}}
                            payload["payload"]["orders"] = task_orders(TaskRecord.model_validate(legacy))
                        existing.payload_json = json.dumps(payload, ensure_ascii=False)
                        continue
                else:
                    existing = session.scalar(select(TaskInboxRow).where(
                        TaskInboxRow.origin == task.origin, TaskInboxRow.task_number == task.task_number,
                        TaskInboxRow.mode == task.purchase_mode.value, TaskInboxRow.status == "pending",
                    ))
                    if existing is not None:
                        previous = TaskRecord.model_validate(json.loads(existing.payload_json))
                        orders = task_orders(previous)
                        edited = previous.payload.get("orders_edited", False)
                        for incoming in task_orders(task):
                            match = next((row for row in orders if incoming["order_number"] and row["order_number"] == incoming["order_number"]), None)
                            if match is None:
                                orders.append(incoming)
                            else:
                                for key in ("supplier", "approvers"):
                                    match[key] = (match[key] or incoming[key]) if edited else (incoming[key] or match[key])
                        orders = normalize_orders(orders)
                        payload["order_number"] = ", ".join(o["order_number"] for o in orders if o["order_number"])
                        payload["supplier"] = ", ".join(dict.fromkeys(o["supplier"] for o in orders if o["supplier"]))
                        payload["payload"] = {**previous.payload, **task.payload, "orders": orders, "orders_edited": edited}
                        existing.payload_json = json.dumps(sanitize_data(payload), ensure_ascii=False)
                        continue
                statement = sqlite_insert(TaskInboxRow).values(
                    origin=task.origin,
                    task_number=task.task_number,
                    mode=task.purchase_mode.value,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                    status="pending",
                    created_at=utc_now(),
                ).on_conflict_do_nothing(
                    index_elements=[TaskInboxRow.origin, TaskInboxRow.task_number],
                    index_where=TaskInboxRow.status == "pending",
                )
                result = session.execute(statement)
                inserted += max(int(getattr(result, "rowcount", 0) or 0), 0)
        return inserted

    def update_task_orders(self, task: TaskRecord, orders: builtins.list[dict], *, edited: bool = True, origin_only: bool = False) -> None:
        from compras_tn.application.task_orders import normalize_orders, task_orders
        orders = normalize_orders(orders)
        with self.database.session() as session:
            rows = session.scalars(select(TaskInboxRow).where(
                TaskInboxRow.task_number == task.task_number,
                TaskInboxRow.mode.in_((task.purchase_mode.value, "general")), TaskInboxRow.status == "pending",
            )).all()
            for row in rows:
                if origin_only and row.origin != task.origin:
                    continue
                payload = json.loads(row.payload_json)
                previous = TaskRecord.model_validate(payload)
                selected = orders
                if not edited:
                    selected = task_orders(previous)
                    if any(o["order_number"] for o in selected):
                        by_number = {o["order_number"]: o for o in orders if o["order_number"]}
                        for original in selected:
                            incoming = by_number.get(original["order_number"], {})
                            original["supplier"] = original["supplier"] or incoming.get("supplier", "")
                            if not previous.payload.get("orders_edited") or not original["approvers"]:
                                original["approvers"] = incoming.get("approvers") or original["approvers"]
                    else:
                        selected = orders
                payload["order_number"] = ", ".join(o["order_number"] for o in selected if o["order_number"])
                payload["supplier"] = ", ".join(dict.fromkeys(o["supplier"] for o in selected if o["supplier"]))
                payload["payload"] = {**payload.get("payload", {}), "orders": selected,
                    "orders_edited": edited or bool(previous.payload.get("orders_edited"))}
                row.payload_json = json.dumps(sanitize_data(payload), ensure_ascii=False)

    def synchronize_oc_task(self, task: TaskRecord, ready: bool) -> None:
        with self.database.session() as session:
            rows = session.scalars(select(TaskInboxRow).where(
                TaskInboxRow.origin == "carga_oc_automatica", TaskInboxRow.task_number == task.task_number,
                TaskInboxRow.mode == task.purchase_mode.value,
            )).all()
            # A reconciled source never reopens consumed or dismissed tasks.
            if any(row.status in {"consumed", "dismissed"} for row in rows):
                return
            row = rows[0] if rows else TaskInboxRow(origin=task.origin, task_number=task.task_number,
                mode=task.purchase_mode.value, created_at=utc_now())
            incoming = task.model_dump(mode="json")
            previous = json.loads(row.payload_json or "{}")
            if previous.get("payload", {}).get("orders_edited"):
                incoming["payload"].update(orders=previous["payload"]["orders"], orders_edited=True)
                incoming["order_number"] = previous.get("order_number", "")
                incoming["supplier"] = previous.get("supplier", "")
            row.payload_json = json.dumps(sanitize_data(incoming), ensure_ascii=False)
            row.status = "pending" if ready else "waiting_oc"
            session.add(row)

    def list_pending(self, origin: str | None = None) -> builtins.list[TaskRecord]:
        with self.database.session() as session:
            query = select(TaskInboxRow).where(TaskInboxRow.status == "pending")
            if origin:
                query = query.where(TaskInboxRow.origin == origin)
            rows = session.scalars(query.order_by(TaskInboxRow.id)).all()
            result: builtins.list[TaskRecord] = []
            for row in rows:
                try:
                    task = TaskRecord.model_validate(json.loads(row.payload_json))
                    # Relational columns identify the source; stale JSON cannot relabel it.
                    result.append(task.model_copy(update={'origin': row.origin, 'task_number': row.task_number,
                                                         'purchase_mode': PurchaseMode(row.mode)}))
                except (json.JSONDecodeError, TypeError, ValueError):
                    try:
                        mode = PurchaseMode(row.mode)
                    except ValueError:
                        mode = PurchaseMode.GENERAL
                    result.append(
                        TaskRecord(
                            task_number=row.task_number,
                            origin=row.origin,
                            purchase_mode=mode,
                        )
                    )
            return result

    def dismiss(self, tasks: Sequence[TaskRecord]) -> None:
        with self.database.session() as session:
            for task in tasks:
                rows = session.scalars(select(TaskInboxRow).where(
                    TaskInboxRow.status == "pending",
                    TaskInboxRow.task_number == task.task_number,
                    TaskInboxRow.origin == task.origin,
                    TaskInboxRow.mode == task.purchase_mode.value,
                ))
                for row in rows:
                    row.status = "dismissed"
                    row.consumed_at = utc_now()

    def consume(self, task_numbers: Sequence[str], origin: str | None = None) -> None:
        if not task_numbers:
            return
        with self.database.session() as session:
            query = select(TaskInboxRow).where(
                TaskInboxRow.status.in_(("pending", "waiting_oc")),
                TaskInboxRow.task_number.in_(task_numbers),
            )
            if origin:
                query = query.where(TaskInboxRow.origin == origin)
            for row in session.scalars(query):
                row.status = "consumed"
                row.consumed_at = utc_now()

    def cycle_successes(self):
        """Successful item evidence, including runs completed before cycle tracking."""
        result = []
        with self.database.session() as session:
            rows = session.execute(select(OperationRunRow.request_json, OperationItemRow.item_key,
                OperationItemRow.payload_json, OperationItemRow.status).join(OperationItemRow, OperationItemRow.run_id == OperationRunRow.id)
                .where(or_(OperationItemRow.status == 'succeeded',
                    (OperationRunRow.kind == 'precarga_oc_bienes') &
                    (OperationItemRow.status == 'failed')),
                    OperationRunRow.kind.in_(
                    ['actualizar_tareas', 'precarga_oc_bienes', 'descarga_normal',
                     'descarga_abastecimiento', 'escaneo_descargas', 'correos_masivos', 'reasignacion'])))
            for request, key, payload, status in rows:
                data = json.loads(payload)
                if status != 'succeeded' and not (
                    data.get('order_number') and isinstance(data.get('sheet_written'), bool)
                ):
                    continue
                result.append((OperationRequest.model_validate_json(request),
                    OperationItem(key=key, status=ItemStatus.SUCCEEDED, payload=json.loads(payload))))
            for raw in session.execute(text('SELECT payload FROM quotation_attachments')).scalars():
                row = json.loads(raw)
                if row.get('saved_path') and not row.get('error') and row.get('status') in ('Guardado', 'Ya guardado'):
                    result.append((OperationRequest(kind='organizar_cotizaciones', items=[row]),
                        OperationItem(key=str(row.get('task_number', '')), status=ItemStatus.SUCCEEDED, payload=row)))
        return result

    def start(self, request: OperationRequest) -> int:
        with self.database.session() as session:
            safe_request = sanitize_data(request.model_dump(mode="json"))
            row = OperationRunRow(
                kind=request.kind,
                mode=request.mode.value,
                status=JobStatus.RUNNING.value,
                request_json=json.dumps(safe_request, ensure_ascii=False),
                started_at=utc_now(),
            )
            session.add(row)
            session.flush()
            return row.id

    def finish(self, run_id: int, result: OperationResult) -> None:
        with self.database.session() as session:
            row = session.get(OperationRunRow, run_id)
            if row is None:
                return
            row.status = result.status.value
            row.message = sanitize_text(result.message)
            row.finished_at = result.finished_at or utc_now()
            row.items.clear()
            for item in result.items:
                row.items.append(
                    OperationItemRow(
                        item_key=item.key,
                        status=item.status.value,
                        message=sanitize_text(item.message),
                        payload_json=json.dumps(sanitize_data(item.payload), ensure_ascii=False),
                    )
                )

    @staticmethod
    def _supplier(row: SupplierRow) -> Supplier:
        return Supplier(
            id=row.id,
            name=row.name,
            nickname=row.nickname,
            nickname_2=row.nickname_2,
            nickname_3=row.nickname_3,
            ruc=row.ruc,
            email_primary=row.email_primary,
            email_secondary=row.email_secondary,
        )

    @staticmethod
    def _normalized_supplier_value(value: str) -> str:
        return " ".join(str(value or "").split()).casefold()

    @classmethod
    def _supplier_nickname_keys(cls, supplier: Supplier) -> builtins.set[str]:
        return {
            key
            for value in (supplier.nickname, supplier.nickname_2, supplier.nickname_3)
            if (key := cls._normalized_supplier_value(value))
        }

    @staticmethod
    def _workflow(row: WorkflowRow) -> WorkflowDefinition:
        try:
            raw_steps = json.loads(row.steps_json or "[]")
            if not isinstance(raw_steps, list):
                raw_steps = []
        except (json.JSONDecodeError, TypeError):
            raw_steps = []
        steps = [
            FlowStep(
                action_id=str(step.get("action_id") or step.get("id") or ""),
                params=dict(step.get("params") or {}),
            )
            for step in raw_steps
            if isinstance(step, dict) and (step.get("action_id") or step.get("id"))
        ]
        try:
            mode = PurchaseMode(row.mode)
        except ValueError:
            mode = PurchaseMode.GENERAL
        return WorkflowDefinition(
            id=row.id,
            name=row.name,
            mode=mode,
            version=row.version,
            enabled=row.enabled,
            stop_on_error=row.stop_on_error,
            steps=steps,
            updated_at=row.updated_at,
        )
