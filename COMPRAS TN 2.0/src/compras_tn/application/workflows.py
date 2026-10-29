from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from compras_tn.domain.models import FlowStep, TaskRecord, WorkflowDefinition

PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    default: str = ""
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    action_id: str
    label: str
    category: str
    description: str
    parameters: tuple[ParameterDefinition, ...] = ()
    requires_previous: tuple[str, ...] = ()


PAUSE_REASONS = (
    "1619 - SUSPENDE TRABAJO POR SOLICITUD DE CLIENTE",
    "1620 - ASIGNACIÓN DE CASO PRIORITARIO",
    "1621 - TRABAJOS O PERMISOS DE EMPRESAS EXTERNAS",
    "1622 - CONDICIONES CLIMÁTICAS",
    "1623 - DAÑO DE EQUIPAMIENTO",
    "1624 - DAÑO DE INFRAESTRUCTURA",
    "1625 - REQUERIMIENTO DE RECURSO EXTERNO",
    "1626 - SECTOR PELIGROSO/INTENTO DE ROBO",
    "1641 - SE SOLICITA COTIZACION AL PROVEEDOR",
    "1642 - EN ESPERA DE AUTORIZACION EN EL NAF",
    "1643 - POR TIEMPO DE ENTREGA DEL PRODUCTO NACIONAL/IMPORTADO",
    "1644 - POR MOTIVO DE PAGO: ANTICIPO / CONTADO",
    "1645 - POR MOTIVO DE ENVIO DE FACTURA ELECTRONICA",
    "1701 - GESTIÓN DE PERMISOS PARA ACCEDER A LAS INSTALACIONES DE CLIENTES",
    "1702 - GESTIÓN DE PERMISOS PARA INGRESAR A CENTROS COMERCIALES",
    "1703 - GESTIÓN DE ASIGNACIÓN DE FISCALIZADOR EN SECTORES REGENERADOS",
    "1704 - GESTIÓN DE ASIGNACIÓN DE CUSTODIOS EN SECTORES PELIGROSOS",
    "1735 - EN ESPERA DE RESPUESTA DEL CLIENTE",
    "1736 - CLIENTE NO CONTACTADO",
    "1737 - CLIENTE SOLICITA ATENCION DIFERIDA",
    "1738 - GESTION POR PERMISOS DEL CLIENTE",
    "1739 - GESTION POR PERMISOS C.C./EDIFICIOS",
    "1740 - SOLICITUD DE FISCALIZADOR",
    "1741 - SOLICITUD DE CUSTODIO",
    "1744 - CORTE FO ACCESO TERCERIZADA - EDIFICIO/C.C.",
    "1745 - ATENUACIÓN FO ACCESO TERCERIZADA - EDIFICIO/C.C.",
    "1746 - REVISIÓN FO ACCESO TERCERIZADA",
    "1761 - EN ESPERA DE REPORTE DE MOVILIZACION",
    "1798 - GESTIÓN POR ACCESOS AL NODO",
    "1799 - NODO EN BATERÍAS",
    "1804 - A LA ESPERA DE PERMISOS POR PARTE DEL C.C/ADMINISTRACIÓN",
    "1805 - A LA ESPERA DE PERMISOS POR PARTE DEL CLIENTE",
    "1806 - A LA ESPERA DE QUE SE DESCARTEN PROBLEMAS ELÉCTRICOS",
    "1807 - A LA ESPERA DE RESPUESTA POR PARTE DE LA EMPRESA TERCERIZADORA",
    "1808 - EN ESPERA DE RESPUESTA DEL CLIENTE (ENVIO DE PRUEBAS)",
    "1809 - NO SE TIENE RESPUESTA DEL CONTACTO PROPORCIONADO",
    "1810 - SOLICITUD DE NUEVO CONTACTO EN SITIO",
    "1812 - PRODUCTO- SOLICITUD DE COTIZACION AL MAYORISTA",
    "1813 - PRODUCTO- SOLICITUD DE COTIZACION AL FABRICANTE",
    "1814 - PRODUCTO- SOLICITUD DE INFORMACION AL CLIENTE FINAL",
    "1815 - PRODUCTO- SOLICITUD DE FACTIBILIDAD A TÉCNICO",
    "1816 - PRODUCTO- SOLICITUD DE APLAZAMIENTO DE COTIZACIÓN PRIORITARIA",
    "1818 - SOLICITUD DE INFORMACION AL ASESOR COMERCIAL",
    "1819 - SOLICITUD DE ASIGNACION DE MAYORISTA",
    "1820 - SOLICITUD DE COTIZACION NO RECURRENTES A IMPORTACIONES",
    "1821 - SOLICITUD DE COTIZACION NO RECURRENTES A COMPRAS",
    "1831 - INACTIVACION POR MORA",
    "1832 - CONVENIO DE PAGO",
    "1833 - CONFIRMACION DE PAGO",
    "1834 - N/D PENDIENTE",
    "1835 - N/C PENDIENTE",
    "1836 - SOLICTUD DE SLA Y CACTI",
    "1837 - CONFIRMACION FECHA DE PAGO",
    "2376 - GESTION DE EXAMENES MEDICOS",
    "2377 - SOLICITUD DE PLANOS ARQUITECTONICOS AL CLIENTE",
    "2378 - GESTION DE RECURSOS ADICIONALES DE PERSONAL TECNICO",
    "2379 - A LA ESPERA DE INFORMES TECNICOS",
    "2380 - GESTION DE APROVISIONAMIENTO DE MATERIALES",
    "2381 - GESTION DE DOCUMENTACION PARA INGRESO A INSTALACION A CLIENTE",
    "2995 - POR ESPERA RESPUESTA DEL USUARIO",
    "2996 - POR FIRMA DE LA ORDEN DE COMPRA",
    "2997 - POR CREACION DE CODIGO DEL ITEM POR PARTE DE BODEGA",
    "2998 - POR CREACION DE PROVEEDOR POR PARTE DE CONTABILIDAD",
    "2999 - POR GESTION DE ENTREGA PROVEEDOR",
    "3649 - CLIENTE SOLICITA REPROGRAMAR",
    "4214 - DESARROLLO IyD",
    "4215 - IA-VISION SOLICITUD DE FACTIBILIDAD",
    "4216 - LLM-PROCESOS SOLICITUD DE FACTIBILIDAD",
    "4217 - SOLICITUD DE FACTIBILIDAD",
)


