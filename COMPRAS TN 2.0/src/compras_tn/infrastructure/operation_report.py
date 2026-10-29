from decimal import Decimal
from html import escape
from typing import Any

from compras_tn.domain.models import ItemStatus, OperationRequest, OperationResult
from compras_tn.infrastructure.download_report import DownloadMailReport, html_table, text_table
from compras_tn.security import sanitize_data


def render_operation_report(request: OperationRequest, result: OperationResult, title: str) -> DownloadMailReport:
    if request.kind == "actualizar_tareas" and request.options.get("workflow"):
        title = f"{title} · Flujo: {request.options['workflow']}"
    oc = request.kind == "precarga_oc_bienes"
    headers = (("Tareas", "OC", "Proveedor / RUC", "Departamento / Solicitante", "Artículos / Subtotal", "Sincronización", "Detalle")
               if oc else ("Elemento / Tarea", "Origen", "OC", "Destino", "Estado", "Detalle"))
    sections: dict[str, list[tuple[str, ...]]] = {"Correctos": [], "Errores": [], "Omitidos": []}
    for item in result.items:
        row: tuple[str, ...]
        data: dict[str, Any] = {}
        for source in request.items:
            same_supplier = all(not item.payload.get(key) or source.get(key) == item.payload[key]
                                for key in ("ruc", "supplier")) if oc else True
            if same_supplier and str(source.get("task_number", "")) == str(item.payload.get("task_number") or item.key):
                data = dict(source)
                data.update(source.get("payload") or {})
                if source.get("sources"):
                    data["task_numbers"] = list(dict.fromkeys(s["task_number"] for s in source["sources"]))
                if oc:
                    data["subtotal"] = f"{sum((Decimal(str(a['quantity'])) * Decimal(str(a['unit_price'])) for a in source.get('articles', [])), Decimal('0')):.2f}"
                break
        data.update(item.payload)
        data = sanitize_data(data)
        task_numbers = data.get("task_numbers") or [data.get("task_number") or item.key]
        orders = data.get("order_numbers") or [data.get("order_number") or "-"]
        detail = " · ".join(filter(None, [item.error_code, item.message]))
        uploads = data.get("document_upload_results") or data.get("contexto_ultimo_intento", {}).get("document_upload_results", [])
        if uploads:
            from pathlib import Path
            detail += " · " + "; ".join(f"{Path(u['path']).name}: {u['status']}" for u in uploads)
        if oc:
            articles = data.get("articles", "-")
            count = len(articles) if isinstance(articles, list) else articles
            sync = ("Verificada" if data.get("sheet_written") else "Pendiente") if data.get("order_number") else "Sin OC confirmada"
            row = (", ".join(task_numbers), ", ".join(orders),
                   f"{data.get('supplier', '-')} / {data.get('ruc', '-')}",
                   f"{data.get('department', '-')} / {data.get('requester', '-')}",
                   f"{count} / {data.get('subtotal', '-')}", sync, detail)
        else:
            origins = data.get("origins") or [data.get("origin", "-")]
            origin = " / ".join("Carga de OC automática" if o == "carga_oc_automatica" else o for o in origins)
            row = (str(data.get("task_number") or item.key), origin,
                   ", ".join(orders), f"{data.get('department') or request.options.get('department', '-')} / {data.get('employee') or request.options.get('employee', '-')}",
                   item.status.value, detail)
        section = "Correctos" if item.status == ItemStatus.SUCCEEDED else "Omitidos" if item.status == ItemStatus.SKIPPED else "Errores"
        sections[section].append(row)
    html = f"<h2>{escape(title)}</h2><p>Estado: {escape(result.status.value)}</p><p>{escape(result.message)}</p>"
    text = f"{title}\nEstado: {result.status.value}\n{result.message}\n"
    for heading, rows in sections.items():
        html += f"<h3>{heading} ({len(rows)})</h3>" + html_table(rows, headers)
        text += f"\n{heading} ({len(rows)})\n" + text_table(rows, headers) + "\n"
    return DownloadMailReport(f"{title} · {result.status.value}", html, text)
