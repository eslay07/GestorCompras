from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path

ASSETS = Path(__file__).parent / "assets" / "telcos"


@dataclass(frozen=True)
class ActionReference:
    image: str
    location: str
    note: str = ""
    internal: bool = False

    @property
    def path(self) -> Path:
        return ASSETS / (self.image + ".jpg")


# Fotografías de los controles, tomadas en Telcos el 13/10/2026.
REFERENCES = {
    "abrir_tareas_personales": ActionReference("tareas_personales", "Barra superior · Tareas pendientes personales"),
    "ingresar_numero_tarea": ActionReference("numero_tarea", "Filtros · Número tarea", "Deje el número vacío en el paso para usar el ingresado al ejecutar."),
    "consultar": ActionReference("consultar", "Filtros · Consultar (lupa)"),
    "filtrar_tareas": ActionReference("filtro", "Tabla · Buscar"),
    "seleccionar_tarea": ActionReference("acciones", "Tabla · fila del número solicitado", "No tiene un botón propio: selecciona la fila exacta."),
    "reanudar_tarea": ActionReference("reanudar", "Fila · Ejecutar o Reanudar", "Asignada: triángulo Ejecutar. Pausada: Reanudar. Requiere observación y Aceptar."),
    "ingresar_observacion": ActionReference("observacion", "Ventana Ejecutar / Reanudar · Observación", "Es un campo de texto, no un icono."),
    "aceptar_observacion": ActionReference("aceptar", "Ventana Ejecutar / Reanudar · Aceptar", "Guarda un cambio en Telcos."),
    "cerrar_mensaje_ok": ActionReference("confirmacion", "Mensaje · OK"),
    "abrir_seguimiento": ActionReference("seguimiento", "Fila · Ingresar Seguimiento (lista)"),
    "escribir_seguimiento": ActionReference("texto_seguimiento", "Ingresar Seguimiento · Seguimiento", "Es un campo de texto, no un icono."),
    "guardar_seguimiento": ActionReference("guardar_seguimiento", "Ingresar Seguimiento · Guardar", "Guarda un cambio en Telcos."),
    "abrir_subida_archivo": ActionReference("cargar_archivo", "Fila · Cargar Archivo"),
    "seleccionar_archivo": ActionReference("selector_archivo", "Subir Archivos Tareas · Seleccionar Archivos"),
    "subir_archivo": ActionReference("subir", "Subir Archivos Tareas · Subir", "Carga el archivo en Telcos."),
    "cerrar_mensaje_fin_tarea": ActionReference("confirmacion", "Mensaje final · OK", "El texto del mensaje depende de la operación."),
    "abrir_reasignar": ActionReference("reasignar", "Fila · Reasignar Tarea (velocímetro)", "Abrir la ventana no cambia el responsable. Guardar sí lo cambia."),
    "ingresar_departamento": ActionReference("departamento", "Reasignar Tarea · Departamento"),
    "ingresar_empleado": ActionReference("empleado", "Reasignar Tarea · Empleado"),
    "observacion_reasignacion": ActionReference("observacion_reasignacion", "Reasignar Tarea · Observación"),
    "guardar_reasignacion": ActionReference("guardar_reasignacion", "Reasignar Tarea · Guardar", "Cambia la persona responsable. Revise el destino antes de ejecutar."),
    "definir_variable": ActionReference("", "Dentro del orquestador", "No existe un símbolo de Telcos: guarda un dato para reutilizarlo.", True),
    "capturar_dato": ActionReference("", "Dentro del orquestador · opción técnica", "No tiene símbolo en Telcos. Para comenzar use Guardar datos de la tarea.", True),
    "esperar_elemento": ActionReference("", "Dentro del orquestador · opción técnica", "No tiene símbolo en Telcos: espera que aparezca o desaparezca un control.", True),
    "pausar_tarea": ActionReference("pausar", "Fila · Pausar Tarea (dos barras)", "Disponible cuando la tarea está Aceptada."),
    "motivo_pausa": ActionReference("motivo_pausa", "Pausar Tarea · Motivo Pausa"),
    "aceptar_pausa": ActionReference("aceptar_pausa", "Pausar Tarea · Aceptar", "Guarda la pausa en Telcos."),
    "capturar_datos_tarea": ActionReference("acciones", "Tabla · datos de la fila seleccionada", "Lectura automática. Use los datos como {telcos_estado} o {telcos_responsable}."),
    "ver_seguimiento": ActionReference("ver_seguimiento", "Fila · Ver Seguimiento (lupa)"),
    "ver_archivos": ActionReference("ver_archivos", "Fila · Ver Archivos (ojo)"),
    "cerrar_panel": ActionReference("cerrar", "Ventana abierta · Cerrar / Cancelar", "Cierra sin guardar."),
    "verificar_estado": ActionReference("", "Dentro del orquestador", "Comprueba la columna Estado. No tiene un símbolo propio en Telcos.", True),
}


def tooltip(action_id: str, description: str) -> str:
    ref = REFERENCES[action_id]
    picture = ""
    if ref.image and ref.path.is_file():
        picture = f'<p><img src="{ref.path.as_uri()}" /></p>'
    return f"<p>{escape(description)}</p>{picture}<p><b>{escape(ref.location)}</b></p><p>{escape(ref.note)}</p>"


OTHER_CONTROLS = (
    ("Reprogramar tarea", ActionReference("reprogramar", "Fila · Reprogramar Tarea (flechas)", "Cambia fecha, hora y observación. Disponible en la tarea Aceptada y Pausada. Úselo directamente en Telcos.")),
    ("Finalizar tarea", ActionReference("finalizar", "Fila · Finalizar Tarea (cuadrado)", "Cierra el trabajo y puede pedir datos adicionales. Úselo directamente en Telcos después de revisar la tarea.")),
    ("Cancelar tarea", ActionReference("cancelar", "Fila · Cancelar Tarea (círculo con cruz)", "Cambia la tarea a cancelada. Úselo directamente en Telcos después de revisar la tarea.")),
    ("Crear tarea", ActionReference("crear", "Fila · Crear Tarea (círculo con más)", "Crea una tarea relacionada. Úselo directamente en Telcos.")),
)
