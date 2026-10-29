from __future__ import annotations

import re
from contextlib import nullcontext
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from compras_tn.application.catalog_matching import match_supplier_nickname
from compras_tn.application.task_cycle import CycleDeclined
from compras_tn.application.ports import (
    CatalogRepository,
    JobRepository,
    MailGateway,
    OrderDownloadGateway,
    OrderMailScanner,
    OrderResolver,
    PurchaseOrderGateway,
    ReportGateway,
    SeafileGateway,
    SettingsRepository,
    SheetGateway,
    SupplierRepository,
    TaskInboxRepository,
    TelcosGateway,
    TemplateRenderer,
)
from compras_tn.application.workflows import validate_workflow
from compras_tn.domain.models import (
    Assignment,
    DispatchPreview,
    DispatchPreviewItem,
    EmailTemplate,
    ItemStatus,
    JobStatus,
    OperationItem,
    OperationRequest,
    OperationResult,
    OrderRecord,
    PurchaseMode,
    PurchaseOrderArticle,
    PurchaseOrderDraft,
    SessionCredentials,
    Supplier,
    TaskRecord,
    WorkflowDefinition,
    utc_now,
)
from compras_tn.domain.purchase_order_groups import consolidate_orders
from compras_tn.security import sanitize_data, sanitize_text

Progress = Callable[[int, int, str], None]
Cancelled = Callable[[], bool]


