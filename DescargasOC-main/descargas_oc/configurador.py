import os
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


def configurar():
    cfg = Config()

    def seleccionar_carpeta(entry):
        carpeta = filedialog.askdirectory()
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
        })
        try:
            cfg.validate()
            archivo = filedialog.askopenfilename(title='Archivo de prueba')
            if not archivo:
                messagebox.showwarning('Prueba', 'Debes seleccionar un archivo de prueba')
                return
            cli = SeafileClient(cfg.seafile_url, cfg.usuario, cfg.password)
            cli.upload_file(cfg.seafile_repo_id, archivo, parent_dir=cfg.seafile_subfolder)
            messagebox.showinfo('OK', 'Archivo subido correctamente')
            cfg.save()
            ventana.destroy()
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def generar_procesados():
        messagebox.showinfo('Espere', 'Esto puede demorar. Escaneando correos...')
        try:
            conn = poplib.POP3_SSL(entry_pop_server.get(), int(entry_pop_port.get() or 995))
            conn.user(entry_usuario.get())
            conn.pass_(entry_password.get())
            count = len(conn.list()[1])
            with open(PROCESADOS_FILE, 'w') as f:
                for i in range(count):
                    uidl = conn.uidl(i + 1).decode().split()[2]
                    f.write(uidl + '\n')
            conn.quit()
            messagebox.showinfo('OK', 'Archivo creado correctamente')
            lbl_estado.config(text='Generado')
        except Exception as e:
            messagebox.showerror('Error', str(e))

    ventana = tk.Tk()
    ventana.title('Configuración')
    ventana.lift()
    ventana.attributes('-topmost', True)

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

    tk.Label(ventana, text='Carpeta destino local:').pack()
    entry_destino = tk.Entry(ventana, width=50)
    entry_destino.pack()
    entry_destino.insert(0, cfg.carpeta_destino_local or '')
    tk.Button(ventana, text='Seleccionar', command=lambda: seleccionar_carpeta(entry_destino)).pack()

    tk.Label(ventana, text='Carpeta a analizar:').pack()
    entry_analizar = tk.Entry(ventana, width=50)
    entry_analizar.pack()
    entry_analizar.insert(0, cfg.carpeta_analizar or '')
    tk.Button(ventana, text='Seleccionar', command=lambda: seleccionar_carpeta(entry_analizar)).pack()

    tk.Label(ventana, text='Seafile URL:').pack()
    entry_url = tk.Entry(ventana, width=50)
    entry_url.pack()
    entry_url.insert(0, cfg.seafile_url or '')

    tk.Label(ventana, text='Seafile Repo ID:').pack()
    entry_repo = tk.Entry(ventana, width=50)
    entry_repo.pack()
    entry_repo.insert(0, cfg.seafile_repo_id or '')

    tk.Label(ventana, text='Seafile Subfolder:').pack()
    entry_sub = tk.Entry(ventana, width=50)
    entry_sub.pack()
    entry_sub.insert(0, cfg.seafile_subfolder or '/')

    tk.Label(ventana, text='Correo para reporte:').pack()
    entry_correo = tk.Entry(ventana, width=50)
    entry_correo.pack()
    entry_correo.insert(0, cfg.correo_reporte or '')

    estado_txt = 'Generado' if os.path.exists(PROCESADOS_FILE) else 'Pendiente'
    frame_proc = tk.Frame(ventana)
    frame_proc.pack(pady=5)
    tk.Button(frame_proc, text='Generar procesados', command=generar_procesados).pack(side=tk.LEFT)
    lbl_estado = tk.Label(frame_proc, text=estado_txt)
    lbl_estado.pack(side=tk.LEFT, padx=5)

    tk.Button(ventana, text='Guardar', command=guardar).pack(pady=10)

    ventana.mainloop()

if __name__ == '__main__':
    configurar()

