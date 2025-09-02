import tkinter as tk
import threading
import logging
from datetime import datetime

try:  # allow running as script
    from .configurador import configurar
    from .escuchador import buscar_ocs, cargar_ultimo_uidl
    from .selenium_modulo import descargar_oc
    from .reporter import enviar_reporte
    from .config import Config
    from .logger import get_logger
except ImportError:  # pragma: no cover
    from configurador import configurar
    from escuchador import buscar_ocs, cargar_ultimo_uidl
    from selenium_modulo import descargar_oc
    from reporter import enviar_reporte
    from config import Config
    from logger import get_logger

logger = get_logger(__name__)

scanning_lock = threading.Lock()


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

        def append(msg: str):
            text_widget.after(0, lambda m=msg: (text_widget.insert(tk.END, m), text_widget.see(tk.END)))

        append("Buscando órdenes...\n")
        ordenes = buscar_ocs(cfg)
        exitosas: list[str] = []
        faltantes: list[str] = []
        for oc in ordenes:
            append(f"Procesando OC {oc['numero']}\n")
            subidos, no_encontrados = descargar_oc(oc['numero'], oc['fecha_aut'], oc['fecha_orden'])
            exitosas.extend(subidos)
            faltantes.extend(no_encontrados)
            append(f"✔️ OC {oc['numero']} procesada\n")
        enviar_reporte(exitosas, faltantes, cfg)
        append("Proceso finalizado\n")
        lbl_last.config(
            text=f"Último UIDL: {cargar_ultimo_uidl()} - {datetime.now:%H:%M:%S}"
        )
    finally:
        scanning_lock.release()


def main():
    root = tk.Tk()
    root.title("Descargas OC")
    root.lift()
    root.attributes('-topmost', True)

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10)

    text = tk.Text(frame, width=80, height=20)
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
            estado["activo"] = True
            estado["contador"] = cfg.scan_interval
            btn_toggle.config(text="Detener escuchador")
            actualizar_contador()

    def escanear_ahora():
        estado["contador"] = cfg.scan_interval
        threading.Thread(target=realizar_escaneo, args=(text, lbl_last), daemon=True).start()

    def actualizar_intervalo():
        try:
            val = int(entry_interval.get())
            if val >= 300:
                cfg.data['scan_interval'] = val
                cfg.save()
                estado['contador'] = val
        except ValueError:
            pass

    btn_toggle = tk.Button(frame, text="Activar escuchador", command=toggle)
    btn_toggle.pack(side=tk.LEFT, padx=5)

    btn_escanear = tk.Button(frame, text="Escanear ahora", command=escanear_ahora)
    btn_escanear.pack(side=tk.LEFT, padx=5)

    btn_config = tk.Button(frame, text="Configuración", command=configurar)
    btn_config.pack(side=tk.LEFT, padx=5)

    tk.Label(frame, text="Intervalo(seg):").pack(side=tk.LEFT, padx=5)
    entry_interval = tk.Entry(frame, width=5)
    entry_interval.insert(0, str(cfg.scan_interval))
    entry_interval.pack(side=tk.LEFT)
    btn_interval = tk.Button(frame, text="Guardar", command=actualizar_intervalo)
    btn_interval.pack(side=tk.LEFT, padx=5)

    root.mainloop()


if __name__ == '__main__':
    main()