def _p(
    name: str,
    label: str,
    *,
    kind: str = "text",
    required: bool = False,
    default: str = "",
    options: tuple[str, ...] = (),
) -> ParameterDefinition:
    return ParameterDefinition(name, label, kind, required, default, options)


ACTION_DEFINITIONS = (
    ActionDefinition("abrir_tareas_personales", "Abrir Tareas personales", "Navegación", "Abre el panel principal."),
    ActionDefinition("ingresar_numero_tarea", "Escribir N° de tarea", "Búsqueda", "Escribe el número; vacío usa la tarea del contexto.", (_p("numero", "Número"),)),
    ActionDefinition("consultar", "Consultar", "Búsqueda", "Ejecuta la consulta y espera el resultado real."),
    ActionDefinition("filtrar_tareas", "Filtrar resultados", "Tabla", "Filtra la tabla.", (_p("texto", "Texto", required=True),)),
    ActionDefinition("seleccionar_tarea", "Seleccionar tarea", "Tabla", "Selecciona la tarea esperada.", (_p("numero", "Número de referencia"),)),
    ActionDefinition("reanudar_tarea", "Ejecutar o reanudar tarea", "Ejecución", "Abre Ejecutar si está asignada o Reanudar si está pausada. Después escriba la observación y pulse Aceptar."),
    ActionDefinition("ingresar_observacion", "Escribir observación", "Ejecución", "Completa la observación.", (_p("texto", "Observación", required=True),)),
    ActionDefinition("aceptar_observacion", "Aceptar observación", "Ejecución", "Guarda la observación."),
    ActionDefinition("cerrar_mensaje_ok", "Cerrar mensaje OK", "Modal", "Cierra la confirmación."),
    ActionDefinition("abrir_seguimiento", "Abrir seguimiento", "Seguimiento", "Abre el panel de seguimiento."),
    ActionDefinition("guardar_seguimiento", "Guardar seguimiento", "Seguimiento", "Guarda el seguimiento."),
    ActionDefinition("escribir_seguimiento", "Escribir seguimiento", "Seguimiento", "Complete el texto que se guardará en la tarea.", (_p("texto", "Seguimiento", required=True),), ("abrir_seguimiento",)),
    ActionDefinition("abrir_subida_archivo", "Abrir carga de archivo", "Archivos", "Abre el panel de archivos."),
    ActionDefinition("seleccionar_archivo", "Seleccionar archivo", "Archivos", "Elija un archivo o busque por tipos en la carpeta de la tarea. Los documentos requeridos se validan antes de iniciar cualquier paso.", (_p("ruta", "Ruta / alias / patrón", kind="file", default="@archivo_tarea"),), ("abrir_subida_archivo",)),
    ActionDefinition("subir_archivo", "Subir archivo", "Archivos", "Carga y verifica el resultado.", (), ("seleccionar_archivo",)),
    ActionDefinition("cerrar_mensaje_fin_tarea", "Cerrar fin de tarea", "Modal", "Cierra la confirmación final."),
    ActionDefinition("abrir_reasignar", "Abrir reasignación", "Reasignación", "Abre el panel de reasignación."),
    ActionDefinition("ingresar_departamento", "Elegir departamento", "Reasignación", "Selecciona el departamento.", (_p("nombre", "Departamento", required=True),), ("abrir_reasignar",)),
    ActionDefinition("ingresar_empleado", "Elegir empleado", "Reasignación", "Selecciona el empleado.", (_p("nombre", "Empleado", required=True),), ("abrir_reasignar",)),
    ActionDefinition("observacion_reasignacion", "Observación de reasignación", "Reasignación", "Escribe la observación.", (_p("texto", "Observación", required=True),), ("abrir_reasignar",)),
    ActionDefinition("guardar_reasignacion", "Guardar reasignación", "Reasignación", "Guarda y verifica la reasignación.", (), ("abrir_reasignar",)),
    ActionDefinition("definir_variable", "Definir variable", "Datos", "Crea una variable reutilizable.", (_p("nombre", "Nombre", required=True), _p("valor", "Valor", required=True))),
    ActionDefinition("capturar_dato", "Capturar desde Telcos", "Datos", "Guarda texto o atributo de un elemento.", (_p("selector_css", "Selector CSS", required=True), _p("nombre", "Variable", required=True), _p("atributo", "Atributo", default="text"))),
    ActionDefinition("esperar_elemento", "Esperar elemento", "Control", "Espera un estado comprobable.", (_p("selector_css", "Selector CSS", required=True), _p("estado", "Estado", kind="choice", default="visible", options=("visible", "presente", "habilitado", "oculto")), _p("tiempo", "Máximo (segundos)", default="20"))),
    ActionDefinition("pausar_tarea", "Pausar tarea", "Ejecución", "Abre el formulario de pausa."),
    ActionDefinition("motivo_pausa", "Seleccionar motivo", "Ejecución", "Selecciona el catálogo de pausa.", (_p("valor_o_label", "Motivo", kind="choice", required=True, options=PAUSE_REASONS),), ("pausar_tarea",)),
    ActionDefinition("aceptar_pausa", "Confirmar pausa", "Ejecución", "Guarda la pausa.", (), ("motivo_pausa",)),
    ActionDefinition("capturar_datos_tarea", "Guardar datos de la tarea", "Datos", "Lee la fila seleccionada y permite usar {telcos_estado}, {telcos_tarea}, {telcos_observacion}, {telcos_responsable} y otros datos en los pasos siguientes. Solo necesita el número de tarea.", (), ("seleccionar_tarea",)),
    ActionDefinition("ver_seguimiento", "Ver historial de seguimiento", "Seguimiento", "Abre la lupa de la fila seleccionada para consultar sus observaciones.", (), ("seleccionar_tarea",)),
    ActionDefinition("ver_archivos", "Ver archivos de la tarea", "Archivos", "Abre el ojo de la fila seleccionada para consultar los documentos cargados.", (), ("seleccionar_tarea",)),
    ActionDefinition("cerrar_panel", "Cerrar ventana sin guardar", "Control", "Cierra la ventana de Telcos abierta por el flujo usando Cerrar o Cancelar."),
    ActionDefinition("verificar_estado", "Comprobar estado de la tarea", "Control", "Detiene el flujo si la tarea no tiene el estado esperado.", (_p("estado", "Estado esperado", kind="choice", required=True, options=("Asignada", "Aceptada", "Pausada", "Finalizada", "Cancelada", "Anulada")),), ("seleccionar_tarea",)),
)

