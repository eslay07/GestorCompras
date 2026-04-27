"""Ruteo centralizado entre pantallas principales."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

_container: tk.Misc | None = None
_email_session: dict[str, str] | None = None
_sidebar = None


def configure(container: tk.Misc, email_session: dict[str, str], *, sidebar=None) -> None:
    global _container, _email_session, _sidebar
    _container = container
    _email_session = email_session
    _sidebar = sidebar


def _clear_container() -> None:
    if _container is None:
        raise RuntimeError("Router no inicializado")
    for widget in list(_container.winfo_children()):
        widget.destroy()


def _root() -> tk.Misc:
    if _container is None:
        raise RuntimeError("Router no inicializado")
    return _container.winfo_toplevel()


def show_welcome() -> None:
    _clear_container()
    from gestorcompras.ui.home import WelcomeScreen
    WelcomeScreen(_container, _email_session or {}).pack(fill="both", expand=True)


def open_module(module_id: str) -> None:
    if _email_session is None:
        raise RuntimeError("Sesion de correo no inicializada")

    handler = _MODULE_MAP.get(module_id)
    if handler is None:
        messagebox.showerror("Error", f"Modulo desconocido: {module_id}", parent=_root())
        return
    handler()


def _open_bienes_reasignacion() -> None:
    open_home()
    from gestorcompras.modules import reasignacion_gui
    reasignacion_gui.open(_root(), _email_session, mode="bienes")


def _open_bienes_correos() -> None:
    open_home()
    from gestorcompras.modules import correos_masivos_gui
    correos_masivos_gui.open(_root(), _email_session)


def _open_bienes_seguimientos() -> None:
    open_home()
    from gestorcompras.gui import seguimientos_gui
    seguimientos_gui.open_seguimientos(_root(), _email_session)


def _open_bienes_descargas() -> None:
    open_home()
    from gestorcompras.modules import descargas_oc_gui
    descargas_oc_gui.open(_root(), _email_session)


def _open_bienes_actua() -> None:
    open_actua_tareas(origin="bienes")


def _open_servicios_reasignacion() -> None:
    open_home()
    from gestorcompras.modules import reasignacion_gui
    reasignacion_gui.open(_root(), _email_session, mode="servicios")


def _open_servicios_correos() -> None:
    open_home()
    from gestorcompras.modules import correos_masivos_gui
    correos_masivos_gui.open(_root(), _email_session)


def _open_servicios_descargas() -> None:
    open_home()
    from gestorcompras.modules import descargas_oc_gui
    descargas_oc_gui.open(_root(), _email_session)


def _open_servicios_actua() -> None:
    open_actua_tareas(origin="servicios")


def _open_config() -> None:
    open_home()
    from gestorcompras.gui import config_gui
    config_gui.open_config_gui(_root(), _email_session)


def _do_logout() -> None:
    root = _root()
    if messagebox.askyesno("Cerrar Sesion", "¿Desea cerrar la sesion actual?", parent=root):
        root.destroy()


_MODULE_MAP: dict[str, callable] = {
    "bienes_reasignacion": _open_bienes_reasignacion,
    "bienes_correos": _open_bienes_correos,
    "bienes_seguimientos": _open_bienes_seguimientos,
    "bienes_descargas": _open_bienes_descargas,
    "bienes_actua": _open_bienes_actua,
    "servicios_reasignacion": _open_servicios_reasignacion,
    "servicios_correos": _open_servicios_correos,
    "servicios_descargas": _open_servicios_descargas,
    "servicios_actua": _open_servicios_actua,
    "config": _open_config,
    "logout": _do_logout,
}


def open_home() -> None:
    show_welcome()
    if _sidebar is not None:
        _sidebar.set_active("")


def open_actua_tareas(origin: str = "bienes") -> None:
    if _email_session is None:
        raise RuntimeError("Sesion de correo no inicializada")
    _clear_container()
    from gestorcompras.ui.actua_tareas_gui import ActuaTareasScreen
    ActuaTareasScreen(_container, _email_session, origin=origin).pack(fill="both", expand=True)
