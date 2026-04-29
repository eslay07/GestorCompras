"""Enriquecimiento de contexto de tareas a partir de PDFs de OC."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_RE_OC = re.compile(r"(?:orden\s*(?:de\s*compra)?|oc)\D{0,10}(\d{4,})", re.IGNORECASE)
_RE_RUC = re.compile(r"\b(?:RUC)\D{0,10}(\d{11})\b", re.IGNORECASE)
_RE_PROV = re.compile(r"(?:proveedor|raz[oó]n\s+social)\s*[:\-]?\s*(.+)", re.IGNORECASE)
_RE_TASK = re.compile(r"(?:tarea|n[.°ºo]*\s*tarea)\D{0,8}(\d{4,})", re.IGNORECASE)


def _read_pdf_text(pdf_path: Path, max_pages: int = 2) -> str:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return ""
    try:
        chunks: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:max_pages]:
                txt = page.extract_text() or ""
                if txt:
                    chunks.append(txt)
        return "\n".join(chunks)
    except Exception:
        return ""


def enrich_task_from_base(task_number: str, carpeta_base: str) -> dict[str, Any]:
    """Busca PDFs ligados a la tarea y retorna metadata base para el flujo."""
    base = Path((carpeta_base or "").strip())
    task = str(task_number or "").strip()
    if not task or not base.exists():
        return {}

    result: dict[str, Any] = {"task_number": task}
    candidates = sorted(base.rglob("*.pdf"))
    linked: list[Path] = []
    for pdf in candidates:
        if task in pdf.name:
            linked.append(pdf)
            continue
        text = _read_pdf_text(pdf, max_pages=1)
        if text and _RE_TASK.search(text) and _RE_TASK.search(text).group(1) == task:
            linked.append(pdf)

    if not linked:
        return result

    result["pdf_paths"] = [str(p.resolve()) for p in linked]
    main_pdf = linked[0]
    text = _read_pdf_text(main_pdf, max_pages=2)
    if not text:
        return result

    oc = _RE_OC.search(text)
    ruc = _RE_RUC.search(text)
    prov = _RE_PROV.search(text)
    if oc:
        result["orden_compra"] = oc.group(1).strip()
        result["oc"] = oc.group(1).strip()
    if ruc:
        result["ruc"] = ruc.group(1).strip()
    if prov:
        result["proveedor"] = prov.group(1).strip()
    return result