ACTION_REGISTRY = {item.action_id: item for item in ACTION_DEFINITIONS}

# Acciones que confirman cambios en Telcos. Si un paso posterior falla no es seguro
# volver a ejecutar el flujo completo, porque podría duplicar una observación, una
# carga o una reasignación. Las esperas de cada Page Object sí se reintentan.
IRREVERSIBLE_ACTIONS = frozenset(
    {
        "aceptar_observacion",
        "guardar_seguimiento",
        "subir_archivo",
        "guardar_reasignacion",
        "aceptar_pausa",
    }
)


class WorkflowExecutionError(RuntimeError):
    def __init__(
        self,
        step_number: int,
        action_id: str,
        cause: Exception,
        *,
        context: dict[str, Any] | None = None,
    ):
        self.step_number = step_number
        self.action_id = action_id
        self.cause = cause
        self.context = dict(context or {})
        self.completed_actions = tuple(self.context.get("pasos_completados", ()))
        label = ACTION_REGISTRY.get(action_id)
        action = label.label if label else action_id
        guidance = " Revise el flujo en Editor visual → Revisar y reparar flujo; allí se indica qué elemento agregar y después de qué paso."
        super().__init__(f"Paso {step_number} ({action}): {cause}{guidance}")


class WorkflowActionExecutor(Protocol):
    def execute(self, action_id: str, params: dict[str, Any], context: dict[str, Any]) -> None: ...


