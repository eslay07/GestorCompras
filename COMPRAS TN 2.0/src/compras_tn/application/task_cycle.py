"""Evidence-based, advisory checks for the purchasing task lifecycle."""
from __future__ import annotations

import re
import unicodedata

STAGES = {
    1: 'Recibir tareas (manual)',
    2: 'Solicitar cotizaciones (manual)',
    3: 'Organizar cotizaciones y crear carpetas',
    4: 'Cargar órdenes de compra',
    5: 'Subir cotizaciones y actualizar seguimiento en Telcos',
    6: 'Descargar órdenes de compra',
    7: 'Enviar órdenes a firmar',
    8: 'Solicitar despacho por correo',
    9: 'Actualizar Telcos para despacho',
    10: 'Reasignar tareas completas',
}
WARNING_PREFIX = 'ADVERTENCIA DE PROCESO:'


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value).casefold())
                   if not unicodedata.combining(c))


def workflow_stage(name):
    name = ' '.join(plain(name).split())
    if 'cotizacion' in name and ('seguimiento' in name or 'actualizar' in name):
        return 5
    if 'firma' in name and 'orden' in name:
        return 7
    if 'despacho' in name and ('cargar' in name or 'orden' in name):
        return 9
    return 0


def request_stage(request):
    if request.kind == 'actualizar_tareas':
        return int(request.options.get('cycle_stage', workflow_stage(request.options.get('workflow', ''))))
    return {'organizar_cotizaciones': 3, 'precarga_oc_bienes': 4,
            'descarga_normal': 6, 'descarga_abastecimiento': 6,
            'escaneo_descargas': 6, 'correos_masivos': 8, 'reasignacion': 10}.get(request.kind, 0)


def targets(raw):
    """Return explicit task/order associations; never infer a task from an OC."""
    payload = raw.get('payload') or {}
    if raw.get('sources'):
        return set().union(*(targets(source) for source in raw['sources']))
    if raw.get('task_number') and 'payload' in raw:
        # A TaskRecord represents one task. Download metadata may still list
        # every task sharing a PDF; it must not multiply this task's OC list.
        tasks = [raw['task_number']]
    else:
        tasks = raw.get('task_numbers') or payload.get('task_numbers') or [raw.get('task_number') or payload.get('task_number') or '']
    if isinstance(tasks, str):
        tasks = tasks.split(',')
    orders = payload.get('orders') if 'orders' in payload else raw.get('orders')
    if orders is not None:
        numbers = [str(row.get('order_number') or '').strip() for row in orders]
    else:
        numbers = payload.get('order_numbers') or raw.get('order_numbers') or re.split(r'[,;]', str(raw.get('order_number') or raw.get('numero') or payload.get('order_number') or ''))
    if isinstance(numbers, str):
        numbers = numbers.split(',')
    return {(str(task or '').strip(), str(number or '').strip())
            for task in tasks for number in (numbers or ['']) if task or number}


def success_targets(request, item):
    destinations = item.payload.get('task_destinations')
    if request.kind in ('descarga_normal', 'descarga_abastecimiento', 'escaneo_descargas') and destinations:
        number = str(item.payload.get('order_number') or item.key)
        return {(str(row['task_number']), number) for row in destinations
                if row.get('task_number') and row.get('preparation_status') == 'succeeded'}
    found = targets(item.payload)
    # Workflow context can contain task data, but audited input identifies all OCs.
    matched = [raw for raw in request.items if str(raw.get('task_number') or '') == item.key
               or str(raw.get('order_number') or raw.get('numero') or '') == item.key
               or (request.kind == 'precarga_oc_bienes' and item.key == (f"{raw.get('task_number')} · {raw.get('supplier')}" + (f" · Parte {raw.get('split_part')}/{raw.get('split_total')}" if raw.get("split_total", 0) > 1 else "")))]
    requested = set().union(*(targets(raw) for raw in matched)) if matched else set()
    if request.kind == 'precarga_oc_bienes' and item.payload.get('order_number'):
        # The generated OC is absent from the input drafts. Carry it to every
        # explicitly grouped task, including older results with only one task.
        number = str(item.payload['order_number']).strip()
        return found | {(task, number) for task, _ in requested if task}
    if request.kind in ('actualizar_tareas', 'reasignacion'):
        return requested or found
    if found:
        # Downloads/dispatch sometimes expose task IDs only in metadata.
        metadata = item.payload.get('metadata') or {}
        extra = targets({**metadata, 'order_number': item.payload.get('order_number') or item.key})
        return found | {pair for pair in extra if pair[0]}
    return requested


class TaskCycle:
    def __init__(self, jobs):
        self.jobs = jobs

    def evidence(self):
        evidence = set()
        for request, item in self.jobs.cycle_successes():
            stage = request_stage(request)
            if stage:
                evidence.update((task, order, stage) for task, order in success_targets(request, item))
        return evidence

    def warnings(self, request):
        stage = request_stage(request)
        if not 4 <= stage <= 10:
            return ''
        evidence = self.evidence()
        selected = set().union(*(targets(raw) for raw in request.items)) if request.items else set()
        lines = []
        for task, order in sorted(selected):
            # Resolve an order-only input from prior task/order associations when possible.
            linked = {t for t, o, _ in evidence if t and o == order} if not task and order else set()
            identities = linked or {task}
            for identity in sorted(identities):
                missing = []
                for previous in range(4, stage):
                    if previous == 3:
                        done = any(s == previous and ((identity and t == identity) or (order and o == order)) for t, o, s in evidence)
                    elif order:
                        done = any(s == previous and o == order and (not identity or not t or t == identity) for t, o, s in evidence)
                    else:
                        # A task-wide run has no OC scope: do not assume that one prior OC covers all.
                        known = {o for t, o, _ in evidence if t == identity and o}
                        done = bool(known) and all(any(s == previous and o == n and (not t or t == identity) for t, o, s in evidence) for n in known)
                    if not done:
                        missing.append(f'{previous}. {STAGES[previous]}')
                label = (f'Tarea {identity}' if identity else 'Tarea sin identificar') + (f' · OC {order}' if order else '')
                if missing:
                    lines.append(label + ': sin ejecución correcta registrada de ' + '; '.join(missing) + '.')
        if not lines:
            return ''
        return (WARNING_PREFIX + f' Paso {stage}: {STAGES[stage]}.\n' + '\n'.join(lines)
                + '\nFaltan registros de pasos anteriores del sistema. ¿Desea continuar de todas formas?')


class CycleDeclined(Exception):
    """The user declined to run an operation with missing system prerequisites."""
