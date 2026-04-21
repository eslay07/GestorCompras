"""Envío de reporte por correo al finalizar un flujo de Actualizar Tareas."""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

SMTP_SERVER = "smtp.telconet.ec"
SMTP_PORT = 587
TZ = ZoneInfo("America/Guayaquil")


def _ensure_email(address: str) -> str:
    if "@" not in address:
        return f"{address}@telconet.ec"
    return address


def _build_html(
    flujo_nombre: str,
    resultados: List[Dict[str, Any]],
    headless: bool,
) -> str:
    ahora = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    n_ok = sum(1 for r in resultados if r.get("status") == "ok")
    n_err = len(resultados) - n_ok

    rows = ""
    for r in resultados:
        status = r.get("status", "?")
        task = r.get("task_number", "?")
        msg = r.get("mensaje", r.get("error", ""))
        color = "#2e7d32" if status == "ok" else "#c62828"
        campos = r.get("campos") or {}
        campos_str = ", ".join(f"{k}={v}" for k, v in campos.items() if v) if campos else ""
        rows += (
            f"<tr>"
            f"<td style='padding:4px 8px;border:1px solid #ddd'>{task}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd;color:{color};font-weight:bold'>{status.upper()}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd'>{msg}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd'>{campos_str}</td>"
            f"</tr>"
        )

    modo = "Oculto (headless)" if headless else "Visible"
    html = f"""\
<html><body style="font-family:Segoe UI,Arial,sans-serif;font-size:13px">
<h2 style="color:#1565c0">Reporte Actualizar Tareas</h2>
<p><b>Flujo:</b> {flujo_nombre}<br>
<b>Fecha:</b> {ahora}<br>
<b>Modo:</b> {modo}<br>
<b>Resultado:</b> {n_ok} OK / {n_err} errores de {len(resultados)} total</p>
<table style="border-collapse:collapse;width:100%">
<tr style="background:#e3f2fd">
<th style="padding:6px 8px;border:1px solid #ddd;text-align:left">Tarea</th>
<th style="padding:6px 8px;border:1px solid #ddd;text-align:left">Estado</th>
<th style="padding:6px 8px;border:1px solid #ddd;text-align:left">Mensaje</th>
<th style="padding:6px 8px;border:1px solid #ddd;text-align:left">Campos</th>
</tr>
{rows}
</table>
<p style="color:#888;font-size:11px;margin-top:16px">Generado por GestorCompras - Actualizar Tareas</p>
</body></html>"""
    return html


def _build_plain(
    flujo_nombre: str,
    resultados: List[Dict[str, Any]],
    headless: bool,
) -> str:
    ahora = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    n_ok = sum(1 for r in resultados if r.get("status") == "ok")
    n_err = len(resultados) - n_ok
    modo = "Oculto" if headless else "Visible"

    lines = [
        f"Reporte Actualizar Tareas",
        f"Flujo: {flujo_nombre}",
        f"Fecha: {ahora}",
        f"Modo: {modo}",
        f"Resultado: {n_ok} OK / {n_err} errores de {len(resultados)} total",
        "",
    ]
    for r in resultados:
        status = r.get("status", "?").upper()
        task = r.get("task_number", "?")
        msg = r.get("mensaje", r.get("error", ""))
        lines.append(f"  {task}  {status}  {msg}")
    return "\n".join(lines)


def send_actua_report(
    email_session: Dict[str, str],
    flujo_nombre: str,
    resultados: List[Dict[str, Any]],
    headless: bool = True,
) -> bool:
    """Envía un correo informe al propio usuario. Devuelve True si se envió."""
    address = email_session.get("address", "")
    password = email_session.get("password", "")
    if not address or not password:
        logger.warning("No se puede enviar reporte: credenciales incompletas.")
        return False

    dest = _ensure_email(address)
    n_ok = sum(1 for r in resultados if r.get("status") == "ok")
    subject = f"Reporte Actualizar Tareas - {flujo_nombre} ({n_ok}/{len(resultados)} OK)"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = dest
    msg["To"] = dest

    plain = _build_plain(flujo_nombre, resultados, headless)
    html = _build_html(flujo_nombre, resultados, headless)
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(address, password)
            server.send_message(msg)
        logger.info("Reporte enviado a %s: %s", dest, subject)
        return True
    except Exception:
        logger.exception("Error al enviar reporte Actualizar Tareas a %s", dest)
        return False


__all__ = ["send_actua_report"]