class ApplicationFacade:
    """Entrada única de la UI a los casos de uso del sistema."""

    def __init__(
        self,
        suppliers: SupplierRepository,
        settings: SettingsRepository,
        catalogs: CatalogRepository,
        inbox: TaskInboxRepository,
        jobs: JobRepository,
        mail: MailGateway,
        telcos: TelcosGateway,
        downloads: OrderDownloadGateway,
        orders: OrderResolver,
        sheets: SheetGateway,
        renderer: TemplateRenderer,
        order_mail: OrderMailScanner,
        reports: ReportGateway,
        seafile: SeafileGateway,
        purchases: PurchaseOrderGateway | None = None,
        quotations: Any = None,
    ):
        self.suppliers = suppliers
        self.settings = settings
        self.catalogs = catalogs
        self.inbox = inbox
        self.jobs = jobs
        self.mail = mail
        self.telcos = telcos
        self.downloads = downloads
        self.orders = orders
        self.sheets = sheets
        self.renderer = renderer
        self.order_mail = order_mail
        self.reports = reports
        self.seafile = seafile
        self.purchases = purchases
        self.quotations = quotations
        self._credentials: SessionCredentials | None = None

    @property
    def credentials(self) -> SessionCredentials:
        if self._credentials is None:
            raise RuntimeError("La sesión está cerrada.")
        return self._credentials

    def login(self, username: str, password: str) -> SessionCredentials:
        normalized = username.strip()
        email = normalized if "@" in normalized else f"{normalized}@telconet.ec"
        credentials = SessionCredentials(
            username=email.split("@", 1)[0].upper(),
            email=email.lower(),
            password=password,
        )
        self.mail.validate(credentials)
        self._credentials = credentials
        self.settings.set("session", "correo_usuario", credentials.email)
        return credentials

    def logout(self) -> None:
        self._credentials = None

    def get_setting(self, namespace: str, key: str, default: Any = None) -> Any:
        return self.settings.get(namespace, key, default)

    def set_setting(self, namespace: str, key: str, value: Any) -> None:
        self.settings.set(namespace, key, value)

    def save_settings(self, values: Mapping[tuple[str, str], Any]) -> None:
        self.settings.set_many(values)

    def list_settings(self, namespace: str) -> dict[str, Any]:
        return self.settings.list_namespace(namespace)

    def list_pending_tasks(self, origin: str | None = None) -> list[TaskRecord]:
        # Local receipts are safe to hydrate during a UI refresh: no network.
        return self._enrich_workflow_tasks(self.inbox.list_pending(origin), persist=True)

    def dismiss_tasks(self, tasks: Sequence[TaskRecord]) -> None:
        self.inbox.dismiss(tasks)

    def enqueue_tasks(self, tasks: Sequence[TaskRecord]) -> int:
        return self._enqueue_workflow_tasks(tasks)

    def update_task_orders(self, task, orders):
        self.inbox.update_task_orders(task, orders)

    def _enrich_workflow_tasks(self, tasks, *, remote=False, persist=False):
        from compras_tn.application.task_orders import task_orders, normalize_orders
        tasks = list(tasks)
        if not tasks:
            return []
        local = {}
        reader = getattr(self.settings, "list_namespace", None)
        receipts = reader("oc_approvals") if callable(reader) else {}
        scope = self._oc_scope()
        for key, receipt in receipts.items():
            if not key.startswith(scope) or receipt.get("state") not in {"read", "synced"} or not receipt.get("names"):
                continue
            try:
                draft = PurchaseOrderDraft.model_validate(receipt["draft"])
                for number in draft.task_numbers:
                    local[(number, receipt["number"])] = dict(order_number=receipt["number"],
                        supplier=draft.supplier, approvers=receipt["names"])
            except (KeyError, TypeError, ValueError):
                continue
        lookup = {}
        failure = ""
        lookup_errors = {}
        if remote:
            try:
                lookup = self.sheets.read_task_orders(list(dict.fromkeys(task.task_number for task in tasks)))
                catalog = self.suppliers.list()
                for number, rows in list(lookup.items()):
                    canonical = []
                    for row in rows:
                        supplier, _error = match_supplier_nickname(row["supplier"], catalog)
                        canonical.append({**row, "supplier": supplier.name if supplier else row["supplier"]})
                    try:
                        lookup[number] = normalize_orders(canonical)
                    except ValueError as exc:
                        lookup[number] = []
                        lookup_errors[number] = str(exc)
            except Exception as exc:
                # Enrichment cannot turn a successful mail/download into a failure.
                failure = self._safe_text(exc)
        result = []
        for task in tasks:
            orders = task_orders(task)
            found = {row["order_number"]: row for row in lookup.get(task.task_number, [])}
            known = {number: row for (task_number, number), row in local.items() if task_number == task.task_number}
            if task.origin != 'descargas' and not any(row["order_number"] for row in orders) and not task.payload.get("orders_edited"):
                orders = list(found.values()) or list(known.values()) or orders
            filled = []
            for row in orders:
                number = row["order_number"]
                sheet = found.get(number, {})
                cached = known.get(number, {})
                names = row["approvers"] if task.payload.get("orders_edited") and row["approvers"] else (
                    sheet.get("approvers") or row["approvers"] or cached.get("approvers", []))
                filled.append({**row, "supplier": row["supplier"] or sheet.get("supplier") or cached.get("supplier", ""),
                               "approvers": names})
            payload = {**task.payload, "orders": normalize_orders(filled)}
            error = lookup_errors.get(task.task_number) or failure
            if error:
                payload["approvers_sync_error"] = error
            elif remote:
                payload.pop("approvers_sync_error", None)
            if task.task_number in lookup_errors:
                payload["approvers_data_conflict"] = lookup_errors[task.task_number]
            elif remote:
                payload.pop("approvers_data_conflict", None)
            prepared = task.model_copy(update={"payload": payload})
            if persist and prepared.payload.get("orders") != task.payload.get("orders"):
                self.inbox.update_task_orders(prepared, payload["orders"], edited=False, origin_only=True)
            result.append(prepared)
        return result

    def _enqueue_workflow_tasks(self, tasks):
        tasks = list(tasks)
        manual = [task for task in tasks if task.origin == "manual"]
        downloads = [task for task in tasks if task.origin == "descargas"]
        imported = [task for task in tasks if task.origin not in {"manual", "descargas"}]
        # Keep download completion independent of Google/network availability.
        # Missing GENERAL data is loaded by the Orchestrator's background refresh.
        return self.inbox.enqueue(manual + self._enrich_workflow_tasks(downloads)
                                  + self._enrich_workflow_tasks(imported, remote=True))

    def synchronize_workflow_origin(self, origin, mode, progress=None, cancelled=None):
        """Refresh the selected module without promoting tasks from another source."""
        batch = getattr(self.sheets, 'batch', None)
        with batch(progress, cancelled) if callable(batch) else nullcontext():
            if origin in ('Todas', 'carga_oc_automatica'):
                if progress:
                    progress(0, 0, 'Sincronizando tareas de Carga de OC automática…')
                self.reconcile_oc_tasks()
            if cancelled and cancelled():
                return []
            tasks = [task for task in self.list_pending_tasks(None if origin == 'Todas' else origin)
                     if task.purchase_mode in {mode, PurchaseMode.GENERAL}
                     and (origin == 'Todas' or task.origin == origin)]
            return self.refresh_workflow_approvers(tasks)

    def refresh_workflow_approvers(self, tasks):
        return self._enrich_workflow_tasks(tasks, remote=True, persist=True)

    def prepare_workflow_tasks(self, workflow, tasks):
        from compras_tn.application.task_orders import missing_order_data
        needs_names = any("{aprobadores}" in str(step.params) for step in workflow.steps)
        enriched = self._enrich_workflow_tasks(tasks, remote=needs_names, persist=True)
        result = []
        for task in enriched:
            errors = missing_order_data(workflow, task)
            if needs_names and task.payload.get("approvers_data_conflict") and not task.payload.get("orders_edited"):
                errors.append("Revise la asociación en GENERAL: " + task.payload["approvers_data_conflict"])
            if errors and task.payload.get("approvers_sync_error"):
                errors.append("No se pudo consultar GENERAL: " + task.payload["approvers_sync_error"])
            result.append({"task": task, "error": "\n".join(errors)})
        return result

    def test_mail_connection(self) -> str:
        self.mail.validate(self.credentials)
        self.mail.validate_inbox(self.credentials)
        self.order_mail.validate(self.credentials)
        return "Conexiones SMTP, IMAP y POP verificadas."

    def test_google_connection(self) -> str:
        drafts = self.sheets.read_purchase_order_drafts()
        return (
            "Conexión con Google Sheets verificada "
            f"({len(drafts)} órdenes detectadas en GENERAL)."
        )

    def test_seafile_connection(self) -> str:
        self.seafile.validate(self.credentials)
        return "Conexión con Seafile verificada."

    def test_telcos_connection(self) -> str:
        self.telcos.validate(self.credentials, headless=True)
        return "Conexión con Telcos verificada."

    def list_suppliers(self, search: str = "") -> list[Supplier]:
        return self.suppliers.list(search)

    def save_supplier(self, item: Supplier) -> Supplier:
        return self.suppliers.save(item)

    def delete_supplier(self, supplier_id: int) -> None:
        self.suppliers.delete(supplier_id)

    def list_assignments(self) -> list[Assignment]:
        return self.catalogs.list_assignments()

    def save_assignment(self, item: Assignment) -> Assignment:
        return self.catalogs.save_assignment(item)

    def delete_assignment(self, subdepartment: str) -> None:
        self.catalogs.delete_assignment(subdepartment)

    def list_templates(self) -> list[EmailTemplate]:
        return self.catalogs.list_templates()

    def save_template(self, item: EmailTemplate) -> EmailTemplate:
        return self.catalogs.save_template(item)

    def delete_template(self, template_id: int) -> None:
        self.catalogs.delete_template(template_id)

    def list_workflows(self, mode: str | None = None) -> list[WorkflowDefinition]:
        return self.catalogs.list_workflows(mode)

    def save_workflow(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        from compras_tn.application.workflows import expand_workflow

        errors = validate_workflow(workflow)
        if errors:
            raise ValueError("Flujo inválido:\n- " + "\n- ".join(errors))
        for index, step in enumerate(expand_workflow(workflow).steps, start=1):
            if step.action_id != "seleccionar_archivo":
                continue
            if step.params.get("modo_archivo") == "tipos":
                known = {definition["id"] for definition in self.document_types()}
                if any(kind not in known for kind in step.params["tipos_archivo"]):
                    errors.append(f"Paso {index}: hay tipos de documento que ya no están configurados.")
                continue
            raw = str(step.params.get("ruta") or "@archivo_tarea").strip()
            if raw == "@archivo_tarea":
                continue
            if raw.startswith("@"):
                key = f"actua_file_alias::{raw[1:]}".lower()
                if not str(self.settings.get("automation", key, "")).strip():
                    errors.append(f"Paso {index}: el alias '{raw}' no está configurado.")
            elif raw and "{" not in raw and not Path(raw).is_file():
                errors.append(f"Paso {index}: no existe el archivo '{raw}'.")
        if errors:
            raise ValueError("Flujo inválido:\n- " + "\n- ".join(errors))
        return self.catalogs.save_workflow(workflow)

    def delete_workflow(self, workflow_id: int) -> None:
        self.catalogs.delete_workflow(workflow_id)

    def load_followups(self) -> list[dict[str, Any]]:
        return self.sheets.read_approved_orders()

    def load_purchase_order_drafts(self, progress=None, cancelled=None) -> list[PurchaseOrderDraft]:
        batch = getattr(self.sheets, 'batch', None)
        with batch(progress, cancelled) if callable(batch) else nullcontext():
            drafts = self._resolve_purchase_order_catalogs(self.sheets.read_purchase_order_drafts())
            drafts = self._block_oc_recoveries(drafts)
            self.reconcile_oc_tasks()
            return drafts

    def _block_oc_recoveries(self, drafts: Sequence[PurchaseOrderDraft]) -> list[PurchaseOrderDraft]:
        result = []
        for draft in drafts:
            errors = list(draft.validation_errors)
            if any(self.settings.get('oc_paused', key, False) for key in self._oc_receipt_keys(draft)):
                errors.append('Bloqueada desde la tabla.')
            for key in self._oc_receipt_keys(draft):
                receipt = self.settings.get("oc_receipts", key, {})
                if receipt.get("state") in {"saving", "pending", "synced"}:
                    warning = f"Recuperación pendiente en fila {key.rsplit(':', 1)[-1]}; no regenerar la OC {receipt.get('number') or '(guardado ambiguo)'}."
                    if warning not in errors:
                        errors.append(warning)
            result.append(draft.model_copy(update={"validation_errors": errors}))
        return result

    def pending_oc_recoveries(self, *, include_synced: bool = False) -> list[dict[str, Any]]:
        """Local receipts remain visible even when Sheets cannot be reached."""
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        paths = getattr(self.purchases, "app_paths", None)
        for key, receipt in self.settings.list_namespace("oc_receipts").items():
            states = {"saving", "pending", "synced"} if include_synced else {"saving", "pending"}
            if not key.startswith(self._oc_scope()) or receipt.get("state") not in states:
                continue
            draft = PurchaseOrderDraft.model_validate(receipt["draft"])
            keys = tuple(self._oc_receipt_keys(draft))
            if keys in seen:
                continue
            seen.add(keys)
            candidates = {str(receipt["number"])} if receipt.get("number") else set()
            evidence: list[str] = []
            if paths:
                for task in draft.task_numbers:
                    for diagnostic in (paths.diagnostics / "precarga_oc").glob(f"*-oc_{task}.txt"):
                        text = diagnostic.read_text(encoding="utf-8", errors="replace")
                        match = re.search(r"/movimientos/orden-compra/bienes/(\d{4,14})(?:\s|$)", text)
                        if match and "Transacción realizada correctamente" in text:
                            candidates.add(match.group(1))
                            evidence.append(str(diagnostic))
            results.append({**receipt, "key": key, "candidates": sorted(candidates), "evidence": evidence})
        return results

    def recover_purchase_order(self, key: str, expected_at: str, *, number: str = "",
                               discard: bool = False, verified: bool = False, reason: str = "",
                               reopen: bool = False) -> str:
        if not verified or not reason.strip():
            raise ValueError("Confirme la revisión en NAF e indique la evidencia o motivo.")
        receipt = self.settings.get("oc_receipts", key, {})
        allowed_states = {"saving", "pending", "synced"} if reopen else {"saving", "pending"}
        if (not key.startswith(self._oc_scope()) or receipt.get("state") not in allowed_states
                or receipt.get("at") != expected_at):
            raise ValueError("El intento cambió; vuelva a abrir Recuperar OC pendientes.")
        draft = PurchaseOrderDraft.model_validate(receipt["draft"])
        for source_key in self._oc_receipt_keys(draft):
            other = self.settings.get("oc_receipts", source_key, {})
            if other.get("at") != expected_at or other.get("draft") != receipt["draft"]:
                raise ValueError("Las filas pertenecen a intentos diferentes; revise el historial antes de recuperar.")
        audit = {"action": "discard" if discard else "recover", "reason": reason.strip(),
                 "actor": self.credentials.username, "number": number, "verified": True}
        if reopen:
            if discard:
                raise ValueError("Seleccione una sola acción de recuperación.")
            # The sheet reader excludes occupied/formula G cells. Release the complete
            # saved attempt only; never clear G or silently release unrelated rows.
            eligible_rows = {a.source_row for current in self.sheets.read_purchase_order_drafts()
                             for a in current.original_articles}
            missing = sorted(set(draft.source_rows) - eligible_rows)
            if missing:
                raise ValueError("No se habilitó: estas filas ya tienen OC, fórmula o no son elegibles en GENERAL: "
                                 + ", ".join(map(str, missing)) + ". Revise la hoja y vuelva a validar.")
            for source_key in self._oc_receipt_keys(draft):
                if self.settings.get("oc_receipts", source_key, {}).get("at") != expected_at:
                    raise ValueError("El intento cambió durante la validación; vuelva a revisar el bloqueo.")
            audit.update(action="reopen", number=receipt.get("number", ""))
            self._record_oc_receipt(draft, "released", str(receipt.get("number") or ""), audit=audit)
            return "Bloqueo retirado para un nuevo intento. Historial y OC anterior conservados. Vuelva a validar GENERAL antes de cargar."
        if discard:
            if receipt.get("number"):
                raise ValueError("Una OC confirmada no se puede descartar como intento sin orden.")
            self._record_oc_receipt(draft, "discarded", audit=audit)
            return "Intento descartado tras revisión; puede volver a cargar GENERAL. Historial conservado."
        if not re.fullmatch(r"\d{4,14}", number):
            raise ValueError("Ingrese el número de OC verificado en NAF.")
        if receipt.get("number") and receipt["number"] != number:
            raise ValueError("El intento ya tiene otra OC confirmada; no se reemplazó.")
        self._record_oc_receipt(draft, "pending", number, audit=audit)
        self.sheets.record_purchase_order(draft, number)
        self._record_oc_receipt(draft, "synced", number)
        self._ensure_approval_pending(draft, number)
        return f"Guardada en NAF: OC {number}. Sincronizada en Google Sheets. Use Recuperar aprobadores para completar aprobación y columna O."

    def recover_selected_orders(self, selected, progress=None, cancelled=None):
        items = []
        batch = getattr(self.sheets, 'batch', None)
        with batch(progress, cancelled) if callable(batch) else nullcontext():
            for index, receipt in enumerate(selected, 1):
                if cancelled and cancelled():
                    break
                draft = PurchaseOrderDraft.model_validate(receipt['draft'])
                try:
                    candidates = receipt.get('candidates', [])
                    number = receipt.get('number') or (candidates[0] if len(candidates) == 1 else '')
                    if not number:
                        raise ValueError('No se identificó una OC única para esta tarea. El intento continúa pendiente.')
                    message = self.recover_purchase_order(receipt['key'], receipt['at'], number=number,
                        verified=True, reason='Recuperación seleccionada desde la tabla')
                    items.append(OperationItem(key=draft.operation_key, status=ItemStatus.SUCCEEDED, message=message))
                except Exception as exc:
                    items.append(OperationItem(key=draft.operation_key, status=ItemStatus.FAILED, message=self._safe_text(exc)))
                if progress:
                    progress(index, len(selected), f'Recuperando tarea {draft.task_number}')
        return OperationResult.from_items(items, 'Recuperación terminada.')

    def set_purchase_order_enabled(self, draft, enabled, progress=None, cancelled=None):
        keys = self._oc_receipt_keys(draft)
        batch = getattr(self.sheets, 'batch', None)
        with batch(progress, cancelled) if callable(batch) else nullcontext():
            if enabled:
                handled = set()
                for key in keys:
                    receipt = self.settings.get('oc_receipts', key, {})
                    if receipt.get('state') not in {'saving', 'pending', 'synced'} or receipt.get('at') in handled:
                        continue
                    handled.add(receipt.get('at'))
                    if receipt.get('number') and receipt.get('state') == 'synced':
                        self.sheets.record_purchase_order(PurchaseOrderDraft.model_validate(receipt['draft']), receipt['number'])
                    elif receipt.get('number'):
                        self.recover_purchase_order(key, receipt['at'], number=receipt['number'],
                            verified=True, reason='Cambio de estado desde la tabla')
                    else:
                        self.recover_purchase_order(key, receipt['at'], reopen=True,
                            verified=True, reason='Cambio de estado desde la tabla')
            self.settings.set_many({('oc_paused', key):not enabled for key in keys})
            return self.load_purchase_order_drafts(progress, cancelled)

    def _oc_receipt_keys(self, draft: PurchaseOrderDraft) -> list[str]:
        sheet = self.settings.get("google", "google_sheet_id", "") or ""
        tab = self.settings.get("google", "google_oc_sheet_name", "GENERAL") or "GENERAL"
        return [f"{sheet}:{tab}:{article.source_row}" for article in draft.original_articles]

    def _record_oc_receipt(self, draft: PurchaseOrderDraft, state: str, number: str = "", *, audit: dict[str, Any] | None = None) -> None:
        receipt = {"state": state, "number": number, "draft": draft.model_dump(mode="json"), "at": utc_now().isoformat()}
        updates: dict[tuple[str, str], Any] = {}
        for key in self._oc_receipt_keys(draft):
            previous = self.settings.get("oc_receipts", key, {})
            history = list(previous.get("history", []))
            if previous:
                history.append({k: v for k, v in previous.items() if k != "history"})
            updates[("oc_receipts", key)] = {**receipt, "history": history, "audit": audit or {}}
        if state == "synced":
            # Only transitions made by this version enroll tasks; old synced receipts are not imported.
            for source in draft.original_drafts:
                key = self._oc_scope() + source.task_number
                candidate = updates.get(("oc_task_candidates", key)) or self.settings.get("oc_task_candidates", key, {"task_number": source.task_number, "rows": {}})
                for article in source.articles:
                    candidate["rows"][str(article.source_row)] = {"order_number": number, "article": article.model_dump(mode="json")}
                updates[("oc_task_candidates", key)] = candidate
        self.settings.set_many(updates)

    def _oc_scope(self) -> str:
        sheet = self.settings.get("google", "google_sheet_id", "") or ""
        tab = self.settings.get("google", "google_oc_sheet_name", "GENERAL") or "GENERAL"
        return f"{sheet}:{tab}:"

    def reconcile_oc_tasks(self) -> list[TaskRecord]:
        scope = self._oc_scope()
        candidates = [value for key, value in self.settings.list_namespace("oc_task_candidates").items() if key.startswith(scope)]
        if not candidates:
            return []
        try:
            states = self.sheets.read_purchase_task_status()
        except Exception:
            for candidate in candidates:
                self.inbox.synchronize_oc_task(TaskRecord(task_number=candidate["task_number"],
                    origin="carga_oc_automatica", purchase_mode=PurchaseMode.BIENES), False)
            raise
        ready_tasks = []
        for candidate in candidates:
            number = candidate["task_number"]
            state = states.get(number, {})
            ready = bool(state.get("ready"))
            for row, expected in candidate["rows"].items():
                actual = state.get("rows", {}).get(row)
                ready = ready and bool(actual) and actual["order_number"] == expected["order_number"]
                if actual:
                    ready = ready and (PurchaseOrderArticle.model_validate(actual["article"]) == PurchaseOrderArticle.model_validate(expected["article"]))
            orders = state.get("order_numbers", [])
            suppliers = state.get("suppliers", [])
            task = TaskRecord(task_number=number, origin="carga_oc_automatica", purchase_mode=PurchaseMode.BIENES,
                order_number=", ".join(orders), supplier=", ".join(suppliers),
                payload={"order_numbers": orders, "suppliers": suppliers, "oc_scope": scope})
            if "orders" in state:
                from compras_tn.application.task_orders import normalize_orders
                associations = []
                for order in state["orders"]:
                    supplier, _error = match_supplier_nickname(order["supplier"], self.suppliers.list())
                    associations.append({**order, "supplier": supplier.name if supplier else order["supplier"]})
                try:
                    task.payload["orders"] = normalize_orders(associations)
                except ValueError:
                    ready = False
            task = self._enrich_workflow_tasks([task])[0]
            self.inbox.synchronize_oc_task(task, ready)
            if ready:
                ready_tasks.append(task)
        ready_numbers = {task.task_number for task in ready_tasks}
        return [task for task in self.inbox.list_pending("carga_oc_automatica") if task.task_number in ready_numbers]

    def _validate_oc_snapshot(self, draft: PurchaseOrderDraft, *, live=None) -> None:
        if any(self.settings.get("oc_receipts", key, {}).get("state") in {"saving", "pending", "synced"}
               for key in self._oc_receipt_keys(draft)):
            raise ValueError("Recuperación pendiente; resuelva el intento anterior antes de crear otra OC.")
        if live is None:
            live = self._resolve_purchase_order_catalogs(self.sheets.read_purchase_order_drafts())
        matching = [item for item in live if (item.ruc, item.department, item.requester) == (draft.ruc, draft.department, draft.requester)
                    and set(item.source_rows) == set(draft.source_rows)]
        if (len(matching) != 1 or matching[0].articles != draft.articles
                or matching[0].original_drafts != draft.original_drafts or not matching[0].is_valid):
            raise ValueError("Los datos cambiaron en el conjunto de artículos de la tarea/proveedor; recargue GENERAL antes de guardar.")

    def _prepare_oc_save(self, draft: PurchaseOrderDraft) -> None:
        self._validate_oc_snapshot(draft)
        self._record_oc_receipt(draft, "saving")

    def _sync_saved_oc(self, draft: PurchaseOrderDraft, number: str) -> None:
        self._record_oc_receipt(draft, "pending", number)
        self.sheets.record_purchase_order(draft, number)
        self._record_oc_receipt(draft, "synced", number)
        self._ensure_approval_pending(draft, number)

    def _ensure_approval_pending(self, draft, number):
        key = self._oc_scope() + number
        if not self.settings.get("oc_approvals", key, {}):
            self.settings.set("oc_approvals", key, {"number": number, "state": "pending", "names": [],
                "draft": draft.model_dump(mode="json"), "at": utc_now().isoformat()})

    def _approve_saved_oc(self, draft, number, page):
        key = self._oc_scope() + number
        previous = self.settings.get("oc_approvals", key, {})
        def stage(state, names):
            current = self.settings.get("oc_approvals", key, {})
            history = list(current.get("history", []))
            if current:
                history.append({k: v for k, v in current.items() if k != "history"})
            value = {"number": number, "state": state, "names": names,
                     "draft": draft.model_dump(mode="json"), "at": utc_now().isoformat(), "history": history}
            self.settings.set("oc_approvals", key, value)
        if previous.get("state") == "synced":
            return
        if previous.get("state") == "read" and previous.get("names"):
            names = previous["names"]
        else:
            # Save a recovery record even if finding the send control fails.
            if not previous:
                stage("pending", [])
            names = page.send_and_read_approval(number, stage, previous.get("state", ""))
        self.sheets.record_approvers(draft, number, names)
        stage("synced", names)

    def pending_approval_recoveries(self):
        return [dict(entry, key=key) for key, entry in self.settings.list_namespace('oc_approvals').items()
                if key.startswith(self._oc_scope()) and entry.get('state') != 'synced']

    def recover_approvers(self, *, headless=False, progress=None, cancelled=None, keys=None):
        entries = [entry for key, entry in self.settings.list_namespace("oc_approvals").items()
                   if key.startswith(self._oc_scope()) and entry.get("state") != "synced"]
        if keys is not None:
            selected = set(keys)
            entries = [entry for entry in entries if self._oc_scope() + entry['number'] in selected]
        if not entries:
            return OperationResult.from_items([], "No hay aprobadores pendientes de recuperar.")
        batch = getattr(self.sheets, 'batch', None)
        with batch(progress, cancelled) if callable(batch) else nullcontext():
            return self.purchases.recover_approvers(self.credentials, entries, self._approve_saved_oc,
                        headless=headless, progress=progress, cancelled=cancelled)

    def _resolve_purchase_order_catalogs(
        self, drafts: Sequence[PurchaseOrderDraft]
    ) -> list[PurchaseOrderDraft]:
        suppliers = self.suppliers.list()
        result: list[PurchaseOrderDraft] = []
        for draft in drafts:
            supplier, error = match_supplier_nickname(draft.supplier, suppliers)
            errors = list(draft.validation_errors)
            if supplier is None:
                if error not in errors:
                    errors.append(error)
                result.append(draft.model_copy(update={"validation_errors": errors, "ruc": ""}))
                continue
            result.append(
                draft.model_copy(
                    update={
                        "supplier": supplier.name,
                        "supplier_reference": draft.supplier_reference or draft.supplier,
                        "ruc": supplier.ruc,
                        "validation_errors": errors,
                    }
                )
            )
        if any(draft.split_total > 1 for draft in drafts):
            planned = []
            for draft in result:
                parts = consolidate_orders([draft])
                if len(parts) == 1 and draft.split_total > 1:
                    parts[0].split_part, parts[0].split_total = draft.split_part, draft.split_total
                planned.extend(parts)
            return planned
        return consolidate_orders(result)

    def preload_purchase_orders(
        self,
        drafts: Sequence[PurchaseOrderDraft],
        *,
        headless: bool = False,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        drafts = self._block_oc_recoveries(self._resolve_purchase_order_catalogs(drafts))
        request = OperationRequest(
            kind="precarga_oc_bienes",
            mode=PurchaseMode.BIENES,
            items=[draft.model_dump(mode="json") for draft in drafts],
            options={"headless": headless},
        )

        def operation() -> OperationResult:
            blocked = [
                OperationItem(
                    key=draft.operation_key,
                    status=ItemStatus.FAILED,
                    error_code="validacion_hoja",
                    message=" ".join(draft.validation_errors),
                    payload={
                        "task_number": draft.task_number,
                        "supplier": draft.supplier,
                        "ruc": draft.ruc,
                        "requester": draft.requester,
                        "articles": len(draft.articles),
                        "subtotal": f"{draft.subtotal:.2f}",
                    },
                )
                for draft in drafts
                if not draft.is_valid
            ]
            valid = [draft for draft in drafts if draft.is_valid]
            if not valid:
                return OperationResult.from_items(blocked, "No existen órdenes válidas para precargar.")
            if self.purchases is None:
                raise RuntimeError("El módulo de automatización de OC no está configurado.")
            batch = getattr(self.sheets, 'batch', None)
            with batch(progress, cancelled) if callable(batch) else nullcontext():
                live = self._resolve_purchase_order_catalogs(self.sheets.read_purchase_order_drafts())
                for draft in valid:
                    self._validate_oc_snapshot(draft, live=live)
                result = self.purchases.preload(
                    self.credentials,
                    valid,
                    headless=headless,
                    progress=progress,
                    cancelled=cancelled,
                    before_save=self._prepare_oc_save,
                    on_saved=self._sync_saved_oc,
                    after_saved=self._approve_saved_oc,
                )
            if blocked:
                result.items.extend(blocked)
                if result.status == JobStatus.SUCCEEDED:
                    result.status = JobStatus.PARTIAL
            try:
                with batch(progress, cancelled) if callable(batch) else nullcontext():
                    self.reconcile_oc_tasks()
            except Exception as exc:
                result.message = self._append_message(result.message, f"No se actualizó el origen OC; reintente Actualizar origen OC: {exc}")
            return result

        return self._audited(
            request,
            operation,
            progress=progress,
            report_recipients=[self.credentials.email],
            report_title="Informe de órdenes precargadas",
        )

    def scan_reassignment_mail(
        self,
        start: datetime,
        end: datetime,
        sender: str,
        mode: PurchaseMode,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
        workflow_mail: bool = False,
    ) -> list[TaskRecord]:
        subject = str(
            self.settings.get("servicios", "cadena_asunto_fija", "NOTIFICACION A PROVEEDOR:")
        )
        scanner = getattr(self.mail, "scan_reassignment_tasks", self.mail.scan_tasks)
        if mode == PurchaseMode.BIENES and not workflow_mail:
            scanner = getattr(self.mail, "scan_goods_reassignment_tasks", self.mail.scan_tasks)
            subject = ""
            sender = sender.strip() or str(self.settings.get("bienes", "remitente_reasignacion", "omar777j@gmail.com"))
        if workflow_mail:
            scanner = self.mail.scan_tasks
        messages = scanner(
            self.credentials,
            start,
            end,
            subject,
            sender,
            progress=progress,
            cancelled=cancelled,
        )
        tasks: list[TaskRecord] = []
        for message in messages:
            number = str(message.get("task_number") or "").strip()
            if not number or number == "N/D":
                continue
            tasks.append(
                TaskRecord(
                    task_number=number,
                    origin="reasignacion",
                    purchase_mode=mode,
                    supplier=str(message.get("supplier") or ""),
                    payload=message,
                )
            )
        return tasks

    def scan_workflow_mail(
        self,
        start: datetime,
        end: datetime,
        sender: str,
        mode: PurchaseMode,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> list[TaskRecord]:
        tasks = self.scan_reassignment_mail(
            start,
            end,
            sender,
            mode,
            progress=progress,
            cancelled=cancelled,
            workflow_mail=True,
        )
        imported = [task.model_copy(update={"origin": "correo"}) for task in tasks]
        self._enqueue_workflow_tasks(imported)
        return imported

    def send_dispatch(
        self,
        order_numbers: Sequence[str],
        template: EmailTemplate,
        *,
        grouped: bool,
        mode: PurchaseMode,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        preview = self.prepare_dispatch(
            order_numbers,
            progress=progress,
            cancelled=cancelled,
        )
        return self.send_prepared_dispatch(
            preview,
            template,
            grouped=grouped,
            mode=mode,
            progress=progress,
            cancelled=cancelled,
        )

    def prepare_dispatch(
        self,
        order_numbers: Sequence[str],
        *,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> DispatchPreview:
        cc = self._email_list("email", "email_cc_despacho")
        preview: list[DispatchPreviewItem] = []
        unique_numbers = list(dict.fromkeys(str(number).strip() for number in order_numbers if str(number).strip()))
        total = len(unique_numbers)
        for index, number in enumerate(unique_numbers, start=1):
            if cancelled and cancelled():
                preview.extend(
                    DispatchPreviewItem(
                        order_number=pending,
                        error="Validación cancelada.",
                        cc=cc,
                    )
                    for pending in unique_numbers[index - 1 :]
                )
                break
            try:
                order = self.orders.resolve(number)
                recipients = list(dict.fromkeys(order.metadata.get("emails") or []))
                if not recipients:
                    raise ValueError("El proveedor no tiene correo registrado.")
                pdf = Path(order.pdf_path)
                stat = pdf.stat()
                tasks = self._order_task_numbers(order)
                preview.append(
                    DispatchPreviewItem(
                        order_number=number,
                        valid=True,
                        task_numbers=tasks,
                        supplier=order.supplier,
                        ruc=order.ruc,
                        recipients=recipients,
                        cc=cc,
                        pdf_path=str(pdf.resolve()),
                        pdf_mtime_ns=stat.st_mtime_ns,
                        pdf_size=stat.st_size,
                    )
                )
            except Exception as exc:
                preview.append(
                    DispatchPreviewItem(
                        order_number=number,
                        error=self._safe_text(exc),
                        cc=cc,
                    )
                )
            if progress:
                progress(index, total, f"Validada OC {number}")
        return DispatchPreview(items=preview)

    def send_prepared_dispatch(
        self,
        preview: DispatchPreview,
        template: EmailTemplate,
        *,
        grouped: bool,
        mode: PurchaseMode,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        request = OperationRequest(
            kind="correos_masivos",
            mode=mode,
            items=[item.model_dump(mode="json") for item in preview.items],
            options={"grouped": grouped, "template": template.name},
        )

        def operation() -> OperationResult:
            resolved: list[OrderRecord] = []
            items = [
                OperationItem(
                    key=item.order_number,
                    status=ItemStatus.FAILED,
                    message=item.error or "La orden no superó la validación previa.",
                )
                for item in preview.items
                if not item.valid
            ]
            valid_items = [item for item in preview.items if item.valid]
            total = len(valid_items)
            for index, prepared in enumerate(valid_items, start=1):
                if cancelled and cancelled():
                    items.extend(
                        OperationItem(
                            key=pending.order_number,
                            status=ItemStatus.SKIPPED,
                            message="No procesada por cancelación.",
                        )
                        for pending in valid_items[index - 1 :]
                    )
                    return OperationResult(
                        status=JobStatus.CANCELLED,
                        items=items,
                        finished_at=utc_now(),
                        message="Proceso de correos cancelado.",
                    )
                try:
                    current = self.orders.resolve(prepared.order_number)
                    pdf = Path(current.pdf_path).resolve()
                    stat = pdf.stat()
                    if (
                        str(pdf).casefold() != str(Path(prepared.pdf_path).resolve()).casefold()
                        or stat.st_mtime_ns != prepared.pdf_mtime_ns
                        or stat.st_size != prepared.pdf_size
                    ):
                        raise ValueError(
                            "El PDF cambió después del resumen. Vuelva a validar antes de enviar."
                        )
                    resolved.append(
                        current.model_copy(
                            update={
                                "task_number": prepared.task_numbers[0] if prepared.task_numbers else "",
                                "task_numbers": prepared.task_numbers,
                                "supplier": prepared.supplier,
                                "ruc": prepared.ruc,
                                "pdf_path": str(pdf),
                                "metadata": {**current.metadata, "emails": prepared.recipients},
                            }
                        )
                    )
                except Exception as exc:
                    items.append(
                        OperationItem(
                            key=prepared.order_number,
                            status=ItemStatus.FAILED,
                            message=self._safe_text(exc),
                        )
                    )
                if progress:
                    progress(index, total, f"Confirmada OC {prepared.order_number}")

            groups: list[list[Any]]
            if grouped:
                by_ruc: dict[str, list[Any]] = defaultdict(list)
                for order in resolved:
                    by_ruc[order.ruc or order.order_number].append(order)
                groups = list(by_ruc.values())
            else:
                groups = [[order] for order in resolved]

            def send_group(group: list[Any]) -> list[OperationItem]:
                if cancelled and cancelled():
                    return [
                        OperationItem(
                            key=order.order_number,
                            status=ItemStatus.SKIPPED,
                            message="No enviado por cancelación.",
                        )
                        for order in group
                    ]
                first = group[0]
                numbers = [order.order_number for order in group]
                task_numbers = list(
                    dict.fromkeys(
                        task
                        for order in group
                        for task in self._order_task_numbers(order)
                    )
                )
                recipients = sorted(
                    {address for order in group for address in order.metadata.get("emails", []) if address}
                )
                context = {
                    "orden": ", ".join(numbers),
                    "ordenes": numbers,
                    "tarea": ", ".join(task_numbers),
                    "tareas": task_numbers,
                    "proveedor": first.supplier,
                    "ruc": first.ruc,
                }
                subject = f"DESPACHO DE OC {', '.join(numbers)}"
                if task_numbers:
                    subject += f" TAREA {', '.join(task_numbers)}"
                try:
                    self.mail.send_html(
                        self.credentials,
                        recipients,
                        subject,
                        self.renderer.render(template, context),
                        [Path(order.pdf_path) for order in group],
                        self._email_list("email", "email_cc_despacho"),
                    )
                    return [
                        OperationItem(
                            key=order.order_number,
                            status=ItemStatus.SUCCEEDED,
                            message="Correo enviado.",
                            payload=order.model_dump(mode="json"),
                        )
                        for order in group
                    ]
                except Exception as exc:
                    return [
                        OperationItem(
                            key=order.order_number,
                            status=ItemStatus.FAILED,
                            message=str(exc),
                        )
                        for order in group
                    ]

            if groups:
                grouped_results: dict[int, list[OperationItem]] = {}
                with ThreadPoolExecutor(
                    max_workers=min(4, len(groups)),
                    thread_name_prefix="compras-smtp",
                ) as executor:
                    futures = {
                        executor.submit(send_group, group): index
                        for index, group in enumerate(groups)
                    }
                    completed = 0
                    for future in as_completed(futures):
                        group_index = futures[future]
                        completed += 1
                        if not future.cancelled():
                            try:
                                grouped_results[group_index] = future.result()
                            except Exception as exc:
                                grouped_results[group_index] = [
                                    OperationItem(
                                        key=order.order_number,
                                        status=ItemStatus.FAILED,
                                        message=str(exc),
                                    )
                                    for order in groups[group_index]
                                ]
                        if completed < len(groups) and cancelled and cancelled():
                            for pending in futures:
                                pending.cancel()
                        if progress:
                            progress(
                                completed,
                                len(groups),
                                f"Procesado grupo {completed} de {len(groups)}",
                            )
                for index, group in enumerate(groups):
                    items.extend(
                        grouped_results.get(
                            index,
                            [
                                OperationItem(
                                    key=order.order_number,
                                    status=ItemStatus.SKIPPED,
                                    message="No enviado por cancelación.",
                                )
                                for order in group
                            ],
                        )
                    )

            # Una solicitud de cancelación que llega cuando todo ya fue enviado no
            # debe convertir retroactivamente el resultado en cancelado. Solo lo es
            # si al menos un elemento quedó realmente sin enviar.
            cancelled_during_send = any(
                item.status == ItemStatus.SKIPPED
                and "cancelaci" in item.message.casefold()
                for item in items
            )

            queued = []
            for item in items:
                if item.status != ItemStatus.SUCCEEDED:
                    continue
                for task_number in self._payload_task_numbers(item.payload):
                    queued.append(
                        TaskRecord(
                            task_number=task_number,
                            origin="correos_masivos",
                            purchase_mode=mode,
                            order_number=item.key,
                            supplier=str(item.payload.get("supplier") or ""),
                            payload={**item.payload, "task_number": task_number},
                        )
                    )
            self._enqueue_workflow_tasks(queued)
            if cancelled_during_send:
                return OperationResult(
                    status=JobStatus.CANCELLED,
                    items=items,
                    finished_at=utc_now(),
                    message="Proceso de correos cancelado.",
                )
            return OperationResult.from_items(items, "Proceso de correos masivos finalizado.")

        return self._audited(request, operation, progress=progress)

    @staticmethod
    def _order_task_numbers(order: OrderRecord) -> list[str]:
        return list(
            dict.fromkeys(
                str(number).strip()
                for number in (order.task_numbers or [order.task_number])
                if str(number).strip()
            )
        )

    @staticmethod
    def _payload_task_numbers(payload: Mapping[str, Any]) -> list[str]:
        values = payload.get("task_numbers") or [payload.get("task_number")]
        if not isinstance(values, (list, tuple, set)):
            values = [values]
        return list(
            dict.fromkeys(
                str(number).strip() for number in values if str(number or "").strip()
            )
        )

    @staticmethod
    def _consolidate_download_request(request: OperationRequest) -> OperationRequest:
        """Agrupa una OC repetida sin perder tareas, proveedor ni correos de origen."""
        grouped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for index, source in enumerate(request.items):
            raw = dict(source)
            number = str(raw.get("order_number") or raw.get("numero") or "").strip()
            key = number or f"__sin_numero_{index}"
            if key not in grouped:
                grouped[key] = raw
                order.append(key)
            target = grouped[key]

            for field, value in raw.items():
                if field not in target or target[field] in (None, "", [], {}):
                    target[field] = value

            tasks: list[str] = []
            for item in (target, raw):
                values = item.get("task_numbers") or [
                    item.get("task_number") or item.get("tarea")
                ]
                if not isinstance(values, (list, tuple, set)):
                    values = [values]
                for value in values:
                    clean = str(value or "").strip()
                    if clean and clean not in tasks:
                        tasks.append(clean)
            if tasks:
                target["task_numbers"] = tasks
                target["task_number"] = tasks[0]

            suppliers: list[str] = []
            existing_suppliers = target.get("supplier_candidates") or []
            if not isinstance(existing_suppliers, (list, tuple, set)):
                existing_suppliers = [existing_suppliers]
            for value in (
                *existing_suppliers,
                target.get("supplier"),
                target.get("proveedor"),
                raw.get("supplier"),
                raw.get("proveedor"),
            ):
                clean = str(value or "").strip()
                if clean and clean.casefold() not in {
                    item.casefold() for item in suppliers
                }:
                    suppliers.append(clean)
            if suppliers:
                target["supplier"] = suppliers[0]
                target["supplier_candidates"] = suppliers

            external_ids: list[str] = []
            existing_ids = target.get("external_ids") or []
            if not isinstance(existing_ids, (list, tuple, set)):
                existing_ids = [existing_ids]
            for value in (*existing_ids, target.get("external_id"), raw.get("external_id")):
                clean = str(value or "").strip()
                if clean and clean not in external_ids:
                    external_ids.append(clean)
            if external_ids:
                target["external_ids"] = external_ids
                target["external_id"] = external_ids[0]
            if number:
                target["order_number"] = number

        return request.model_copy(
            update={"items": [grouped[key] for key in order]},
            deep=True,
        )

    def send_followups(
        self,
        selected: Sequence[dict[str, Any]],
        template: EmailTemplate,
        *,
        attach_pdf: bool,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        request = OperationRequest(kind="seguimientos", mode=PurchaseMode.BIENES, items=list(selected))

        def operation() -> OperationResult:
            def process(raw: dict[str, Any]) -> OperationItem:
                number = str(raw.get("order_number") or "")
                if cancelled and cancelled():
                    return OperationItem(
                        key=number,
                        status=ItemStatus.SKIPPED,
                        message="No enviado por cancelación.",
                    )
                try:
                    order = self.orders.resolve(number)
                    recipients = list(order.metadata.get("emails") or [])
                    if not recipients:
                        raise ValueError("El proveedor no tiene correo registrado.")
                    context = {
                        "orden": order.order_number,
                        "tarea": raw.get("task_number") or order.task_number,
                        "proveedor": raw.get("supplier") or order.supplier,
                    }
                    self.mail.send_html(
                        self.credentials,
                        recipients,
                        f"SEGUIMIENTO OC {order.order_number}",
                        self.renderer.render(template, context),
                        [Path(order.pdf_path)] if attach_pdf else [],
                        self._email_list("email", "email_cc_seguimiento"),
                    )
                    return OperationItem(
                        key=number,
                        status=ItemStatus.SUCCEEDED,
                        message="Seguimiento enviado.",
                    )
                except Exception as exc:
                    return OperationItem(
                        key=number,
                        status=ItemStatus.FAILED,
                        message=str(exc),
                    )

            results_by_index: dict[int, OperationItem] = {}
            if selected:
                with ThreadPoolExecutor(
                    max_workers=min(4, len(selected)),
                    thread_name_prefix="compras-seguimiento",
                ) as executor:
                    futures = {
                        executor.submit(process, dict(raw)): index
                        for index, raw in enumerate(selected)
                    }
                    completed = 0
                    for future in as_completed(futures):
                        index = futures[future]
                        completed += 1
                        if not future.cancelled():
                            try:
                                results_by_index[index] = future.result()
                            except Exception as exc:
                                results_by_index[index] = OperationItem(
                                    key=str(selected[index].get("order_number") or ""),
                                    status=ItemStatus.FAILED,
                                    message=str(exc),
                                )
                        if completed < len(selected) and cancelled and cancelled():
                            for pending in futures:
                                pending.cancel()
                        if progress:
                            progress(
                                completed,
                                len(selected),
                                f"Procesado seguimiento {completed} de {len(selected)}",
                            )
            results = [
                results_by_index.get(
                    index,
                    OperationItem(
                        key=str(raw.get("order_number") or ""),
                        status=ItemStatus.SKIPPED,
                        message="No enviado por cancelación.",
                    ),
                )
                for index, raw in enumerate(selected)
            ]
            cancelled_during_send = any(
                item.status == ItemStatus.SKIPPED
                and "cancelaci" in item.message.casefold()
                for item in results
            )
            if cancelled_during_send:
                return OperationResult(
                    status=JobStatus.CANCELLED,
                    items=results,
                    finished_at=utc_now(),
                    message="Seguimientos cancelados.",
                )
            return OperationResult.from_items(results, "Seguimientos finalizados.")

        return self._audited(request, operation, progress=progress)

    def reassign_tasks(
        self,
        tasks: Sequence[TaskRecord],
        department: str,
        employee: str,
        comment: str,
        *,
        headless: bool,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        assignments = {item.subdepartment.strip().upper(): item for item in self.list_assignments()}
        for task in tasks:
            if task.purchase_mode == PurchaseMode.BIENES:
                key = str(task.payload.get("reasignacion", "")).strip().upper()
                target = assignments.get(key)
                if target is None or not target.department.strip() or not target.person.strip():
                    raise ValueError(f"Tarea {task.task_number}: configure la asignación de '{key}' antes de ejecutar.")
                if not task.payload.get("details"):
                    raise ValueError(f"Tarea {task.task_number}: faltan los datos de OC, factura e ingreso del correo.")
                task.payload.update(department_override=target.department, employee_override=target.person)
        mode = tasks[0].purchase_mode if tasks else PurchaseMode.GENERAL
        request = OperationRequest(kind="reasignacion", mode=mode, items=[task.model_dump(mode="json") for task in tasks])

        def operation() -> OperationResult:
            result = self.telcos.reassign(
                self.credentials,
                tasks,
                department,
                employee,
                comment,
                headless=headless,
                progress=progress,
                cancelled=cancelled,
            )
            succeeded = {item.key for item in result.items if item.status == ItemStatus.SUCCEEDED}
            self._enqueue_workflow_tasks([task for task in tasks if task.task_number in succeeded])
            return result

        return self._audited(
            request,
            operation,
            progress=progress,
            report_recipients=self._automation_report_recipients(),
            report_title="Reasignación",
        )

    def document_types(self):
        from compras_tn.infrastructure.document_files import file_types
        return file_types(self.settings)

    def add_document_type(self, name: str, words: str, **options):
        from compras_tn.infrastructure.document_files import add_type
        return add_type(self.settings, name, words, **options)

    def prepare_workflow_files(self, workflow, tasks, progress=None, cancelled=None):
        from compras_tn.application.workflows import expand_workflow
        workflow = expand_workflow(workflow)
        from compras_tn.infrastructure.document_files import (
            DocumentFileResolver,
            FolderChoiceRequired,
        )
        resolver = DocumentFileResolver(self.settings)
        results = []
        for index, task in enumerate(tasks, 1):
            if cancelled and cancelled():
                break
            if progress:
                progress(index, len(tasks), f"Validando archivos de la tarea {task.task_number}")
            try:
                manifests = resolver.prepare(workflow, task)
                prepared = task.model_copy(update={"payload": {**task.payload, "document_file_manifests": manifests}})
                results.append({"task": prepared, "error": "", "choices": []})
            except FolderChoiceRequired as exc:
                results.append({"task": task, "error": str(exc), "choices": exc.candidates, "step": exc.step})
            except (OSError, ValueError) as exc:
                results.append({"task": task, "error": str(exc), "choices": []})
        return results

    def scan_quotations(self, start, end, tasks=None, progress=None, cancelled=None):
        return self.quotations.scan(self.credentials, start, end, tasks, progress, cancelled)

    def review_local_quotation_tasks(self, rows, progress=None, cancelled=None):
        return self.quotations.review_local_tasks(rows, progress, cancelled)

    def review_local_quotation_task(self, row):
        return self.quotations.review_local_task(row)

    def scan_local_quotations(self, paths, progress=None, cancelled=None):
        return self.quotations.scan_local(paths, progress, cancelled)

    def prepare_quotation_save(self, rows):
        return self.quotations.prepare_save(rows)

    def save_quotations(self, rows, progress=None, cancelled=None):
        self._cycle_notice(OperationRequest(kind="organizar_cotizaciones", items=list(rows)), progress)
        return self.quotations.save(rows, progress, cancelled)

    def workflow_cycle_stage(self, workflow):
        from compras_tn.application.task_cycle import workflow_stage
        configured = self.settings.get("workflow_cycle", str(workflow.id), 0) if workflow.id else 0
        return int(configured) or workflow_stage(workflow.name)

    def _cycle_notice(self, request, progress=None):
        from compras_tn.application.task_cycle import TaskCycle
        try:
            message = TaskCycle(self.jobs).warnings(request)
        except Exception as exc:
            if progress:
                progress(0, max(1, len(request.items)), "No se pudo comprobar el historial del ciclo: " + self._safe_text(exc))
            return ''
        if message:
            confirm = getattr(progress, 'confirm_cycle', None)
            if callable(confirm):
                if not confirm(message):
                    raise CycleDeclined('Proceso cancelado: no se confirmó continuar con pasos anteriores pendientes.')
                if progress:
                    progress(0, max(1, len(request.items)), 'Continuación confirmada por el usuario.')
            elif progress:
                progress(0, max(1, len(request.items)), message)
        return message

    def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        tasks: Sequence[TaskRecord],
        *,
        headless: bool,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        from compras_tn.application.workflows import expand_workflow
        workflow = expand_workflow(workflow)
        request = OperationRequest(
            kind="actualizar_tareas",
            mode=workflow.mode,
            items=[task.model_dump(mode="json") for task in tasks],
            options={"workflow": workflow.name, "cycle_stage": self.workflow_cycle_stage(workflow), "headless": headless, "stop_on_error": workflow.stop_on_error},
        )

        def operation() -> OperationResult:
            warnings: list[str] = []
            scope = self._oc_scope()
            tracked = {value["task_number"] for key, value in self.settings.list_namespace("oc_task_candidates").items() if key.startswith(scope)}
            if any(task.task_number in tracked or task.origin == "carga_oc_automatica" for task in tasks):
                try:
                    ready = {task.task_number for task in self.reconcile_oc_tasks()}
                    invalid = [task.task_number for task in tasks if (task.task_number in tracked or task.origin == "carga_oc_automatica") and task.task_number not in ready]
                    if invalid:
                        warnings.append(
                            "Tareas con OC pendientes o sin verificar: " + ", ".join(invalid)
                        )
                except Exception as exc:
                    warnings.append(
                        "No se pudo verificar el estado de las OC; se continuará con las "
                        f"tareas seleccionadas: {self._safe_text(exc)}"
                    )
            if warnings and progress:
                progress(0, len(tasks), "Advertencia: " + " ".join(warnings))
            result = self.telcos.execute_workflow(
                self.credentials,
                workflow,
                tasks,
                headless=headless,
                progress=progress,
                cancelled=cancelled,
            )
            if warnings:
                result.message = self._append_message(
                    result.message,
                    "Advertencia: " + " ".join(warnings),
                )
            failed_keys = {item.key for item in result.items if item.status != ItemStatus.SUCCEEDED}
            done = [item.key for item in result.items
                    if item.status == ItemStatus.SUCCEEDED and item.key not in failed_keys]
            for task in tasks:
                if task.task_number not in done:
                    continue
                origins = task.payload.get('origins') or [task.origin]
                if isinstance(origins, str):
                    origins = [origins]
                for origin in dict.fromkeys(origins):
                    self.inbox.consume([task.task_number], origin=origin)
            return result

        return self._audited(
            request,
            operation,
            progress=progress,
            report_recipients=self._automation_report_recipients(),
            report_title="Actualizar Tareas",
        )

    def download_orders(
        self,
        request: OperationRequest,
        *,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        report_key = (
            "abastecimiento_correo_reporte"
            if request.kind == "descarga_abastecimiento"
            else "correo_reporte"
        )
        return self._audited(
            request,
            lambda: self._download_orders_operation(request, progress, cancelled),
            report_recipients=self._email_list("downloads", report_key),
            legacy_download_report=True,
        )

    def scan_and_download_orders(
        self,
        mode: PurchaseMode,
        *,
        headless: bool,
        progress: Progress | None = None,
        cancelled: Cancelled | None = None,
    ) -> OperationResult:
        audit_request = OperationRequest(
            kind="escaneo_descargas",
            mode=mode,
            options={"headless": headless, "source": "email"},
        )

        def operation() -> OperationResult:
            messages = self.order_mail.scan(
                self.credentials,
                progress=progress,
                cancelled=cancelled,
            )
            if cancelled and cancelled():
                return OperationResult(
                    status=JobStatus.CANCELLED,
                    finished_at=utc_now(),
                    message="Escaneo cancelado.",
                )
            items = [
                dict(order, external_id=message.external_id)
                for message in messages
                for order in message.orders
            ]
            if not items:
                return OperationResult(
                    status=JobStatus.SUCCEEDED,
                    finished_at=utc_now(),
                    message="No existen órdenes nuevas en el correo.",
                )
            download_request = OperationRequest(
                kind="descarga_normal",
                mode=mode,
                items=items,
                options={"headless": headless, "source": "email"},
            )
            result = self._download_orders_operation(download_request, progress, cancelled)
            result_by_order = {item.key: item.status for item in result.items}
            completed_messages = [
                message.external_id
                for message in messages
                if message.orders
                and all(
                    result_by_order.get(
                        str(order.get("order_number") or order.get("numero") or "")
                    )
                    in {ItemStatus.SUCCEEDED, ItemStatus.SKIPPED}
                    for order in message.orders
                )
            ]
            try:
                self.order_mail.mark_processed(completed_messages)
            except Exception as exc:
                result.message = self._append_message(
                    result.message,
                    f"No se pudo registrar el punto de control del correo: {exc}",
                )
            return result

        return self._audited(
            audit_request,
            operation,
            report_recipients=self._email_list("downloads", "correo_reporte"),
            legacy_download_report=True,
        )

    def _download_orders_operation(
        self,
        request: OperationRequest,
        progress: Progress | None,
        cancelled: Cancelled | None,
    ) -> OperationResult:
        effective_request = self._consolidate_download_request(request)
        cycle_warning = self._cycle_notice(effective_request, progress)
        download_progress = progress
        if not effective_request.items and progress:
            facade = self
            class DiscoveredProgress:
                def __call__(self, current, total, text):
                    progress(current, total, text)

                def check_cycle(self, items):
                    nonlocal cycle_warning
                    cycle_warning = facade._cycle_notice(effective_request.model_copy(update={'items': items}), progress)
            download_progress = DiscoveredProgress()
        result = self.downloads.download(
            self.credentials,
            effective_request,
            progress=download_progress,
            cancelled=cancelled,
        )
        if cycle_warning:
            result.message = self._append_message(result.message, cycle_warning)
        queued: list[TaskRecord] = []
        for item in result.items:
            if item.status != ItemStatus.SUCCEEDED:
                continue
            destinations = {
                str(destination.get("task_number") or "").strip(): destination
                for destination in item.payload.get("task_destinations", [])
                if destination.get("preparation_status") == "succeeded"
                and str(destination.get("task_number") or "").strip()
            }
            for task_number in self._payload_task_numbers(item.payload):
                destination = destinations.get(task_number, {})
                if item.payload.get("task_destinations") and not destination:
                    continue
                payload = {
                    **item.payload,
                    **destination,
                    "task_number": task_number,
                }
                queued.append(
                    TaskRecord(
                        task_number=task_number,
                        origin="descargas",
                        purchase_mode=request.mode,
                        order_number=str(item.payload.get("order_number") or item.key),
                        supplier=str(item.payload.get("supplier") or ""),
                        payload=payload,
                    )
                )
        self._enqueue_workflow_tasks(queued)
        return result

    def _audited(
        self,
        request: OperationRequest,
        callback: Callable[[], OperationResult],
        *,
        report_recipients: Sequence[str] = (),
        report_title: str = "",
        legacy_download_report: bool = False,
        progress: Progress | None = None,
    ) -> OperationResult:
        run_id: int | None = None
        audit_warning = ""
        # Downloads check after resolving the actual OC list, including mail scans.
        try:
            cycle_warning = "" if request.kind.startswith("descarga") or request.kind == "escaneo_descargas" else self._cycle_notice(request, progress)
        except CycleDeclined as exc:
            return OperationResult(status=JobStatus.CANCELLED, finished_at=utc_now(), message=str(exc))
        try:
            run_id = self.jobs.start(request)
        except Exception as exc:
            audit_warning = self._safe_text(f"No se pudo iniciar la auditoría: {exc}")
        try:
            result = callback()
        except CycleDeclined as exc:
            result = OperationResult(status=JobStatus.CANCELLED, finished_at=utc_now(), message=str(exc))
        except Exception as exc:
            result = OperationResult(
                status=JobStatus.FAILED,
                finished_at=utc_now(),
                message=self._safe_text(exc),
            )
        result = self._safe_result(result)
        if cycle_warning:
            result.message = self._append_message(result.message, cycle_warning)
        if audit_warning:
            result.message = self._append_message(result.message, audit_warning)
        try:
            result.report_path = str(self.reports.write(request, result))
        except Exception as exc:
            result.message = self._append_message(
                result.message,
                f"No se pudo crear el reporte: {exc}",
            )
        if result.status == JobStatus.CANCELLED:
            report_recipients = ()
        if report_recipients and legacy_download_report:
            self._send_download_report(request, result, report_recipients)
        elif report_recipients and report_title:
            self._send_report(request, result, report_recipients, report_title)
        result = self._safe_result(result)
        if run_id is not None:
            try:
                self.jobs.finish(run_id, result)
            except Exception as exc:
                result.message = self._append_message(
                    result.message,
                    f"No se pudo finalizar la auditoría: {exc}",
                )
        return self._safe_result(result)

    def _send_report(
        self,
        request: OperationRequest,
        result: OperationResult,
        recipients: Sequence[str],
        title: str,
    ) -> None:
        if not recipients:
            return
        try:
            from compras_tn.infrastructure.operation_report import render_operation_report
            report = render_operation_report(request, result, title)
            sender = getattr(self.mail, "send_html_with_text", None)
            if callable(sender):
                sender(self.credentials, recipients, report.subject, report.html, report.text)
            else:
                self.mail.send_html(self.credentials, recipients, report.subject, report.html)
        except Exception as exc:
            result.message = self._append_message(
                result.message,
                f"No se pudo enviar el reporte: {exc}",
            )

    def _send_download_report(
        self,
        request: OperationRequest,
        result: OperationResult,
        recipients: Sequence[str],
    ) -> None:
        from compras_tn.infrastructure.download_report import render_download_report

        report = render_download_report(request, result)
        if report is None or not recipients:
            return
        try:
            multipart_sender = getattr(self.mail, "send_html_with_text", None)
            if callable(multipart_sender):
                multipart_sender(
                    self.credentials,
                    recipients,
                    report.subject,
                    report.html,
                    report.text,
                )
            else:
                self.mail.send_html(
                    self.credentials,
                    recipients,
                    report.subject,
                    report.html,
                )
        except Exception as exc:
            result.message = self._append_message(
                result.message,
                f"No se pudo enviar el reporte: {exc}",
            )

    def _automation_report_recipients(self) -> list[str]:
        configured = self.settings.get("automation", "actua_report_email", "")
        # En la aplicación anterior ACTUA_REPORT_EMAIL era un booleano. Las
        # bases ya migradas pueden conservar todavía ese valor.
        if self._is_boolean_value(configured):
            enabled = self._as_bool(configured)
            explicit: list[str] = []
        else:
            enabled = self._as_bool(
                self.settings.get("automation", "actua_send_report", True)
            )
            explicit = self._email_list("automation", "actua_report_email")
        if not enabled:
            return []
        return explicit or [self.credentials.email]

    def _email_list(self, namespace: str, key: str) -> list[str]:
        value = self.settings.get(namespace, key, "")
        if isinstance(value, list):
            raw = [str(item).strip() for item in value]
        else:
            raw = str(value or "").replace(",", ";").split(";")
        result: list[str] = []
        for part in raw:
            address = part.strip()
            if "@" not in address or any(character.isspace() for character in address):
                continue
            if address.casefold() not in {item.casefold() for item in result}:
                result.append(address)
        return result

    def _safe_result(self, result: OperationResult) -> OperationResult:
        secrets = (self._credentials.password,) if self._credentials is not None else ()
        safe_items = [
            item.model_copy(
                update={
                    "key": sanitize_text(item.key, secrets),
                    "message": sanitize_text(item.message, secrets),
                    "payload": sanitize_data(item.payload, secrets),
                }
            )
            for item in result.items
        ]
        return result.model_copy(
            update={
                "items": safe_items,
                "message": sanitize_text(result.message, secrets),
                "report_path": sanitize_text(result.report_path, secrets),
            }
        )

    def _safe_text(self, value: object) -> str:
        secrets = (self._credentials.password,) if self._credentials is not None else ()
        return sanitize_text(value, secrets)

    def _append_message(self, current: str, extra: object) -> str:
        safe = self._safe_text(extra).strip()
        return " ".join(part for part in (current.strip(), safe) if part)

    @staticmethod
    def _is_boolean_value(value: Any) -> bool:
        return isinstance(value, bool) or str(value).strip().casefold() in {
            "0",
            "1",
            "false",
            "no",
            "si",
            "sí",
            "true",
            "yes",
        }

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "si", "sí"}
