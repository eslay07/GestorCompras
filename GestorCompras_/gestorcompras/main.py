import tkinter as tk
from tkinter import ttk, messagebox
import smtplib
from gestorcompras.services import db
from gestorcompras.gui import config_gui
from gestorcompras.gui import reasignacion_gui
from gestorcompras.gui import despacho_gui

email_session = {}

def test_email_connection(email_address, email_password):
    try:
        with smtplib.SMTP("smtp.telconet.ec", 587) as server:
            server.starttls()
            server.login(email_address, email_password)
        return True
    except Exception:
        return False

def init_styles():
    style = ttk.Style()
    style.theme_use("clam")
    
    # Colores
    bg_base        = "#F5F7FA"
    bg_frame       = "#E9ECF0"
    color_primario = "#2D9CDB"
    color_hover    = "#1B6A8C"
    color_texto    = "#333333"
    color_titulos  = "#222222"
    color_blanco   = "#FFFFFF"
    
    # Fuentes aumentadas
    fuente_normal = ("Helvetica", 14)
    fuente_bold   = ("Helvetica", 16, "bold")
    fuente_banner = ("Helvetica", 24, "bold")
    fuente_entry  = ("Helvetica", 20)
    
    style.configure("MyFrame.TFrame", background=bg_frame)
    style.configure("MyLabel.TLabel", background=bg_frame, foreground=color_texto, font=fuente_normal)
    style.configure("MyButton.TButton", font=fuente_bold, foreground=color_blanco,
                    background=color_primario, padding=10)
    style.map("MyButton.TButton",
              background=[("active", color_hover),
                          ("disabled", "#CCCCCC")])
    style.configure("MyCheckbutton.TCheckbutton", background=bg_frame, foreground=color_texto, font=fuente_normal)
    style.configure("MyEntry.TEntry", font=fuente_entry)
    style.configure("MyNotebook.TNotebook", background=bg_base, borderwidth=0)
    style.configure("MyNotebook.TNotebook.Tab", padding=[12, 8], font=fuente_bold)
    style.map("MyNotebook.TNotebook.Tab",
              background=[("selected", color_primario),
                          ("active", color_hover)],
              foreground=[("selected", color_blanco),
                          ("active", color_blanco)])
    style.configure("MyTreeview.Treeview", background=color_blanco, foreground=color_texto, rowheight=30,
                    fieldbackground="#FAFAFA", font=fuente_normal)
    style.configure("MyTreeview.Treeview.Heading", background=color_primario, foreground=color_blanco, font=fuente_bold)
    style.map("MyTreeview.Treeview.Heading", background=[("active", color_hover)])
    style.configure("MyVertical.TScrollbar", gripcount=0, background=color_primario, troughcolor=bg_frame,
                    bordercolor=bg_frame, arrowcolor=color_blanco)
    style.map("MyVertical.TScrollbar", background=[("active", color_hover)], arrowcolor=[("active", color_blanco)])
    style.configure("MyLabelFrame.TLabelframe", background=bg_frame, relief="groove")
    style.configure("MyLabelFrame.TLabelframe.Label", background=bg_frame, foreground=color_texto, font=fuente_bold)

class LoginScreen(tk.Frame):
    def __init__(self, master, on_success):
        super().__init__(master)
        self.on_success = on_success
        self.create_widgets()
    
    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)
        
        banner = ttk.Label(container, text="Sistema de automatización - compras")
        banner.configure(font=("Helvetica", 24, "bold"), foreground="#222222")
        banner.pack(pady=(20,10))
        
        login_frame = ttk.Frame(container, style="MyFrame.TFrame", padding=20)
        login_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        lbl_title = ttk.Label(login_frame, text="Inicio de Sesión", style="MyLabel.TLabel")
        lbl_title.configure(font=("Helvetica", 18, "bold"), foreground="#222222")
        lbl_title.grid(row=0, column=0, pady=15)
        
        lbl_user = ttk.Label(login_frame, text="Usuario Telcos:", style="MyLabel.TLabel")
        lbl_user.grid(row=1, column=0, sticky="w", pady=(5,0))
        
        self.user_entry = ttk.Entry(login_frame, style="MyEntry.TEntry")
        self.user_entry.grid(row=2, column=0, pady=5)
        self.user_entry.config(font=("Helvetica", 16))
        
        lbl_pass = ttk.Label(login_frame, text="Contraseña:", style="MyLabel.TLabel")
        lbl_pass.grid(row=3, column=0, sticky="w", pady=(5,0))
        
        self.pass_entry = ttk.Entry(login_frame, show="*", style="MyEntry.TEntry")
        self.pass_entry.grid(row=4, column=0, pady=5)
        self.pass_entry.config(font=("Helvetica", 16))
        self.pass_entry.bind("<Return>", lambda event: self.attempt_login())
        
        btn_login = ttk.Button(login_frame, text="Iniciar Sesión", style="MyButton.TButton", command=self.attempt_login)
        btn_login.grid(row=5, column=0, pady=15)
    
    def attempt_login(self):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Debe ingresar usuario y contraseña.")
            return
        email_address = username + "@telconet.ec"
        if test_email_connection(email_address, password):
            email_session["address"] = email_address
            email_session["password"] = password
            messagebox.showinfo("Éxito", "Inicio de sesión correcto.")
            self.on_success()
        else:
            messagebox.showerror("Error", "Usuario o contraseña incorrectos.")

class MainMenu(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.create_widgets()
    
    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)
        
        banner = ttk.Label(container, text="Sistema de automatización - compras")
        banner.configure(font=("Helvetica", 24, "bold"), foreground="#222222")
        banner.pack(pady=(20,10))
        
        menu_frame = ttk.Frame(container, style="MyFrame.TFrame", padding=20)
        menu_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        lbl_title = ttk.Label(menu_frame, text="Menú Principal", style="MyLabel.TLabel")
        lbl_title.configure(font=("Helvetica", 18, "bold"), foreground="#222222")
        lbl_title.grid(row=0, column=0, pady=15, sticky="n")
        
        # Lista de botones
        buttons = [
            ("Reasignación de Tareas", self.open_reasignacion),
            ("Solicitud de Despachos", self.open_despacho),
            ("Cotizador", self.open_cotizador),
            ("Configuración", self.open_config),
            ("Salir", self.master.quit)
        ]
        for idx, (text, cmd) in enumerate(buttons, start=1):
            btn = ttk.Button(menu_frame, text=text, style="MyButton.TButton", command=cmd)
            btn.grid(row=idx, column=0, padx=20, pady=5, sticky="ew")
    
    def open_reasignacion(self):
        reasignacion_gui.open_reasignacion(self.master, email_session)
    
    def open_despacho(self):
        despacho_gui.open_despacho(self.master, email_session)
    
    def open_config(self):
        config_gui.open_config_gui(self.master)
    
    def open_cotizador(self):
        messagebox.showinfo("Cotizador", "Esta opción se encuentra en desarrollo")

def main():
    db.init_db()
    root = tk.Tk()
    root.title("Sistema de Automatización")
    root.geometry("700x550")
    
    init_styles()
    
    def on_main_close():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                messagebox.showwarning("Aviso", "No puede cerrar la ventana principal mientras existan ventanas abiertas.")
                return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_main_close)
    
    container = tk.Frame(root)
    container.pack(fill="both", expand=True)
    
    def show_main_menu():
        for widget in container.winfo_children():
            widget.destroy()
        MainMenu(container).pack(fill="both", expand=True)
    
    LoginScreen(container, on_success=show_main_menu).pack(fill="both", expand=True)
    
    root.mainloop()

if __name__ == "__main__":
    main()
