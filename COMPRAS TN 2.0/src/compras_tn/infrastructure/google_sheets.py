from __future__ import annotations

import csv
import io
import re
import time
import threading
from contextlib import contextmanager
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from typing import Any

import gspread
import requests
from google.auth.exceptions import TransportError
from google.oauth2.service_account import Credentials

from compras_tn.application.ports import SettingsRepository
from compras_tn.infrastructure.sheets_transport import QuotaHTTPClient, sheets_context
from compras_tn.domain.models import PurchaseOrderArticle, PurchaseOrderDraft

TASK_PATTERN = re.compile(r"(?:TAREA\s*#?\s*)?(\d{6,14})", re.IGNORECASE)
HEADER_WORDS = {"codigo", "código", "descripcion", "descripción", "articulo", "artículo"}
DEFAULT_SHEET_ID = ""
PURCHASE_ORDER_START_ROW = 7346


class GoogleSheetsGateway:
    def read_task_orders(self, numbers: list[str]) -> dict[str, list[dict]]:
        name = str(self.settings.get("google", "google_oc_sheet_name", "GENERAL") or "GENERAL")
        worksheet = self._worksheet(name, timeout=(10, 20))
        rows = worksheet.get("A:O", value_render_option="UNFORMATTED_VALUE")
        wanted = set(numbers)
        result = {number: [] for number in wanted}
        task = ""
        seen = {}
        for raw in rows:
            row = list(raw) + [""] * max(0, 15 - len(raw))
            task = self._task_marker(row[2]) or task
            number = self._text(row[6])
            if task not in wanted or not re.fullmatch(r"\d{4,14}", number):
                continue
            names = list(dict.fromkeys(n.strip() for n in self._text(row[14]).split(",") if n.strip()))
            item = dict(order_number=number, supplier=self._text(row[4]), approvers=names)
            key = (task, number, item["supplier"])
            for previous in result[task]:
                if previous["order_number"] == number and previous["approvers"] != names:
                    raise ValueError(f"GENERAL contiene aprobadores contradictorios para tarea {task}, OC {number}.")
            if key in seen:
                if seen[key] != item:
                    raise ValueError(f"GENERAL contiene datos contradictorios para tarea {task}, OC {number}.")
            else:
                seen[key] = item
                result[task].append(item)
        return result

    def record_approvers(self, draft: PurchaseOrderDraft, number: str, names: list[str]) -> None:
        if not names:
            raise ValueError("NAF no proporcionó aprobadores pendientes; no se vació la columna O.")
        text = ", ".join(dict.fromkeys(name.strip() for name in names if name.strip()))
        for attempt in range(3):
            try:
                # Same identity checks as G; an existing matching OC is idempotent.
                self.record_purchase_order(draft, number)
                tab = str(self.settings.get("google", "google_oc_sheet_name", "GENERAL") or "GENERAL")
                worksheet = self._worksheet(tab, writable=True)
                columns = getattr(worksheet, "col_count", 15)
                if columns < 15:
                    worksheet.add_cols(15 - columns)
                cells = [f"O{a.source_row}" for a in draft.original_articles]
                before = self._batch_cells(worksheet, ['O1', *cells])
                header = before['O1']
                current_header = self._text(header[0][0]) if header and header[0] else ""
                if current_header and current_header.upper() != "APROBADORES PENDIENTES":
                    raise ValueError("O1 contiene un encabezado incompatible; no se sobrescribió.")
                updates = [] if current_header else [{"range": "O1", "values": [["APROBADORES PENDIENTES"]]}]
                for cell in cells:
                    existing = before[cell]
                    value = self._text(existing[0][0]) if existing and existing[0] else ""
                    if value.startswith("="):
                        raise ValueError(f"{cell} contiene una fórmula; no se sobrescribió.")
                    if value != text:
                        updates.append({"range": cell, "values": [[text]]})
                if updates:
                    worksheet.batch_update(updates, value_input_option="RAW")
                confirmed = self._batch_cells(worksheet, ['O1', *cells])
                for cell in ["O1", *cells]:
                    actual = confirmed[cell]
                    expected = "APROBADORES PENDIENTES" if cell == "O1" else text
                    if not actual or not actual[0] or self._text(actual[0][0]) != expected:
                        raise requests.ConnectionError(f"Sincronización de aprobadores pendiente en {cell}.")
                return
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    def __init__(self, settings: SettingsRepository):
        self.settings = settings
        self._sessions = threading.local()

    @contextmanager
    def batch(self, progress=None, cancelled=None):
        previous = getattr(self._sessions, 'worksheets', None)
        self._sessions.worksheets = {} if previous is None else previous
        try:
            with sheets_context(progress, cancelled):
                yield
        finally:
            self._sessions.worksheets = previous

    @staticmethod
    def _batch_cells(worksheet, cells):
        reader = getattr(worksheet, 'batch_get', None)
        if callable(reader):
            result = reader(list(cells), value_render_option='FORMULA')
            if len(result) != len(cells):
                raise requests.ConnectionError('Google Sheets no devolvió todos los rangos solicitados.')
            return dict(zip(cells, result))
        return {cell: worksheet.get(cell, value_render_option='FORMULA') for cell in cells}

    def read_approved_orders(self) -> list[dict[str, Any]]:
        worksheet_name = str(
            self.settings.get("google", "google_sheet_name", "")
            or self.settings.get("google", "google_oc_sheet_name", "GENERAL")
            or "GENERAL"
        )
        rows = self._records(worksheet_name)
        result: list[dict[str, Any]] = []
        for raw in rows:
            normalized = {str(key).strip().casefold(): value for key, value in raw.items()}
            status = str(
                normalized.get("estado aprobación")
                or normalized.get("estado aprobacion")
                or normalized.get("estado")
                or ""
            ).strip().casefold()
            if status and "aprob" not in status:
                continue
            order = normalized.get("orden de compra") or normalized.get("oc") or ""
            if not str(order).strip():
                continue
            result.append(
                {
                    "order_number": str(order).strip(),
                    "task_number": str(normalized.get("tarea") or "").strip(),
                    "supplier": str(normalized.get("proveedor") or "").strip(),
                    "raw": raw,
                }
            )
        return result

    def read_purchase_order_drafts(self) -> list[PurchaseOrderDraft]:
        for attempt in range(3):
            try:
                return self._read_purchase_order_drafts_once()
            except (requests.ConnectionError, requests.Timeout, ConnectionError, TransportError) as exc:
                if attempt == 2:
                    raise ConnectionError(
                        "Se interrumpio la lectura de GENERAL tras tres intentos. "
                        "No se pudo validar la hoja. Vuelva a cargar GENERAL."
                    ) from exc
                time.sleep(attempt + 1)

    def _read_purchase_order_drafts_once(self) -> list[PurchaseOrderDraft]:
        worksheet_name = str(
            self.settings.get("google", "google_oc_sheet_name", "GENERAL")
        ).strip() or "GENERAL"
        # UNFORMATTED_VALUE evita que cantidades y precios dependan del formato
        # visual o de la configuración regional de la hoja.
        worksheet = self._worksheet(worksheet_name, timeout=(10, 30))
        rows = worksheet.get(f"A{PURCHASE_ORDER_START_ROW}:L", value_render_option="UNFORMATTED_VALUE")
        formulas = worksheet.get(f"G{PURCHASE_ORDER_START_ROW}:G{PURCHASE_ORDER_START_ROW + len(rows) - 1}", value_render_option="FORMULA") if rows else []
        for index, raw in enumerate(rows):
            values = formulas[index] if index < len(formulas) else []
            current = values[0] if values else ""
            rows[index] = list(raw) + [""] * max(0, 7 - len(raw))
            rows[index][6] = "FORMULA: revisar OC" if str(current).startswith("=") else current
        return self.parse_purchase_order_rows(rows, start_row=PURCHASE_ORDER_START_ROW)

    def read_task_catalog(self) -> dict[str, dict[str, Any]]:
        name = str(self.settings.get("google", "google_oc_sheet_name", "GENERAL") or "GENERAL")
        for attempt in range(3):
            try:
                return self.parse_task_catalog(self._rows(name, range_name="B:L"))
            except (requests.ConnectionError, requests.Timeout, ConnectionError) as exc:
                if attempt == 2:
                    raise ConnectionError(
                        "Se interrumpio la lectura de GENERAL tras tres intentos. "
                        "No se guardo ningun archivo. Revise la conexion y vuelva a intentar."
                    ) from exc
                time.sleep(attempt + 1)

    @classmethod
    def parse_task_catalog(cls, rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
        catalog: dict[str, dict[str, Any]] = {}
        blocks: list[tuple[str, int, list[list[Any]]]] = []
        current = ""
        block: list[list[Any]] = []
        start = 0
        for number, raw in enumerate(rows, 1):
            row = list(raw) + [""] * max(0, 11 - len(raw))
            label = cls._text(row[1])
            marker = cls._task_marker(label) if not cls._text(row[0]) and re.fullmatch(r"(?:TAREA\s*#?\s*)?\d{6,14}", label, re.I) else ""
            if marker:
                if current:
                    blocks.append((current, start, block))
                current, start, block = marker, number, [row]
            elif current:
                block.append(row)
        if current:
            blocks.append((current, start, block))
        for task, start, block in blocks:
            descriptions = list(dict.fromkeys(cls._text(r[10]) for r in block if cls._text(r[10])))
            project = cls._text(block[0][10]) or (descriptions[0] if len(descriptions) == 1 else "")
            entry = catalog.setdefault(task, {"task_number": task, "project": project, "items": [], "blocks": [], "error": ""})
            entry["blocks"].append(start)
            entry["items"].extend({"row": start+i, "code": cls._text(row[0]), "description": cls._text(row[1])} for i, row in enumerate(block[1:], 1) if cls._text(row[0]) or cls._text(row[1]))
            if len({cls._plain(d) for d in descriptions}) > 1:
                entry["error"] = "La tarea tiene descripciones de proyecto contradictorias en GENERAL."
            elif not project:
                entry["error"] = "Falta una descripción única del proyecto en la columna L."
            elif entry["project"] and cls._plain(entry["project"]) != cls._plain(project):
                entry["error"] = "La tarea tiene descripciones de proyecto contradictorias en GENERAL."
            else:
                entry["project"] = project
        return catalog

    def validate_purchase_order(self, draft: PurchaseOrderDraft) -> None:
        live = self.read_purchase_order_drafts()
        by_row = {a.source_row: (group, a) for group in live for a in group.articles}
        for source in draft.original_drafts:
            self._validate_source(source, by_row)

    def read_purchase_task_status(self) -> dict[str, Any]:
        name = str(self.settings.get("google", "google_oc_sheet_name", "GENERAL") or "GENERAL")
        worksheet = self._worksheet(name)
        rows = worksheet.get(f"A{PURCHASE_ORDER_START_ROW}:O", value_render_option="UNFORMATTED_VALUE")
        values = worksheet.get(f"G{PURCHASE_ORDER_START_ROW}:G{PURCHASE_ORDER_START_ROW + len(rows) - 1}", value_render_option="FORMULA") if rows else []
        orders = {}
        approvers = {}
        originals = []
        for index, raw in enumerate(rows):
            row = list(raw) + [""] * max(0, 15 - len(raw))
            approvers[index + PURCHASE_ORDER_START_ROW] = list(dict.fromkeys(n.strip() for n in self._text(row[14]).split(",") if n.strip()))
            orders[index + PURCHASE_ORDER_START_ROW] = self._text(values[index][0]) if index < len(values) and values[index] else ""
            row[6] = ""
            originals.append(row)
        result: dict[str, Any] = {}
        for draft in self.parse_purchase_order_rows(originals, start_row=PURCHASE_ORDER_START_ROW):
            state = result.setdefault(draft.task_number, {"ready": True, "rows": {}, "order_numbers": [], "suppliers": []})
            associations = state.setdefault("orders", [])
            for article in draft.articles:
                number = orders[article.source_row]
                state["ready"] = state["ready"] and bool(re.fullmatch(r"\d{4,14}", number))
                state["rows"][str(article.source_row)] = {"order_number": number, "article": article.model_dump(mode="json")}
                if number and number not in state["order_numbers"]:
                    state["order_numbers"].append(number)
                association = {"order_number": number, "supplier": draft.supplier, "approvers": approvers[article.source_row]}
                if number and association not in associations:
                    associations.append(association)
            if draft.supplier not in state["suppliers"]:
                state["suppliers"].append(draft.supplier)
        return result

    @staticmethod
    def _validate_source(draft: PurchaseOrderDraft, by_row: dict[int, Any]) -> None:
        for article in draft.articles:
            current = by_row.get(article.source_row)
            if current is None:
                raise ValueError(f"Fila {article.source_row}: dejó de ser elegible o ya tiene OC; recargue GENERAL.")
            group, actual = current
            if (group.task_number != draft.task_number or actual != article or
                    any(getattr(group, key) != getattr(draft, key) for key in ("requester", "pedido", "department", "detail"))):
                raise ValueError(f"Fila {article.source_row}: los datos cambiaron; recargue GENERAL.")

    def _configuration(self, worksheet_name: str) -> tuple[str, str, str]:
        credentials_path = str(self.settings.get("google", "google_creds", "")).strip()
        sheet_id = str(
            self.settings.get("google", "google_sheet_id", "") or DEFAULT_SHEET_ID
        ).strip()
        worksheet_name = worksheet_name.strip()
        if not sheet_id or not worksheet_name:
            raise ValueError(
                "Falta el ID del Google Sheet o el nombre de la pestaña en Configuración."
            )
        return credentials_path, sheet_id, worksheet_name

    def _worksheet(self, worksheet_name: str, *, writable: bool = False, timeout=None):
        credentials_path, sheet_id, worksheet_name = self._configuration(worksheet_name)
        if not credentials_path:
            raise ValueError("No se configuró un archivo de credenciales Google.")
        cache = getattr(self._sessions, 'worksheets', None)
        key = (credentials_path, sheet_id, worksheet_name, writable)
        if cache is not None and key in cache:
            return cache[key]
        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=("https://www.googleapis.com/auth/spreadsheets" if writable else "https://www.googleapis.com/auth/spreadsheets.readonly",),
        )
        client = gspread.authorize(credentials, http_client=QuotaHTTPClient)
        client.set_timeout(timeout or (10, 30))
        worksheet = client.open_by_key(sheet_id).worksheet(worksheet_name.strip())
        if cache is not None:
            cache[key] = worksheet
        return worksheet

    def _rows(
        self,
        worksheet_name: str,
        *,
        unformatted: bool = False,
        range_name: str = "",
    ) -> list[list[Any]]:
        credentials_path, sheet_id, worksheet_name = self._configuration(worksheet_name)
        if credentials_path:
            worksheet = self._worksheet(worksheet_name)
            return worksheet.get(
                range_name or "A:ZZ",
                value_render_option="UNFORMATTED_VALUE" if unformatted else "FORMATTED_VALUE",
            )
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        try:
            params = {"tqx": "out:csv", "sheet": worksheet_name}
            if range_name:
                params["range"] = range_name
            response = requests.get(
                url,
                params=params,
                timeout=45,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ConnectionError(
                "No se pudo leer el Google Sheet como documento público. "
                "Si la hoja es privada, configure el archivo JSON de una cuenta de servicio "
                "y compártala con el correo de esa cuenta."
            ) from exc
        content_type = response.headers.get("Content-Type", "")
        raw_content = getattr(response, "content", b"")
        text = raw_content.decode("utf-8-sig") if raw_content else response.text
        if "text/html" in content_type.casefold() and "accounts.google.com" in text:
            raise PermissionError(
                "Google solicitó iniciar sesión. Comparta la hoja para lectura mediante enlace "
                "o configure Credenciales Google (JSON)."
            )
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise ValueError(f"La pestaña '{worksheet_name}' no devolvió datos.")
        if range_name and range_name.upper().startswith("A") and range_name.upper().endswith(":L"):
            return [row[:12] for row in rows]
        return rows

    def _records(self, worksheet_name: str) -> list[dict[str, Any]]:
        rows = self._rows(worksheet_name)
        if not rows:
            return []
        headers = [self._text(value) for value in rows[0]]
        result: list[dict[str, Any]] = []
        for values in rows[1:]:
            padded = list(values) + [""] * max(0, len(headers) - len(values))
            result.append({
                header: padded[index]
                for index, header in enumerate(headers)
                if header
            })
        return result

    @classmethod
    def parse_purchase_order_rows(
        cls,
        rows: list[list[Any]],
        *,
        start_row: int = 1,
    ) -> list[PurchaseOrderDraft]:
        blocks: list[tuple[str, list[tuple[int, list[Any]]]]] = []
        current_task = ""
        current_rows: list[tuple[int, list[Any]]] = []
        for row_number, raw in enumerate(rows, start=start_row):
            row = list(raw) + [""] * max(0, 12 - len(raw))
            marker = cls._task_marker(row[2])
            if marker:
                if current_task:
                    blocks.append((current_task, current_rows))
                current_task = marker
                current_rows = [(row_number, row)]
            elif current_task:
                current_rows.append((row_number, row))
        if current_task:
            blocks.append((current_task, current_rows))

        drafts: list[PurchaseOrderDraft] = []
        for task_number, block_rows in blocks:
            context = {"pedido": "S/N", "department": "", "requester": "", "detail": ""}
            raw_articles: list[dict[str, Any]] = []
            for row_number, row in block_rows:
                for key, index in (("pedido", 8), ("department", 9), ("requester", 10), ("detail", 11)):
                    value = str(row[index] or "").strip() if key in ("department", "requester") else cls._text(row[index])
                    if value:
                        context[key] = value
                code = cls._text(row[1])
                description = cls._text(row[2])
                if cls._task_marker(description) or not (code or description):
                    continue
                if code.casefold() in HEADER_WORDS or (not code and description.casefold() in HEADER_WORDS):
                    continue
                supplier = cls._text(row[4])
                existing_order = cls._text(row[6])
                if (
                    not code
                    or "crear codigo" in cls._plain(code)
                    or not cls._text(row[3])
                    or not supplier
                    or not cls._text(row[5])
                    or existing_order
                ):
                    continue
                try:
                    quantity = cls._decimal(row[3])
                    price = cls._decimal(row[5])
                    if not quantity.is_finite() or not price.is_finite() or quantity <= 0 or price < 0:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    continue
                raw_articles.append(
                    {
                        "row": row_number,
                        "code": code,
                        "description": description or code,
                        "quantity": quantity,
                        "supplier": supplier,
                        "price": price,
                    }
                )

            by_supplier: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
            for article in raw_articles:
                by_supplier.setdefault(article["supplier"].casefold(), []).append(article)
            if not by_supplier:
                continue

            for supplier, grouped in by_supplier.items():
                supplier = grouped[0]["supplier"]
                errors: list[str] = []
                articles: list[PurchaseOrderArticle] = []
                for field, label in (
                    (context["requester"], "solicitante"),
                    (context["department"], "departamento"),
                    (context["detail"], "detalle"),
                ):
                    if not field:
                        errors.append(f"Falta el campo {label}.")
                for item in grouped:
                    row_number = item["row"]
                    code = item["code"]
                    description = item["description"]
                    articles.append(
                        PurchaseOrderArticle(
                            source_supplier=item["supplier"],
                            code=code,
                            description=description,
                            quantity=item["quantity"],
                            unit_price=item["price"],
                            source_row=row_number,
                        )
                    )
                drafts.append(
                    PurchaseOrderDraft(
                        supplier_reference=supplier,
                        task_number=task_number,
                        supplier=supplier or "SIN PROVEEDOR",
                        requester=context["requester"],
                        pedido=context["pedido"] or "S/N",
                        department=context["department"],
                        detail=context["detail"],
                        articles=articles,
                        source_rows=[item["row"] for item in grouped],
                        validation_errors=list(dict.fromkeys(errors)),
                    )
                )
        return drafts

    def record_purchase_order(self, draft: PurchaseOrderDraft, order_number: str) -> None:
        for attempt in range(3):
            try:
                self._record_purchase_order_attempt(draft, order_number)
                return
            except (requests.ConnectionError, requests.Timeout, gspread.exceptions.APIError) as exc:
                if isinstance(exc, gspread.exceptions.APIError):
                    status = getattr(exc.response, 'status_code', None)
                    if status not in (429, 500, 502, 503, 504) or getattr(exc, 'sheets_retries_exhausted', False):
                        raise
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def _record_purchase_order_attempt(self, draft: PurchaseOrderDraft, order_number: str) -> None:
        if not re.fullmatch(r"\d{4,14}", order_number):
            raise ValueError("Número de OC no válido para Google Sheets.")
        source_rows = [article.source_row for article in draft.original_articles]
        if not source_rows or min(source_rows) < PURCHASE_ORDER_START_ROW or len(set(source_rows)) != len(source_rows):
            raise ValueError("Filas de origen de OC inválidas o duplicadas.")
        name = str(self.settings.get("google", "google_oc_sheet_name", "GENERAL")).strip() or "GENERAL"
        worksheet = self._worksheet(name, writable=True)
        rows = worksheet.get(f"A{PURCHASE_ORDER_START_ROW}:L{max(source_rows)}", value_render_option="UNFORMATTED_VALUE")
        task = ""
        tasks = {}
        for row_number, raw in enumerate(rows, PURCHASE_ORDER_START_ROW):
            row = list(raw) + [""] * max(0, 12 - len(raw))
            task = self._task_marker(row[2]) or task
            tasks[row_number] = (task, row)
        updates = []
        cells: list[str] = []
        origins = {a.source_row: source for source in draft.original_drafts for a in source.articles}
        before = self._batch_cells(worksheet, [f'G{row}' for row in source_rows])
        for article in draft.original_articles:
            source = origins[article.source_row]
            task, row = tasks.get(article.source_row, ("", [""] * 12))
            supplier = article.source_supplier or source.supplier_reference or source.supplier
            if (task != source.task_number or self._text(row[1]) != article.code
                    or (self._text(row[2]) or article.code) != article.description
                    or self._text(row[4]).casefold() != supplier.casefold()
                    or self._decimal(row[3]) != article.quantity or self._decimal(row[5]) != article.unit_price):
                raise ValueError(f"La fila {article.source_row} cambió; no se escribió la OC.")
            cell = f"G{article.source_row}"
            current = before[cell]
            existing = self._text(current[0][0]) if current and current[0] else ""
            if existing and existing != order_number:
                raise ValueError(f"{cell} ya contiene un valor o fórmula; no se sobrescribió.")
            if existing != order_number:
                updates.append({"range": cell, "values": [[order_number]]})
            cells.append(cell)
        if updates:
            worksheet.batch_update(updates, value_input_option="RAW")
        # gspread califica y modifica internamente los rangos de ``updates``.
        # Verificar con la copia A1 original evita GENERAL!GENERAL!G123.
        confirmed_cells = self._batch_cells(worksheet, cells)
        for cell in cells:
            values = confirmed_cells[cell]
            existing = self._text(values[0][0]) if values and values[0] else ""
            if not existing:
                raise requests.ConnectionError(f"Sincronización parcial: aún no se confirmó la OC en {cell}.")
            if existing != order_number:
                raise ValueError(f"Conflicto al confirmar {cell}: cambió el valor o apareció una fórmula; no se sobrescribió.")
        # Confirm the complete source range as well as individual cells. Never
        # report success when the two reads disagree about the persisted values.
        confirmed = worksheet.get(
            f"A{PURCHASE_ORDER_START_ROW}:L{max(source_rows)}",
            value_render_option="FORMULA",
        )
        for row_number in source_rows:
            offset = row_number - PURCHASE_ORDER_START_ROW
            row = confirmed[offset] if offset < len(confirmed) else []
            actual = self._text(row[6]) if len(row) > 6 else ""
            if actual != order_number:
                raise requests.ConnectionError(
                    f"GENERAL no confirma la OC {order_number} en G{row_number} "
                    "al releer el bloque. La OC sigue pendiente de sincronizar; no regenerar."
                )

    @staticmethod
    def _task_marker(value: Any) -> str:
        text = GoogleSheetsGateway._text(value)
        match = TASK_PATTERN.fullmatch(text) if text.isdigit() else TASK_PATTERN.search(text)
        return match.group(1) if match and (text.isdigit() or "tarea" in text.casefold()) else ""

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return " ".join(str(value).strip().split())

    @staticmethod
    def _plain(value: Any) -> str:
        import unicodedata

        return "".join(
            char for char in unicodedata.normalize("NFKD", str(value).casefold())
            if not unicodedata.combining(char)
        )

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        text = str(value or "").strip().replace("$", "").replace(" ", "")
        if not text:
            raise ValueError("valor vacío")
        if "," in text and "." in text:
            if text.rfind(".") > text.rfind(","):
                text = text.replace(",", "")
            else:
                text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        return Decimal(text)
