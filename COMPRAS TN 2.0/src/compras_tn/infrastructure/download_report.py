from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from typing import Any

from compras_tn.domain.models import ItemStatus, OperationRequest, OperationResult


@dataclass(frozen=True, slots=True)
class DownloadMailReport:
    subject: str
    html: str
    text: str


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _clip(value: Any, width: int) -> str:
    text = str(value).replace("\n", " ").strip()
    return (text[: width - 1] + "…") if len(text) > width else text


def text_table(
    rows: Sequence[tuple[str, ...]], headers: tuple[str, ...] | None = None
) -> str:
    if not rows:
        return "─ Sin datos ─"
    headers = headers or ("Orden", "Tarea", "Proveedor", "Ubicación")
    maximums = [16, 18, 32, 60]
    clipped = [
        tuple(_clip(row[index], maximums[index] if index < len(maximums) else 30)
              for index in range(len(headers)))
        for row in ([headers] + list(rows))
    ]
    widths = [max(len(row[index]) for row in clipped) for index in range(len(headers))]
    top = "┌" + "┬".join("─" * (width + 2) for width in widths) + "┐"
    middle = "├" + "┼".join("─" * (width + 2) for width in widths) + "┤"
    bottom = "└" + "┴".join("─" * (width + 2) for width in widths) + "┘"

    def formatted(row: tuple[str, ...]) -> str:
        return "│ " + " │ ".join(
            row[index].ljust(widths[index]) for index in range(len(headers))
        ) + " │"

    return "\n".join([top, formatted(clipped[0]), middle,
                       *(formatted(row) for row in clipped[1:]), bottom])


def html_table(
    rows: Sequence[tuple[str, ...]], headers: tuple[str, ...] | None = None
) -> str:
    if not rows:
        return "<p style='font-family:Segoe UI, Arial, sans-serif;font-size:13px;'>– Sin datos –</p>"
    headers = headers or ("Orden", "Tarea", "Proveedor", "Ubicación")
    table_style = (
        "border-collapse:collapse;border:1px solid #d0d7de;width:100%;"
        "font-family:Segoe UI, Arial, sans-serif;font-size:13px;table-layout:fixed;"
        "word-wrap:break-word;line-height:1.35;"
    )
    th_style = (
        "text-align:left;padding:8px 10px;border:1px solid #d0d7de;"
        "background:#f6f8fa;font-weight:600;white-space:nowrap;"
    )
    td_style = (
        "padding:6px 10px;border:1px solid #d0d7de;vertical-align:top;"
        "word-break:break-word;"
    )
    widths = ["12ch", "16ch", "22ch", "auto"]
    colgroup = "<colgroup>" + "".join(
        f"<col style='width:{widths[index] if index < len(widths) else 'auto'}'>"
        for index in range(len(headers))
    ) + "</colgroup>"
    header = "".join(f"<th style='{th_style}'>{escape(str(value))}</th>" for value in headers)
    body = "".join(
        "<tr style='background:{};'>{}</tr>".format(
            "#ffffff" if row_index % 2 == 0 else "#fafbfc",
            "".join(
                f"<td style='{td_style}'>{escape(str(row[column]))}</td>"
                for column in range(len(headers))
            ),
        )
        for row_index, row in enumerate(rows)
    )
    return (
        f"<table style='{table_style}'>{colgroup}<thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _merge_order_data(
    target: dict[str, Any], source: dict[str, Any], *, prefer_incoming: bool = True
) -> None:
    """Combina duplicados sin permitir que un valor vacío borre datos útiles."""
    for key, value in source.items():
        if key in {"task_numbers", "pdf_paths", "external_ids"}:
            current = target.get(key) or []
            current = current if isinstance(current, (list, tuple, set)) else [current]
            incoming = value if isinstance(value, (list, tuple, set)) else [value]
            target[key] = _unique(
                [str(item).strip() for item in (*current, *incoming) if str(item).strip()]
            )
            continue
        if key == "task_destinations":
            current_destinations = [
                dict(item)
                for item in (target.get(key) or [])
                if isinstance(item, dict)
            ]
            seen = {
                (
                    str(item.get("task_number") or ""),
                    str(item.get("pdf_path") or ""),
                    str(item.get("month") or ""),
                )
                for item in current_destinations
            }
            for item in value or []:
                if not isinstance(item, dict):
                    continue
                identity = (
                    str(item.get("task_number") or ""),
                    str(item.get("pdf_path") or ""),
                    str(item.get("month") or ""),
                )
                if identity not in seen:
                    seen.add(identity)
                    current_destinations.append(dict(item))
            target[key] = current_destinations
            continue
        if value not in (None, "", [], {}) and (
            prefer_incoming or target.get(key) in (None, "", [], {})
        ):
            target[key] = value


