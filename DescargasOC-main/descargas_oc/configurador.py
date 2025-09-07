import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import poplib

try:  # allow running as script
    from .config import Config
    from .seafile_client import SeafileClient
    from .escuchador import PROCESADOS_FILE
except ImportError:  # pragma: no cover
    from config import Config
    from seafile_client import SeafileClient
from escuchador import PROCESADOS_FILE


class ToolTip:
    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, event=None):  # pragma: no cover - UI helper
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 1
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal"),
        )
        label.pack(ipadx=1)

    def hide(self, event=None):  # pragma: no cover - UI helper
        tw = self.tip
        self.tip = None
        if tw:
            tw.destroy()


def add_tooltip(widget: tk.Widget, text: str) -> None:
    ToolTip(widget, text)


def configurar():
    cfg = Config()

    def center_window(win: tk.Tk | tk.Toplevel):
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        x = (win.winfo_screenwidth() // 2) - (w // 2)
        y = (win.winfo_screenheight() // 2) - (h // 2)
        win.geometry(f"{w}x{h}+{x}+{y}")

    def seleccionar_carpeta(entry):
        carpeta = filedialog.askdirectory(initialdir=entry.get() or os.getcwd())
        if carpeta:
            entry.delete(0, tk.END)
            entry.insert(0, carpeta)

    def guardar():
        cfg.data.update({
            'usuario': entry_usuario.get(),
            'password': entry_password.get(),
            'pop_server': entry_pop_server.get(),
            'pop_port': int(entry_pop_port.get() or 995),
            'carpeta_destino_local': entry_destino.get(),
            'carpeta_analizar': entry_analizar.get(),
            'seafile_url': entry_url.get(),
            'seafile_repo_id': entry_repo.get(),
            'seafile_subfolder': entry_sub.get(),
            'correo_reporte': entry_correo.get(),
            'remitente_adicional': entry_remitente.get(),
            'headless': var_headless.get(),
        })
        try:
            cfg.validate()
            cfg.save()
            archivo = filedialog.askopenfilename(title='Archivo de prueba')
            if not archivo:
                messagebox.showwarning('Prueba', 'Debes seleccionar un archivo de prueba')
                return
            cli = SeafileClient(cfg.seafile_url, cfg.usuario, cfg.password)
            cli.upload_file(cfg.seafile_repo_id, archivo, parent_dir=cfg.seafile_subfolder)
            messagebox.showinfo('OK', 'Archivo subido correctamente')
            try:
                ventana.grab_release()
            except Exception:  # pragma: no cover - grab may not be set
                pass
            ventana.destroy()
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def generar_procesados():
        btn_gen_proc.config(state=tk.DISABLED)
        popup = tk.Toplevel(ventana)
        popup.transient(ventana)
        popup.grab_set()
        lbl_msg = tk.Label(popup, text='Esto puede demorar. Escaneando correos...')
        lbl_msg.pack(padx=20, pady=10)
        btn_ok = tk.Button(
            popup, text='Aceptar', state=tk.DISABLED,
            command=lambda: (popup.grab_release(), popup.destroy())
        )
        btn_ok.pack(pady=(0, 10))
        center_window(popup)

        def tarea():
            try:
                conn = poplib.POP3_SSL(
                    entry_pop_server.get(), int(entry_pop_port.get() or 995)
                )
                conn.user(entry_usuario.get())
                conn.pass_(entry_password.get())
                count = len(conn.list()[1])
                with open(PROCESADOS_FILE, 'w') as f:
                    for i in range(count):
                        uidl = conn.uidl(i + 1).decode().split()[2]
                        f.write(uidl + '\n')
                conn.quit()
                estado, msg = 'Generado', 'Archivo creado correctamente'
            except Exception as e:  # pragma: no cover - network errors
                estado, msg = lbl_estado.cget('text'), f'Error: {e}'

            def finalizar():
                lbl_estado.config(text=estado)
                lbl_msg.config(text=msg)
                btn_ok.config(state=tk.NORMAL)
                btn_gen_proc.config(state=tk.NORMAL)

            popup.after(0, finalizar)

        threading.Thread(target=tarea, daemon=True).start()

    parent = tk._get_default_root()
    if parent is None:
        ventana = tk.Tk()
    else:
        ventana = tk.Toplevel(parent)
        ventana.transient(parent)
        ventana.grab_set()
    ventana.title('Configuración')
    ventana.geometry('600x700')

    tk.Label(ventana, text='Servidor POP3:').pack()
    entry_pop_server = tk.Entry(ventana, width=50)
    entry_pop_server.pack()
    entry_pop_server.insert(0, cfg.pop_server or '')

    tk.Label(ventana, text='Puerto POP3:').pack()
    entry_pop_port = tk.Entry(ventana, width=10)
    entry_pop_port.pack()
    entry_pop_port.insert(0, str(cfg.pop_port or 995))

    tk.Label(ventana, text='Usuario:').pack()
    entry_usuario = tk.Entry(ventana)
    entry_usuario.pack()
    entry_usuario.insert(0, cfg.usuario or '')

    tk.Label(ventana, text='Contraseña:').pack()
    entry_password = tk.Entry(ventana, show='*')
    entry_password.pack()
    entry_password.insert(0, cfg.password or '')

    lbl_destino = tk.Label(ventana, text='Carpeta de descarga principal:')
    lbl_destino.pack()
    add_tooltip(
        lbl_destino,
        'Esta carpeta es la ubicacion de destino de las ordenes de compra que se descargaran directamente del naf web',
    )
    entry_destino = tk.Entry(ventana, width=50)
    entry_destino.pack()
    entry_destino.insert(0, cfg.carpeta_destino_local or '')
    tk.Button(ventana, text='Seleccionar', command=lambda: seleccionar_carpeta(entry_destino)).pack()

    lbl_analizar = tk.Label(ventana, text='Carpeta de tareas Bienes:')
    lbl_analizar.pack()
    add_tooltip(
        lbl_analizar,
        'Esta carpeta es en donde el programa buscara una carpeta con el numero de tarea similar al que tiene la orden de compra y a donde se movera dicho archivo, esta configuracion es para compras bienes, si usted es de servicios, coloque cualquier ubicacion del seadrive.',
    )
    entry_analizar = tk.Entry(ventana, width=50)
    entry_analizar.pack()
    entry_analizar.insert(0, cfg.carpeta_analizar or '')
    tk.Button(ventana, text='Seleccionar', command=lambda: seleccionar_carpeta(entry_analizar)).pack()

    lbl_url = tk.Label(ventana, text='URL principal de Telcodrive:')
    lbl_url.pack()
    add_tooltip(
        lbl_url,
        'aqui va el enlace principal de telcodrive, ejemplo: https://telcodrive.telconet.net/',
    )
    entry_url = tk.Entry(ventana, width=50)
    entry_url.pack()
    entry_url.insert(0, cfg.seafile_url or '')

    lbl_repo = tk.Label(ventana, text='ID de la carpeta principal:')
    lbl_repo.pack()
    add_tooltip(
        lbl_repo,
        'este id es un codigo que se encuentra en la url de su carpeta personal en telcodrive entre https://telcodrive.telconet.net/library/   y /nombre de la carpeta principal/nombre de la subcarpeta  y su formato es similar a este ede837d2-5de8-45f8-802d-aa513aaad8b2',
    )
    entry_repo = tk.Entry(ventana, width=50)
    entry_repo.pack()
    entry_repo.insert(0, cfg.seafile_repo_id or '')

    lbl_sub = tk.Label(ventana, text='Carpeta Personal Telcodrive:')
    lbl_sub.pack()
    add_tooltip(
        lbl_sub,
        'esta carpeta no es la carpeta compartida es una carpeta personal creada en telcodrive a donde siempre se subiran ordenes de compra como un respaldo principal',
    )
    entry_sub = tk.Entry(ventana, width=50)
    entry_sub.pack()
    entry_sub.insert(0, cfg.seafile_subfolder or '/')

    tk.Label(ventana, text='Correo para reporte:').pack()
    entry_correo = tk.Entry(ventana, width=50)
    entry_correo.pack()
    entry_correo.insert(0, cfg.correo_reporte or '')

    tk.Label(ventana, text='Remitente principal de órdenes autorizadas:').pack()
    entry_remitente = tk.Entry(ventana, width=50)
    entry_remitente.pack()
    entry_remitente.insert(0, cfg.remitente_adicional or '')

    var_headless = tk.BooleanVar(value=bool(cfg.headless))
    txt_headless = tk.StringVar()

    def _actualizar_headless(*_):  # pragma: no cover - UI binding
        txt_headless.set(
            'Descarga invisible' if var_headless.get() else 'Descarga visible'
        )

    _actualizar_headless()
    var_headless.trace_add('write', _actualizar_headless)
    chk_headless = tk.Checkbutton(
        ventana,
        textvariable=txt_headless,
        variable=var_headless,
    )
    chk_headless.pack(pady=5)

    estado_txt = 'Generado' if os.path.exists(PROCESADOS_FILE) else 'Pendiente'
    frame_proc = tk.Frame(ventana)
    frame_proc.pack(pady=5)
    btn_gen_proc = tk.Button(frame_proc, text='Generar procesados', command=generar_procesados)
    btn_gen_proc.pack(side=tk.LEFT)
    lbl_estado = tk.Label(frame_proc, text=estado_txt)
    lbl_estado.pack(side=tk.LEFT, padx=5)

    tk.Button(ventana, text='Guardar', command=guardar).pack(pady=10)
    center_window(ventana)
    ventana.mainloop()

if __name__ == '__main__':
    configurar()

