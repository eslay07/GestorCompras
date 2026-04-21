import tkinter as tk
import threading
import logging
import re
import sys
from datetime import datetime
from tkinter import messagebox
from pathlib import Path

try:  # permite ejecutar como script
    from .escuchador import buscar_ocs, cargar_ultimo_uidl, registrar_procesados
    from .selenium_modulo import descargar_oc
    from .reporter import enviar_reporte
    from .config import Config
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from escuchador import buscar_ocs, cargar_ultimo_uidl, registrar_procesados
    from selenium_modulo import descargar_oc
    from reporter import enviar_reporte
    from config import Config
    from logger import get_logger

logger = get_logger(__name__)

scanning_lock = threading.Lock()

try:
    _ROOT = Path(__file__).resolve().parents[2]
    if str(_ROOT) not in sys.path:
        sys.path.append(str(_ROOT))
    _GESTOR = (_ROOT / "GestorCompras_").resolve()
    if _GESTOR.exists() and str(_GESTOR) not in sys.path:
        sys.path.append(str(_GESTOR))
    from gestorcompras.ui.actua_tareas_gui import abrir_panel_tareas  # type: ignore
except Exception:  # pragma: no cover
    abrir_panel_tareas = None


def center_window(win: tk.Tk | tk.Toplevel):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


def config_completa(cfg: Config) -> bool:
    try:
        cfg.validate()
    except Exception:
        return False
    requeridos = [cfg.carpeta_destino_local, cfg.carpeta_analizar, cfg.correo_reporte]
    return all(requeridos)


class TextHandler(logging.Handler):
    def __init__(self, widget: tk.Text):
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord):
        msg = self.format(record) + "\n"
        self.widget.after(0, lambda m=msg: (self.widget.insert(tk.END, m), self.widget.see(tk.END)))