def render_download_report(
    request: OperationRequest, result: OperationResult
) -> DownloadMailReport | None:
    supply = request.kind == "descarga_abastecimiento"
    category = str(request.options.get("category") or ("Abastecimiento" if supply else "")).strip()
    source: dict[str, dict[str, Any]] = {}
    for request_item in request.items:
        number = str(
            request_item.get("order_number") or request_item.get("numero") or ""
        ).strip()
        if not number:
            continue
        _merge_order_data(
            source.setdefault(number, {}),
            dict(request_item),
            prefer_incoming=False,
        )
    successful = _unique([
        item.key for item in result.items if item.status == ItemStatus.SUCCEEDED
    ])
    not_approved = _unique([
        item.key for item in result.items
        if item.error_code == "order_not_approved"
        or (item.status == ItemStatus.SKIPPED and "aprob" in item.message.casefold())
    ])
    missing = _unique([
        item.key for item in result.items
        if item.status in {ItemStatus.FAILED, ItemStatus.NOT_FOUND}
        and item.key not in not_approved
    ])
    if not successful and not missing and not not_approved:
        return None

    by_number = {number: dict(data) for number, data in source.items()}
    result_seen: set[str] = set()
    for result_item in result.items:
        _merge_order_data(
            by_number.setdefault(result_item.key, {}),
            dict(result_item.payload),
            prefer_incoming=result_item.key not in result_seen,
        )
        result_seen.add(result_item.key)
    headers = (
        ("Orden", "Proveedor", "Categoría", "Ubicación")
        if supply else ("Orden", "Tarea", "Proveedor", "Ubicación")
    )

    def row(number: str) -> tuple[str, ...]:
        data = by_number.get(number, source.get(number, {}))
        supplier = str(data.get("supplier") or data.get("proveedor") or "-")
        destinations = [
            item
            for item in data.get("task_destinations", [])
            if isinstance(item, dict) and item.get("preparation_status") == "succeeded"
        ]
        locations = _unique(
            [str(item.get("pdf_path") or "").strip() for item in destinations]
            + [str(value).strip() for value in (data.get("pdf_paths") or [])]
        )
        location = " ; ".join(locations) or str(data.get("pdf_path") or data.get("ruta") or "-")
        if supply:
            return (number, supplier, str(data.get("category") or data.get("categoria") or category or "-"), location)
        task_numbers = _unique(
            [str(value).strip() for value in (data.get("task_numbers") or [])]
            + [str(data.get("task_number") or data.get("tarea") or "").strip()]
        )
        month_groups: dict[str, list[str]] = {}
        for destination in destinations:
            task = str(destination.get("task_number") or "").strip()
            if not task:
                continue
            month = str(destination.get("month") or "").strip()
            month_groups.setdefault(month, [])
            if task not in month_groups[month]:
                month_groups[month].append(task)
        represented = {
            task for tasks in month_groups.values() for task in tasks
        }
        unplaced = [task for task in task_numbers if task not in represented]
        if len(month_groups) == 1:
            month, tasks = next(iter(month_groups.items()))
            task_display = " - ".join([*tasks, month] if month else tasks)
            if unplaced:
                task_display += " / " + " - ".join(unplaced)
        elif month_groups:
            task_display = " / ".join(
                " - ".join([*tasks, month] if month else tasks)
                for month, tasks in month_groups.items()
            )
            if unplaced:
                task_display += " / " + " - ".join(unplaced)
        else:
            task_display = " - ".join(task_numbers)
        return (number, task_display or "-", supplier, location)

    def grouped_rows(numbers):
        if supply:
            return [row(number) for number in numbers]

        def numeric(value):
            import re
            value = str(value).strip()
            return (0, int(value)) if re.fullmatch(r'\d+', value) else (1, value.casefold())

        def sort_key(number):
            data = by_number.get(number, {})
            raw_tasks = data.get('task_numbers') or []
            if isinstance(raw_tasks, str):
                raw_tasks = raw_tasks.split(',')
            tasks = _unique([str(value).strip() for value in raw_tasks]
                + [str(data.get('task_number') or data.get('tarea') or '').strip()]
                + [str(item.get('task_number') or '').strip()
                   for item in data.get('task_destinations', []) if isinstance(item, dict)])
            # One OC remains one row. Place shared OCs with their lowest task;
            # keep the original combined task/month and location cells intact.
            return (min((numeric(task) for task in tasks), default=(2, '')), numeric(number))

        return [row(number) for number in sorted(_unique(list(numbers)), key=sort_key)]

    ok_rows = grouped_rows(successful)
    missing_rows = grouped_rows(missing)
    subject = "Reporte de órdenes descargadas" + (f" - {category}" if category else "")
    text = f"Categoría: {category}\n\n" if category else ""
    text += "Órdenes descargadas correctamente:\n"
    if ok_rows:
        text += text_table(ok_rows, headers) + "\n"
    html = f"<p>Categoría: {escape(category)}</p>" if category else ""
    html += "<h3>Órdenes descargadas correctamente:</h3>" + html_table(ok_rows, headers)
    if missing_rows:
        heading = "No se ubicaron archivos locales para las siguientes OC:"
        text += f"\n{heading}\n{text_table(missing_rows, headers)}\n"
        html += f"<h3>{heading}</h3>" + html_table(missing_rows, headers)
    if not_approved:
        na_headers = ("Orden", "Proveedor")
        na_rows = [
            (number, str(by_number.get(number, {}).get("supplier")
                         or by_number.get(number, {}).get("proveedor") or "-"))
            for number in not_approved
        ]
        if not supply:
            na_headers = headers
            na_rows = grouped_rows(not_approved)
        heading = "Órdenes de compra NO APROBADAS (descarga no permitida):"
        text += f"\n{heading}\n{text_table(na_rows, na_headers)}\n"
        html += (
            '<h3 style="color:#c0392b;">⚠ Órdenes de compra NO APROBADAS '
            "(descarga no permitida):</h3>" + html_table(na_rows, na_headers)
        )
    return DownloadMailReport(subject=subject, html=html, text=text)