def expand_workflow(workflow: WorkflowDefinition) -> WorkflowDefinition:
    def flatten(steps, depth=0):
        if depth > 12:
            raise ValueError("Demasiados niveles de flujos incluidos.")
        result = []
        for step in steps:
            if step.action_id == "ejecutar_flujo":
                children = step.params.get("pasos", [])
                if not children:
                    raise ValueError("El flujo incluido no contiene pasos.")
                result.extend(flatten([FlowStep.model_validate(child) for child in children], depth + 1))
            else:
                result.append(step.model_copy(deep=True))
            if len(result) > 1000:
                raise ValueError("El flujo supera 1000 pasos.")
        return result
    return workflow.model_copy(update={"steps": flatten(workflow.steps)})


def validate_workflow(workflow: WorkflowDefinition) -> list[str]:
    try:
        workflow = expand_workflow(workflow)
    except ValueError as exc:
        return [str(exc)]
    errors: list[str] = []
    seen: list[str] = []
    if not workflow.name.strip():
        errors.append("El flujo necesita un nombre.")
    if not workflow.steps:
        errors.append("El flujo no contiene pasos.")
    for index, step in enumerate(workflow.steps, start=1):
        definition = ACTION_REGISTRY.get(step.action_id)
        if definition is None:
            errors.append(f"Paso {index}: acción no soportada '{step.action_id}'.")
            continue
        for dependency in definition.requires_previous:
            if dependency not in seen:
                label = ACTION_REGISTRY[dependency].label
                errors.append(f"Paso {index}: primero debe agregarse '{label}'.")
        if step.action_id == "seleccionar_archivo" and step.params.get("modo_archivo") == "tipos":
            if not isinstance(step.params.get("tipos_archivo"), list) or not step.params["tipos_archivo"]:
                errors.append(f"Paso {index}: seleccione al menos un tipo de documento.")
        for parameter in definition.parameters:
            value = step.params.get(parameter.name, parameter.default)
            if parameter.required and not str(value or "").strip():
                errors.append(f"Paso {index}: falta '{parameter.label}'.")
        if step.action_id == "esperar_elemento":
            try:
                timeout = int(float(step.params.get("tiempo", 20)))
                if not 1 <= timeout <= 120:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(f"Paso {index}: el tiempo debe estar entre 1 y 120 segundos.")
            state = str(step.params.get("estado") or "visible")
            if state not in {"visible", "presente", "habilitado", "oculto"}:
                errors.append(f"Paso {index}: el estado de espera no es válido.")
        if step.action_id in {"definir_variable", "capturar_dato"}:
            name = str(step.params.get("nombre") or "")
            if name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                errors.append(f"Paso {index}: el nombre de variable no es válido.")
        seen.append(step.action_id)
    return errors


