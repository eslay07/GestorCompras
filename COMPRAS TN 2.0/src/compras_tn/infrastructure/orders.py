from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

import pdfplumber

from compras_tn.application.ports import SettingsRepository, SupplierRepository
from compras_tn.domain.models import OrderRecord

RUC_PATTERN = re.compile(r"(?:RUC|IDENTIFICACI[ÓO]N)\D{0,12}(\d{10,13})", re.IGNORECASE)
TASK_PATTERN = re.compile(r"(?:TAREA|N[.°ºO]*\s*TAREA)\D{0,10}(\d{4,14})", re.IGNORECASE)
SUPPLIER_PATTERN = re.compile(r"(?:PROVEEDOR|RAZ[ÓO]N SOCIAL)\s*[:=-]\s*([^\n]+)", re.IGNORECASE)
ORDER_PATTERN = re.compile(r'(?:O\s*/\s*C|ORDEN\s+DE\s+COMPRA)\s*(?:N[°ºO.]*)?\s*[:#=-]?\s*(\d{4,14})', re.IGNORECASE)


def extract_task_numbers(*values: str) -> list[str]:
    """Extrae tareas sin duplicados y conserva el orden en que aparecen."""
    result: list[str] = []
    for value in values:
        for number in TASK_PATTERN.findall(str(value or "")):
            clean = str(number).strip()
            if clean and clean not in result:
                result.append(clean)
    return result


