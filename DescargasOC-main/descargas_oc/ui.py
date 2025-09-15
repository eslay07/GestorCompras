import tkinter as tk
import threading
import logging
from datetime import datetime
from tkinter import messagebox

try:  # allow running as script
    from .configurador import configurar
    from .escuchador import buscar_ocs, cargar_ultimo_uidl, registrar_procesados
    from .selenium_modulo import descargar_oc
    from .reporter import enviar_reporte
    from .config import Config
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from configurador import configurar
    from escuchador import buscar_ocs, cargar_ultimo_uidl, registrar_procesados
    from selenium_modulo import descargar_oc
    from reporter import enviar_reporte
    from config import Config
    from logger import get_logger

logger = get_logger(__name__)

scanning_lock = threading.Lock()


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
    requeridos = [
        cfg.usuario,
        cfg.password,
        cfg.carpeta_destino_local,
        cfg.carpeta_analizar,
        cfg.seafile_url,
        cfg.seafile_repo_id,
        cfg.correo_reporte,
    ]
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
        exitosas: list[str] = []
        faltantes: list[str] = []
        errores: list[str] = []
        if ordenes:
            append(f"Procesando {len(ordenes)} OC(s)\n")
            try:
                subidos, no_encontrados, errores = descargar_oc(
                    ordenes, headless=cfg.headless
                )
            except Exception as exc:  # pragma: no cover - runtime safety
                logger.exception("Fallo al descargar OC")
                errores = [str(exc)]
                subidos, no_encontrados = [], [o.get("numero") for o in ordenes]
            exitosas.extend(subidos)
            faltantes.extend(no_encontrados)
            for num in subidos:
                append(f"✔️ OC {num} procesada\n")
            for num in no_encontrados:
                append(f"❌ OC {num} faltante\n")
        else:
            append("No se encontraron nuevas órdenes\n")
        enviado = enviar_reporte(exitosas, faltantes, ordenes, cfg)
        if enviado:
            registrar_procesados([o['uidl'] for o in ordenes], ultimo)
        if ordenes:
            if errores:
                summary = "Errores durante la descarga:\n" + "\n".join(errores)
            elif enviado:
                summary = "ORDENES DE COMPRA DESCARGADAS Y REPORTE ENVIADO"
            else:
                summary = "No se pudo enviar el reporte"
            text_widget.after(0, lambda: messagebox.showinfo("Resultado", summary))
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
    root.tk_setPalette(
        background="#1e1e1e",
        foreground="#f0f0f0",
        activeBackground="#333333",
        activeForeground="#f0f0f0",
        highlightColor="#555555",
    )
    root.configure(bg="#1e1e1e")

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    text = tk.Text(frame, width=80, height=20, bg="#000000", fg="#f0f0f0", insertbackground="#f0f0f0")
    text.pack(pady=5)

    handler = TextHandler(text)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logging.getLogger().addHandler(handler)

    estado = {"activo": False, "contador": 0}
    lbl_contador = tk.Label(frame, text="Escuchador detenido")
    lbl_contador.pack()
    lbl_last = tk.Label(frame, text="Último UIDL: " + (cargar_ultimo_uidl() or '-'))
    lbl_last.pack()

    cfg = Config()
    manual_mode = {"active": False}

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
                messagebox.showerror(
                    "Error",
                    "Configuración incompleta o por favor configurar correctamente",
                )
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
        text.insert(tk.END, "Introduzca ordenes que desea descargar 1 por linea:\n")
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
        if not messagebox.askyesno(
            "Confirmación",
            "Se descargarán las siguientes órdenes:\n" + "\n".join(numeros),
        ):
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
                    subidos, no_encontrados, errores = descargar_oc(
                        ordenes, headless=cfg.headless
                    )
                except Exception as exc:
                    errores = [str(exc)]
                    subidos, no_encontrados = [], numeros
                for num in subidos:
                    append(f"✔️ OC {num} procesada\n")
                for num in no_encontrados:
                    append(f"❌ OC {num} faltante\n")
                enviar_reporte(subidos, no_encontrados, ordenes, cfg)
                if errores:
                    summary = "Errores durante la descarga:\n" + "\n".join(errores)
                else:
                    summary = "Proceso finalizado"
                text.after(0, lambda: messagebox.showinfo("Resultado", summary))
            finally:
                scanning_lock.release()
                text.after(0, lambda: btn_ejecutar.config(state=tk.DISABLED))

        threading.Thread(target=run, daemon=True).start()

    def actualizar_intervalo():
        try:
            val = int(entry_interval.get())
            if val >= 300:
                cfg.load()
                cfg.data['scan_interval'] = val
                cfg.save()
                estado['contador'] = val
        except ValueError:
            pass

    btn_toggle = tk.Button(frame, text="Activar escuchador", command=toggle)
    btn_toggle.pack(side=tk.LEFT, padx=5)

    btn_escanear = tk.Button(frame, text="Escanear ahora", command=escanear_ahora)
    btn_escanear.pack(side=tk.LEFT, padx=5)

    btn_manual = tk.Button(frame, text="Descarga manual", command=activar_manual)
    btn_manual.pack(side=tk.LEFT, padx=5)
    btn_ejecutar = tk.Button(frame, text="Ejecutar descarga", command=ejecutar_manual, state=tk.DISABLED)
    btn_ejecutar.pack(side=tk.LEFT, padx=5)

    def abrir_config():
        configurar()
        cfg.load()
        var_bienes.set(bool(cfg.compra_bienes))
        var_visible.set(not bool(cfg.headless))
        try:
            entry_interval.delete(0, tk.END)
            entry_interval.insert(0, str(cfg.scan_interval))
        except tk.TclError:
            logger.error("Campo de intervalo no disponible", exc_info=True)

    btn_config = tk.Button(frame, text="Configuración", command=abrir_config)
    btn_config.pack(side=tk.LEFT, padx=5)

    var_bienes = tk.BooleanVar(value=bool(cfg.compra_bienes))

    def actualizar_bienes():
        cfg.load()
        cfg.data['compra_bienes'] = var_bienes.get()
        cfg.save()

    chk_bienes = tk.Checkbutton(
        frame,
        text="Compra Bienes",
        variable=var_bienes,
        command=actualizar_bienes,
        selectcolor="#00aa00",
    )
    chk_bienes.pack(side=tk.LEFT, padx=5)

    var_visible = tk.BooleanVar(value=not bool(cfg.headless))

    def actualizar_visible():
        cfg.load()
        cfg.data['headless'] = not var_visible.get()
        cfg.save()

    chk_visible = tk.Checkbutton(
        frame,
        text="Descarga visible",
        variable=var_visible,
        command=actualizar_visible,
        selectcolor="#00aa00",
    )
    chk_visible.pack(side=tk.LEFT, padx=5)

    tk.Label(frame, text="Intervalo(seg):").pack(side=tk.LEFT, padx=5)
    entry_interval = tk.Entry(frame, width=5)
    entry_interval.insert(0, str(cfg.scan_interval))
    entry_interval.pack(side=tk.LEFT)
    btn_interval = tk.Button(frame, text="Guardar", command=actualizar_intervalo)
    btn_interval.pack(side=tk.LEFT, padx=5)

    center_window(root)
    root.mainloop()


if __name__ == '__main__':
    main()