def resolve_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(resolve_value(item, context) for item in value)
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            raise ValueError(f"Falta el dato '{key}' requerido por {match.group(0)}.")
        item = context[key]
        if item is None or (isinstance(item, str) and not item.strip()):
            raise ValueError(f"Falta el dato '{key}' requerido por {match.group(0)}.")
        if isinstance(item, (list, tuple)):
            return ", ".join(str(part) for part in item if part is not None)
        return str(item)

    return PLACEHOLDER.sub(replace, value)


class WorkflowEngine:
    def __init__(self, executor: WorkflowActionExecutor, progress: Callable[[int, int, str], None] | None = None):
        self.executor = executor
        self.progress = progress

    def execute(self, workflow: WorkflowDefinition, task: TaskRecord) -> dict[str, Any]:
        workflow = expand_workflow(workflow)
        errors = validate_workflow(workflow)
        if errors:
            raise ValueError("Flujo inválido:\n- " + "\n- ".join(errors))
        context = dict(task.payload)
        context.update(
            task_number=task.task_number,
            numero_tarea=task.task_number,
            orden_compra=task.order_number,
            proveedor=task.supplier,
            origen=task.origin,
        )
        context["pasos_completados"] = []
        from compras_tn.application.task_orders import task_orders, missing_order_data
        rows = task_orders(task)
        missing = missing_order_data(workflow, task)
        if missing:
            raise ValueError("\n".join(missing))
        context["orders"] = rows
        if rows:
            context["orden_compra"] = ", ".join(row["order_number"] for row in rows if row["order_number"])
            context["proveedor"] = ", ".join(dict.fromkeys(row["supplier"] for row in rows if row["supplier"]))
        context["aprobadores"] = ", ".join(dict.fromkeys(name for row in rows for name in row["approvers"]))
        preflight = getattr(self.executor, 'preflight', None)
        if callable(preflight):
            preflight(workflow, context)
        for index, step in enumerate(workflow.steps, start=1):
            if self.progress:
                self.progress(index, len(workflow.steps), ACTION_REGISTRY[step.action_id].label)
            context["paso_actual"] = index
            context["accion_actual"] = step.action_id
            try:
                params = {
                    key: resolve_value(value, context) for key, value in step.params.items()
                }
                if step.action_id in {"ingresar_observacion", "escribir_seguimiento", "observacion_reasignacion"}:
                    template = step.params.get("texto", "")
                    if isinstance(template, str) and len(rows) > 1 and any("{" + token + "}" in template for token in ("orden_compra", "proveedor", "aprobadores")):
                        params["texto"] = "\n".join(resolve_value(template, {**context,
                            "orden_compra": row["order_number"], "proveedor": row["supplier"],
                            "aprobadores": ", ".join(row["approvers"])}) for row in rows)
                if step.action_id == "ingresar_numero_tarea" and not str(
                    params.get("numero", "")
                ).strip():
                    params["numero"] = task.task_number
                if step.action_id == "seleccionar_archivo":
                    params.setdefault("ruta", "@archivo_tarea")
                self.executor.execute(step.action_id, params, context)
            except Exception as exc:
                context["error_paso"] = index
                context["error_accion"] = step.action_id
                context["error_detalle"] = str(exc)
                raise WorkflowExecutionError(
                    index,
                    step.action_id,
                    exc,
                    context=context,
                ) from exc
            context["ultimo_paso"] = index
            context["ultima_accion"] = step.action_id
            context["pasos_completados"].append(step.action_id)
            context.pop("error_paso", None)
            context.pop("error_accion", None)
            context.pop("error_detalle", None)
        finalizer = getattr(self.executor, "finish_task", None)
        if callable(finalizer):
            try:
                finalizer(context)
            except Exception as exc:
                raise WorkflowExecutionError(len(workflow.steps), workflow.steps[-1].action_id, exc, context=context) from exc
        return context