class OrderFileService:
    def __init__(self, settings: SettingsRepository, suppliers: SupplierRepository):
        self.settings = settings
        self.suppliers = suppliers
        self._inventory_lock = threading.Lock()
        self._inventory_folder: Path | None = None
        self._inventory_at = 0.0
        self._inventory: list[Path] = []

    def resolve(self, order_number: str) -> OrderRecord:
        number = str(order_number or "").strip()
        if not number:
            raise ValueError("Número de OC vacío.")
        candidates = self._order_candidates(number, primary_only=True)
        if not candidates:
            folder_value = str(self.settings.get("files", "pdf_folder", "")).strip()
            folder = Path(folder_value) if folder_value else None
            if folder is None or not folder.is_dir():
                raise FileNotFoundError("La carpeta de PDF no está configurada o no existe.")
            raise FileNotFoundError(f"No se encontró el PDF de la OC {number}.")
        pdf = candidates[0]
        info = self.extract(pdf)
        task_numbers = list(info.get("task_numbers") or [])
        ruc = str(info.get("ruc") or "")
        supplier = self.suppliers.find_by_ruc(ruc) if ruc else None
        supplier_name = self.resolve_supplier(
            number,
            preferred_path=pdf,
            preferred_info=info,
        )
        return OrderRecord(
            order_number=number,
            task_number=task_numbers[0] if task_numbers else "",
            task_numbers=task_numbers,
            supplier=supplier_name,
            ruc=ruc,
            pdf_path=str(pdf),
            metadata={
                "emails": [
                    address
                    for address in (
                        supplier.email_primary if supplier else "",
                        supplier.email_secondary if supplier else "",
                    )
                    if address
                ]
            },
        )

    def _configured_roots(self, *, primary_only: bool = False) -> list[Path]:
        keys = [("files", "pdf_folder")]
        if not primary_only:
            keys.extend(
                [
                    ("downloads", "carpeta_analizar"),
                    ("downloads", "carpeta_destino_local"),
                ]
            )
        roots: list[Path] = []
        resolved_roots: set[Path] = set()
        for namespace, key in keys:
            value = str(self.settings.get(namespace, key, "")).strip()
            if not value:
                continue
            root = Path(value)
            if not root.is_dir():
                continue
            resolved = root.resolve()
            if resolved not in resolved_roots:
                resolved_roots.add(resolved)
                roots.append(root)
        return roots

    def _order_candidates(self, order_number: str, *, primary_only: bool = False) -> list[Path]:
        number_pattern = re.compile(
            rf"(?<!\d){re.escape(str(order_number).strip())}(?!\d)", re.IGNORECASE
        )
        candidates = [
            path
            for root in self._configured_roots(primary_only=primary_only)
            for path in self._pdf_inventory(root)
            if number_pattern.search(path.stem)
        ]
        unique = {str(path.resolve()).casefold(): path for path in candidates}
        return sorted(
            unique.values(),
            key=lambda path: (path.stat().st_mtime_ns, str(path.resolve()).casefold()),
            reverse=True,
        )

    def _registered_supplier_name(self, ruc: str) -> str:
        if not ruc:
            return ""
        supplier = self.suppliers.find_by_ruc(ruc)
        return supplier.name.strip() if supplier else ""

    @staticmethod
    def _supplier_from_filename(path: Path, order_number: str) -> str:
        match = re.match(
            rf"^\s*(?:OC\s*)?{re.escape(order_number)}\s+-\s+(.+?)(?:\s+\(\d+\))?$",
            path.stem,
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def resolve_supplier(
        self,
        order_number: str,
        *,
        preferred_path: Path | None = None,
        preferred_info: dict[str, Any] | None = None,
        fallback: str = "",
    ) -> str:
        """Resuelve el proveedor sin confundir la carpeta de tarea con su nombre."""
        number = str(order_number or "").strip()
        info = preferred_info
        if info is None and preferred_path is not None and preferred_path.is_file():
            try:
                info = self.extract(preferred_path)
            except ValueError:
                info = {}
        info = info or {}
        registered = self._registered_supplier_name(str(info.get("ruc") or ""))
        if registered:
            return registered
        extracted = str(info.get("supplier") or "").strip()
        if extracted:
            return extracted
        fallback = str(fallback or "").strip()
        if fallback:
            return fallback

        candidates = self._order_candidates(number)
        preferred_resolved = preferred_path.resolve() if preferred_path is not None else None
        for candidate in candidates:
            if preferred_resolved is not None and candidate.resolve() == preferred_resolved:
                continue
            try:
                candidate_info = self.extract(candidate)
            except ValueError:
                continue
            registered = self._registered_supplier_name(
                str(candidate_info.get("ruc") or "")
            )
            if registered:
                return registered
            extracted = str(candidate_info.get("supplier") or "").strip()
            if extracted:
                return extracted

        filename_candidates = ([preferred_path] if preferred_path is not None else []) + candidates
        for candidate in filename_candidates:
            supplier_name = self._supplier_from_filename(candidate, number)
            if supplier_name:
                return supplier_name
        return ""

    @staticmethod
    def extract(path: Path) -> dict[str, Any]:
        text_parts: list[str] = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
        except Exception as exc:
            raise ValueError(f"No se pudo leer el PDF '{path.name}': {exc}") from exc
        text = "\n".join(text_parts)
        ruc = RUC_PATTERN.search(text)
        task_numbers = extract_task_numbers(text)
        order = ORDER_PATTERN.search(text)
        supplier = SUPPLIER_PATTERN.search(text)
        if order is None and "ORDEN DE COMPRA" in text.upper():
            order = re.search(r"(?im)^No\.?\s+(\d{4,14})\s*$", text[:2000])
        if supplier is None and "PROVEEDOR CONDICIONES" in text.upper():
            supplier = re.search(r"(?im)^NOMBRE:\s*(.+?)(?:\s+FORMA\b|$)", text)
        return {
            "ruc": ruc.group(1) if ruc else "",
            "task_number": task_numbers[0] if task_numbers else "",
            "task_numbers": task_numbers,
            "order_number": order.group(1) if order else "",
            "supplier": supplier.group(1).strip() if supplier else "",
        }

    def find_context_file(self, payload: dict[str, Any], pattern: str = "") -> Path:
        for key in ("archivo", "ruta_archivo", "pdf_path"):
            value = str(payload.get(key) or "").strip()
            if value and Path(value).is_file():
                return Path(value).resolve()
        tokens = [
            str(payload.get(key) or "").strip()
            for key in ("order_number", "orden_compra", "oc", "task_number", "numero_tarea")
        ]
        tokens = [token for token in tokens if token]
        automation_value = str(
            self.settings.get("automation", "actua_tareas_carpeta_base", "")
        ).strip()
        files_value = str(self.settings.get("files", "pdf_folder", "")).strip()
        folder = Path(automation_value) if automation_value else None
        if folder is None or not folder.is_dir():
            folder = Path(files_value) if files_value else None
        if folder is None or not folder.is_dir():
            raise FileNotFoundError("No existe una carpeta base válida para buscar el archivo.")
        matches = [
            item for item in self._pdf_inventory(folder)
            if item.is_file() and (not pattern or item.match(pattern)) and tokens and
            any(re.search(rf'(?<!\d){re.escape(token)}(?!\d)', item.stem) for token in tokens)
        ]
        if not matches:
            raise FileNotFoundError("No se encontró un archivo relacionado con la tarea.")
        if len(matches) != 1:
            raise ValueError('Hay varios archivos relacionados; seleccione una ruta o alias explícito.')
        return matches[0]

    def _pdf_inventory(self, folder: Path) -> list[Path]:
        try:
            ttl = max(1, int(self.settings.get("files", "pdf_index_ttl_seconds", 10)))
        except (TypeError, ValueError):
            ttl = 10
        now = time.monotonic()
        with self._inventory_lock:
            if (
                self._inventory_folder == folder
                and now - self._inventory_at < ttl
            ):
                return list(self._inventory)
            self._inventory = [path for path in folder.rglob("*.pdf") if path.is_file()]
            self._inventory_folder = folder
            self._inventory_at = now
            return list(self._inventory)

    def invalidate_inventory(self) -> None:
        """Fuerza el siguiente resolve a volver a leer el disco."""
        with self._inventory_lock:
            self._inventory_folder = None
            self._inventory_at = 0.0
            self._inventory = []
