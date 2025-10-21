"""Generación y envío de reportes para la reasignación de Servicios."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Dict, List

from .email_sender import send_email_custom

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """
<p>Se adjunta el resumen de tareas procesadas por el módulo de Servicios.</p>
{% if filas_ok %}
<h3>Tareas reasignadas correctamente</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <thead>
    <tr>
      <th>Fecha</th>
      <th>Número de tarea</th>
      <th>Taller</th>
      <th>Asunto</th>
    </tr>
  </thead>
  <tbody>
  {% for fila in filas_ok %}
    <tr>
      <td>{{ fila.fecha }}</td>
      <td>{{ fila.task_number }}</td>
      <td>{{ fila.taller }}</td>
      <td>{{ fila.asunto }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
{% if filas_fail %}
<h3>Tareas con inconvenientes</h3>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <thead>
    <tr>
      <th>Fecha</th>
      <th>Número de tarea</th>
      <th>Taller</th>
      <th>Asunto</th>
    </tr>
  </thead>
  <tbody>
  {% for fila in filas_fail %}
    <tr>
      <td>{{ fila.fecha }}</td>
      <td>{{ fila.task_number }}</td>
      <td>{{ fila.taller }}</td>
      <td>{{ fila.asunto }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}
"""


def _formatear_filas(filas: Iterable[Dict[str, object]]) -> List[Dict[str, str]]:
    resultado: List[Dict[str, str]] = []
    for fila in filas:
        if not fila:
            continue
        fecha = fila.get("fecha")
        if isinstance(fecha, datetime):
            fecha_str = fecha.strftime("%Y-%m-%d %H:%M")
        else:
            fecha_str = str(fecha or "")
        asunto = str(fila.get("asunto", ""))
        error = fila.get("error")
        if error:
            asunto = f"{asunto} (Error: {error})" if asunto else f"Error: {error}"
        resultado.append(
            {
                "fecha": fecha_str,
                "task_number": str(fila.get("task_number") or "N/D"),
                "taller": str(fila.get("taller") or "N/D"),
                "asunto": asunto,
            }
        )
    return resultado


def enviar_reporte_servicios(
    email_session: Dict[str, str] | None,
    destinatario: str | None,
    exitosos: Iterable[Dict[str, object]] | None,
    fallidos: Iterable[Dict[str, object]] | None,
) -> bool:
    """Envía un resumen de las tareas reasignadas y las que fallaron."""

    if not email_session or not destinatario:
        logger.debug("No se envía reporte: faltan credenciales o destinatario")
        return False

    filas_ok = _formatear_filas(exitosos or [])
    filas_fail = _formatear_filas(fallidos or [])

    if not filas_ok and not filas_fail:
        logger.debug("No se envía reporte: no hay filas para reportar")
        return False

    contexto = {
        "email_to": destinatario,
        "filas_ok": filas_ok,
        "filas_fail": filas_fail,
    }

    try:
        send_email_custom(
            email_session,
            "Reporte de tareas reasignadas",
            _HTML_TEMPLATE,
            contexto,
            cc_key="EMAIL_CC_REASIGNACION",
        )
        logger.info("Reporte de reasignación enviado a %s", destinatario)
        return True
    except Exception as exc:  # pragma: no cover - la entrega puede fallar por red
        logger.warning("No se pudo enviar el reporte de reasignación: %s", exc)
        return False


__all__ = ["enviar_reporte_servicios"]