def realizar_escaneo(text_widget: tk.Text, lbl_last: tk.Label):
    if not scanning_lock.acquire(blocking=False):
        text_widget.insert(tk.END, "Escaneo en progreso...\n")
        text_widget.see(tk.END)
        return
    try:
        cfg = Config()
        if not config_completa(cfg):
            messagebox.showerror(
                "Error", "Configuración incompleta o por favor configurar correctamente"
            )
            return

        def append(msg: str):
            text_widget.after(0, lambda m=msg: (text_widget.insert(tk.END, m), text_widget.see(tk.END)))

        append("Buscando órdenes...\n")
        ordenes, ultimo = buscar_ocs(cfg)
        uidl_por_numero = {
            o.get("numero"): o.get("uidl")
            for o in ordenes
            if o.get("numero") and o.get("uidl")
        }
        uidl_a_numeros: dict[str, set[str]] = {}
        for numero, uidl in uidl_por_numero.items():
            if not uidl:
                continue
            uidl_a_numeros.setdefault(uidl, set()).add(numero)
        pendientes_uidls = set(uidl_a_numeros)
        exitosas: list[str] = []
        faltantes: list[str] = []
        errores: list[str] = []
        if ordenes:
            append(f"Procesando {len(ordenes)} OC(s)\n")
            try:
                subidos, no_encontrados, errores = descargar_oc(
                    ordenes, headless=cfg.headless
                )
            except Exception as exc:  # pragma: no cover - seguridad en ejecución
                logger.exception("Fallo al descargar OC")
                errores = [str(exc)]
                subidos, no_encontrados = [], [o.get("numero") for o in ordenes]
            exitosas.extend(subidos)
            faltantes.extend(no_encontrados)
            numeros_con_problemas = {str(n) for n in no_encontrados}
            for error in errores:
                m = re.search(r"OC\s*(\d+)", error)
                if m:
                    numeros_con_problemas.add(m.group(1))
            uidls_con_problemas = {
                uidl_por_numero[num]
                for num in numeros_con_problemas
                if num in uidl_por_numero and uidl_por_numero[num]
            }
            subidos_set = set(subidos)
            uidls_exitosos: list[str] = []
            for orden in ordenes:
                uidl = orden.get("uidl")
                if not uidl or uidl in uidls_con_problemas:
                    continue
                numeros_uidl = uidl_a_numeros.get(uidl, set())
                if numeros_uidl and numeros_uidl.issubset(subidos_set) and uidl not in uidls_exitosos:
                    uidls_exitosos.append(uidl)
            pendientes_uidls -= set(uidls_exitosos)
            for num in subidos:
                append(f"✔️ OC {num} procesada\n")
            for num in no_encontrados:
                append(f"❌ OC {num} faltante\n")
            if uidls_exitosos:
                uidls_sin_duplicados = list(dict.fromkeys(uidls_exitosos))
                ultimo_guardar = ultimo if not pendientes_uidls else None
                registrar_procesados(uidls_sin_duplicados, ultimo_guardar)
        else:
            append("No se encontraron nuevas órdenes\n")
        enviado = enviar_reporte(exitosas, faltantes, ordenes, cfg, errores=errores)
        try:
            if abrir_panel_tareas and ordenes:
                tasks = []
                for orden in ordenes:
                    tasks.append(
                        {
                            "task_number": str(orden.get("tarea") or ""),
                            "oc": orden.get("numero", ""),
                            "proveedor": orden.get("proveedor", ""),
                            "fecha_orden": orden.get("fecha_orden", ""),
                        }
                    )
                tasks = [t for t in tasks if t["task_number"]]
                if tasks:
                    def _abrir_panel(_tasks=tasks):
                        if messagebox.askyesno(
                            "Actualizar Tareas",
                            "¿Desea abrir el panel de Actualizar Tareas con las OC procesadas?",
                        ):
                            abrir_panel_tareas(
                                text_widget.winfo_toplevel(),
                                {
                                    "address": cfg.usuario_oc,
                                    "password": cfg.password_oc,
                                },
                                "descargas_oc",
                                _tasks,
                            )

                    text_widget.after(0, _abrir_panel)
        except Exception as exc:
            append(f"[Hook Actualizar Tareas] Error no bloqueante: {exc}")
        if ordenes:
            no_aprobadas = [
                e.split(":", 1)[1] for e in errores if e.startswith("OC_NO_APROBADA:")
            ]
            otros_errores = [e for e in errores if not e.startswith("OC_NO_APROBADA:")]
            partes_summary: list[str] = []
            if exitosas:
                partes_summary.append(
                    f"✔ Descargadas correctamente ({len(exitosas)}): "
                    + ", ".join(str(n) for n in exitosas)
                )
            if faltantes:
                partes_summary.append(
                    f"❌ No encontradas ({len(faltantes)}): "
                    + ", ".join(str(n) for n in faltantes)
                )
            if no_aprobadas:
                partes_summary.append(
                    f"⚠ OC no aprobadas — descarga no permitida ({len(no_aprobadas)}): "
                    + ", ".join(no_aprobadas)
                )
            if otros_errores:
                partes_summary.append("Errores adicionales:\n" + "\n".join(otros_errores))
            if not partes_summary:
                partes_summary.append("No se encontraron nuevas órdenes")
            if enviado:
                partes_summary.append("📧 Reporte enviado por correo.")
            summary = "\n\n".join(partes_summary)
            text_widget.after(0, lambda s=summary: messagebox.showinfo("Resultado", s))
        append("Proceso finalizado\n")
        lbl_last.config(
            text="Último UIDL: {} - {}".format(
                cargar_ultimo_uidl(), datetime.now().strftime("%H:%M:%S")
            )
        )
    finally:
        scanning_lock.release()


