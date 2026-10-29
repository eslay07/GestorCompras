from __future__ import annotations

from compras_tn.application.workflows import ACTION_REGISTRY, expand_workflow
from compras_tn.domain.models import FlowStep, WorkflowDefinition


def repair_workflow(workflow: WorkflowDefinition) -> tuple[WorkflowDefinition, list[str]]:
    """Propose a copy; never save or execute business actions here.

    Step numbers in instructions refer to the original, expanded flow.
    Only infer transitions with an unambiguous existing commit action.
    """
    flow = expand_workflow(workflow)
    result: list[FlowStep] = []
    advice: list[str] = []
    observation = False
    confirmation = False
    pause = False
    previous_number = 0
    last_insert_at = -1
    panel = ""

    def insert(action: str, after: int) -> None:
        nonlocal last_insert_at
        if last_insert_at == after and result:
            anchor = ACTION_REGISTRY[result[-1].action_id].label
            advice.append(f"Después de «{anchor}» propuesto tras el paso {after}, agregue «{ACTION_REGISTRY[action].label}».")
        else:
            advice.append(f"Después del paso {after}, agregue «{ACTION_REGISTRY[action].label}».")
        result.append(FlowStep(action_id=action))
        last_insert_at = after

    for number, original in enumerate(flow.steps, 1):
        step = original.model_copy(deep=True)
        action = step.action_id
        if observation and action not in {"ingresar_observacion", "aceptar_observacion", "definir_variable", "capturar_dato", "esperar_elemento"}:
            insert("aceptar_observacion", previous_number)
            observation = False
            confirmation = True
        if confirmation and action not in {"cerrar_mensaje_ok", "cerrar_mensaje_fin_tarea", "definir_variable", "capturar_dato", "esperar_elemento"}:
            insert("cerrar_mensaje_ok", previous_number)
            confirmation = False
        if pause and action == "aceptar_observacion":
            step = FlowStep(action_id="aceptar_pausa")
            action = step.action_id
            advice.append(f"En el paso {number}, reemplace «Aceptar observación» por «Confirmar pausa», después de «Seleccionar motivo».")
        result.append(step)
        if action == "ingresar_observacion":
            observation = True
        elif action == "aceptar_observacion":
            observation = False
            confirmation = True
        elif action in {"guardar_seguimiento", "subir_archivo", "guardar_reasignacion", "aceptar_pausa"}:
            confirmation = True
            if action == "aceptar_pausa":
                pause = False
        elif action in {"cerrar_mensaje_ok", "cerrar_mensaje_fin_tarea"}:
            confirmation = False
        elif action == "motivo_pausa":
            pause = True
        if action in {"abrir_subida_archivo", "abrir_seguimiento", "abrir_reasignar", "pausar_tarea", "reanudar_tarea", "ver_seguimiento", "ver_archivos"}:
            panel = action
        elif action in {"cerrar_panel", "cerrar_mensaje_ok", "cerrar_mensaje_fin_tarea"}:
            panel = ""
        previous_number = number
    # Do not invent commits for unfinished forms at the end of a draft.
    if observation:
        advice.append(f"Después del paso {previous_number}, complete «Aceptar observación» y «Cerrar mensaje OK» cuando termine de editar la observación.")
    if confirmation:
        insert("cerrar_mensaje_ok", previous_number)
    elif panel and not observation:
        if panel in {"ver_seguimiento", "ver_archivos"}:
            insert("cerrar_panel", previous_number)
        else:
            advice.append("El flujo termina con un formulario abierto. Complete su guardado y confirmación, o agregue «Cerrar ventana sin guardar» si desea cancelarlo. No se añadirá un guardado automáticamente.")
    return flow.model_copy(update={"steps": result}), advice