def main():
    root = tk.Tk()
    root.title("Descargas OC")
    root.geometry("850x620")
    root.tk_setPalette(
        background="#F3F4F6",
        foreground="#374151",
        activeBackground="#1D4ED8",
        activeForeground="#FFFFFF",
        highlightColor="#D1D5DB",
    )
    root.configure(bg="#F3F4F6")

    main_frame = tk.Frame(root, bg="#F3F4F6", padx=20, pady=16)
    main_frame.pack(fill="both", expand=True)
    main_frame.columnconfigure(0, weight=1)
    main_frame.rowconfigure(2, weight=1)

    header = tk.Frame(main_frame, bg="#F3F4F6")
    header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    tk.Label(header, text="Descargas de Ordenes de Compra",
             font=("Segoe UI", 16, "bold"), bg="#F3F4F6", fg="#111827").pack(side="left")

    ctrl_frame = tk.LabelFrame(main_frame, text="Control del escuchador",
                                bg="#FFFFFF", fg="#111827", font=("Segoe UI", 10, "bold"),
                                padx=12, pady=8)
    ctrl_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

    cfg = Config()
    estado = {"activo": False, "contador": 0}
    manual_mode = {"active": False}

    row_auto = tk.Frame(ctrl_frame, bg="#FFFFFF")
    row_auto.pack(fill="x", pady=(0, 6))

    btn_toggle = tk.Button(row_auto, text="Activar escuchador", width=18)
    btn_toggle.pack(side="left", padx=(0, 8))

    btn_escanear = tk.Button(row_auto, text="Escanear ahora", width=14)
    btn_escanear.pack(side="left", padx=(0, 8))

    lbl_contador = tk.Label(row_auto, text="Escuchador detenido",
                            bg="#FFFFFF", fg="#374151", font=("Segoe UI", 10))
    lbl_contador.pack(side="left", padx=(8, 0))

    lbl_last = tk.Label(row_auto, text="Ultimo UIDL: " + (cargar_ultimo_uidl() or '-'),
                        bg="#FFFFFF", fg="#6B7280", font=("Segoe UI", 9))
    lbl_last.pack(side="right")

    row_opts = tk.Frame(ctrl_frame, bg="#FFFFFF")
    row_opts.pack(fill="x", pady=(0, 4))

    var_bienes = tk.BooleanVar(value=bool(cfg.compra_bienes))
    var_visible = tk.BooleanVar(value=not bool(cfg.headless))

    def actualizar_bienes():
        cfg.load()
        cfg.data['compra_bienes'] = var_bienes.get()
        cfg.save()

    def actualizar_visible():
        cfg.load()
        cfg.data['headless'] = not var_visible.get()
        cfg.save()

    tk.Checkbutton(row_opts, text="Compra Bienes", variable=var_bienes,
                   command=actualizar_bienes, bg="#FFFFFF", selectcolor="#059669").pack(side="left", padx=(0, 12))
    tk.Checkbutton(row_opts, text="Mostrar navegador", variable=var_visible,
                   command=actualizar_visible, bg="#FFFFFF", selectcolor="#059669").pack(side="left", padx=(0, 16))

    tk.Label(row_opts, text="Intervalo (seg):", bg="#FFFFFF").pack(side="left", padx=(8, 4))
    entry_interval = tk.Entry(row_opts, width=6)
    entry_interval.insert(0, str(cfg.scan_interval))
    entry_interval.pack(side="left")

    def actualizar_intervalo():
        try:
            val = int(entry_interval.get())
            if val >= 300:
                cfg.load()
                cfg.data['scan_interval'] = val
                cfg.save()
                estado['contador'] = val
                messagebox.showinfo("Guardado", f"Intervalo actualizado a {val} segundos.")
        except ValueError:
            messagebox.showwarning("Advertencia", "Ingrese un numero valido (minimo 300).")

    tk.Button(row_opts, text="Guardar intervalo", command=actualizar_intervalo).pack(side="left", padx=(6, 0))

    row_manual = tk.Frame(ctrl_frame, bg="#FFFFFF")
    row_manual.pack(fill="x")

    btn_manual = tk.Button(row_manual, text="Descarga manual", width=16)
    btn_manual.pack(side="left", padx=(0, 8))
    btn_ejecutar = tk.Button(row_manual, text="Ejecutar descarga", width=16, state=tk.DISABLED)
    btn_ejecutar.pack(side="left")
    tk.Label(row_manual, text="Ingrese numeros de OC en el area de texto y presione Ejecutar.",
             bg="#FFFFFF", fg="#6B7280", font=("Segoe UI", 9)).pack(side="left", padx=(12, 0))

    log_frame = tk.LabelFrame(main_frame, text="Registro de actividad",
                               bg="#FFFFFF", fg="#111827", font=("Segoe UI", 10, "bold"),
                               padx=10, pady=8)
    log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 0))

    text = tk.Text(log_frame, width=80, height=18, bg="#FFFFFF", fg="#374151",
                   insertbackground="#374151", font=("Segoe UI", 10),
                   relief="solid", borderwidth=1)
    text.pack(fill="both", expand=True, pady=(0, 4))

    handler = TextHandler(text)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logging.getLogger().addHandler(handler)

    def actualizar_contador():
        if estado["activo"]:
            if estado["contador"] <= 0:
                threading.Thread(target=realizar_escaneo, args=(text, lbl_last), daemon=True).start()
                estado["contador"] = cfg.scan_interval
            lbl_contador.config(text=f"Siguiente escaneo en {estado['contador']} s")
            estado["contador"] -= 1
            root.after(1000, actualizar_contador)
        else:
            lbl_contador.config(text="Escuchador detenido")

    def toggle():
        if estado["activo"]:
            estado["activo"] = False
            btn_toggle.config(text="Activar escuchador")
        else:
            if not config_completa(cfg):
                messagebox.showerror("Error", "Configuracion incompleta. Verifique los parametros en Configuracion.")
                return
            estado["activo"] = True
            estado["contador"] = cfg.scan_interval
            btn_toggle.config(text="Detener escuchador")
            actualizar_contador()

    def escanear_ahora():
        estado["contador"] = cfg.scan_interval
        threading.Thread(target=realizar_escaneo, args=(text, lbl_last), daemon=True).start()

    def activar_manual():
        manual_mode["active"] = True
        text.delete("1.0", tk.END)
        text.insert(tk.END, "Ingrese los numeros de OC a descargar, uno por linea:\n")
        btn_ejecutar.config(state=tk.DISABLED)
        text.focus_set()

    def check_manual_input(event=None):
        if manual_mode["active"]:
            contenido = text.get("2.0", tk.END).strip()
            btn_ejecutar.config(state=tk.NORMAL if contenido else tk.DISABLED)

    text.bind("<KeyRelease>", check_manual_input)

    def ejecutar_manual():
        if not scanning_lock.acquire(blocking=False):
            text.insert(tk.END, "Descarga en progreso...\n")
            text.see(tk.END)
            return
        contenido = text.get("2.0", tk.END).strip()
        numeros = [n.strip() for n in contenido.splitlines() if n.strip()]
        if not numeros:
            scanning_lock.release()
            return
        if not messagebox.askyesno("Confirmar", f"Se descargaran {len(numeros)} orden(es):\n" + "\n".join(numeros)):
            scanning_lock.release()
            return
        text.delete("1.0", tk.END)
        manual_mode["active"] = False
        btn_ejecutar.config(state=tk.DISABLED)

        def run():
            try:
                cfg.load()
                ordenes = [{"numero": n} for n in numeros]

                def append(msg: str):
                    text.after(0, lambda m=msg: (text.insert(tk.END, m), text.see(tk.END)))

                append(f"Procesando {len(ordenes)} OC(s)\n")
                try:
                    subidos, no_encontrados, errores = descargar_oc(ordenes, headless=cfg.headless)
                except Exception as exc:
                    errores = [str(exc)]
                    subidos, no_encontrados = [], numeros
                for num in subidos:
                    append(f"  OC {num} descargada correctamente\n")
                for num in no_encontrados:
                    append(f"  OC {num} no encontrada\n")
                enviar_reporte(subidos, no_encontrados, ordenes, cfg, errores=errores)
                no_aprobadas = [e.split(":", 1)[1] for e in errores if e.startswith("OC_NO_APROBADA:")]
                otros_errores = [e for e in errores if not e.startswith("OC_NO_APROBADA:")]
                partes: list[str] = []
                if subidos:
                    partes.append(f"Descargadas ({len(subidos)}): " + ", ".join(str(n) for n in subidos))
                if no_encontrados:
                    partes.append(f"No encontradas ({len(no_encontrados)}): " + ", ".join(str(n) for n in no_encontrados))
                if no_aprobadas:
                    partes.append(f"No aprobadas ({len(no_aprobadas)}): " + ", ".join(no_aprobadas))
                if otros_errores:
                    partes.append("Errores:\n" + "\n".join(otros_errores))
                summary = "\n\n".join(partes) if partes else "Proceso finalizado"
                text.after(0, lambda s=summary: messagebox.showinfo("Resultado", s))
            finally:
                scanning_lock.release()
                text.after(0, lambda: btn_ejecutar.config(state=tk.DISABLED))

        threading.Thread(target=run, daemon=True).start()

    btn_toggle.configure(command=toggle)
    btn_escanear.configure(command=escanear_ahora)
    btn_manual.configure(command=activar_manual)
    btn_ejecutar.configure(command=ejecutar_manual)

    center_window(root)
    root.mainloop()


if __name__ == '__main__':
    main()
