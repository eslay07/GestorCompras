import tkinter as tk
from tkinter import ttk, messagebox
import smtplib
import subprocess
import sys
from pathlib import Path
from gestorcompras.services import db
from gestorcompras.gui import config_gui
from gestorcompras.gui import reasignacion_gui
from gestorcompras.gui import despacho_gui
from gestorcompras.gui import seguimientos_gui
from gestorcompras.gui.status_bar import ResourceStatusBar
from gestorcompras import theme

# Palette (imported from theme for a cohesive modern look)
bg_base = theme.bg_base
bg_frame = theme.bg_frame
color_primario = theme.color_primario
color_hover = theme.color_hover
color_acento = theme.color_acento
color_texto = theme.color_texto
color_titulos = theme.color_titulos
color_borde = theme.color_borde

# Fonts
fuente_normal = ("Segoe UI", 11)
fuente_bold = ("Segoe UI", 11, "bold")
fuente_banner = ("Segoe UI", 20, "bold")
fuente_entry = ("Segoe UI", 14)

email_session = {}


def _find_descargas_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "DescargasOC-main"
        if candidate.exists():
            return candidate
    return None


_DESCARGAS_ROOT = _find_descargas_root()


def center_window(win: tk.Tk | tk.Toplevel):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.configure(bg=bg_base)

def test_email_connection(email_address, email_password):
    try:
        with smtplib.SMTP("smtp.telconet.ec", 587) as server:
            server.starttls()
            server.login(email_address, email_password)
        return True
    except Exception:
        return False


def add_hover_effect(btn: ttk.Button):
    """Simple zoom-like hover animation for buttons."""

    def on_enter(_):
        btn.configure(style="MyButtonHover.TButton")

    def on_leave(_):
        btn.configure(style="MyButton.TButton")

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

def init_styles():
    style = ttk.Style()
    style.theme_use("clam")
    
    style.configure("MyFrame.TFrame", background=bg_frame, relief="groove", borderwidth=1)
    style.configure("MyLabel.TLabel", background=bg_frame, foreground=color_texto, font=fuente_normal)
    style.map(
        "MyLabel.TLabel",
        background=[("active", bg_frame)],
        foreground=[("active", color_texto)],
    )
    style.configure(
        "MyButton.TButton",
        font=fuente_bold,
        foreground=color_texto,
        background=color_primario,
        padding=10,
        relief="raised",
        borderwidth=1,
    )
    style.configure(
        "MyButtonHover.TButton",
        font=fuente_bold,
        foreground=color_texto,
        background=color_hover,
        padding=12,
        relief="raised",
        borderwidth=1,
    )
    style.map(
        "MyButton.TButton",
        background=[("active", color_hover), ("disabled", color_borde)],
    )
    style.configure("MyCheckbutton.TCheckbutton", background=bg_frame, foreground=color_texto, font=fuente_normal)
    style.configure(
        "MyEntry.TEntry",
        font=fuente_entry,
        padding=5,
        relief="solid",
        borderwidth=1,
        foreground=color_texto,
        fieldbackground=bg_base,
        background=bg_base,
        insertcolor=color_texto,
    )
    style.configure(
        "TCombobox",
        foreground=color_texto,
        fieldbackground=bg_base,
        background=bg_base,
        arrowcolor=color_texto,
    )
    style.configure("MyNotebook.TNotebook", background=bg_base, borderwidth=0)
    style.configure("MyNotebook.TNotebook.Tab", padding=[12, 8], font=fuente_bold)
    style.map("MyNotebook.TNotebook.Tab",
              background=[("selected", color_primario),
                          ("active", color_hover)],
              foreground=[("selected", color_texto),
                          ("active", color_texto)])
    style.configure(
        "MyTreeview.Treeview",
        background=bg_frame,
        foreground=color_texto,
        rowheight=28,
        fieldbackground=bg_frame,
        font=fuente_normal,
    )
    style.configure("MyTreeview.Treeview.Heading", background=color_primario, foreground=color_titulos, font=fuente_bold)
    style.map("MyTreeview.Treeview.Heading", background=[("active", color_hover)])
    style.configure("MyVertical.TScrollbar", gripcount=0, background=color_primario, troughcolor=bg_frame,
                    bordercolor=bg_frame, arrowcolor=color_texto)
    style.map("MyVertical.TScrollbar", background=[("active", color_hover)], arrowcolor=[("active", color_texto)])
    style.configure("MyLabelFrame.TLabelframe", background=bg_frame, relief="groove")
    style.configure("MyLabelFrame.TLabelframe.Label", background=bg_frame, foreground=color_texto, font=fuente_bold)
    style.configure("Banner.TLabel", background=bg_frame, foreground=color_titulos, font=fuente_banner)

class LoginScreen(tk.Frame):
    def __init__(self, master, on_success):
        super().__init__(master)
        self.on_success = on_success
        self._banner_text = "COMPRAS TELCONET S.A"
        self._banner_index = 0
        self._banner_colors = [color_primario, color_acento]
        self._color_index = 0
        self.create_widgets()
        self.animate_banner()
    
    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)

        self.banner = ttk.Label(container, text="", style="Banner.TLabel")
        self.banner.pack(pady=(20,10))
        
        login_frame = ttk.Frame(container, style="MyFrame.TFrame", padding=20)
        login_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        lbl_title = ttk.Label(login_frame, text="Inicio de Sesión", style="MyLabel.TLabel")
        lbl_title.configure(font=fuente_bold, foreground=color_titulos)
        lbl_title.grid(row=0, column=0, pady=15)
        
        lbl_user = ttk.Label(login_frame, text="Usuario Telcos:", style="MyLabel.TLabel")
        lbl_user.grid(row=1, column=0, sticky="w", pady=(5,0))
        
        self.user_entry = ttk.Entry(login_frame, style="MyEntry.TEntry")
        self.user_entry.grid(row=2, column=0, pady=5)
        self.user_entry.config(font=fuente_entry)
        
        lbl_pass = ttk.Label(login_frame, text="Contraseña:", style="MyLabel.TLabel")
        lbl_pass.grid(row=3, column=0, sticky="w", pady=(5,0))
        
        self.pass_entry = ttk.Entry(login_frame, show="*", style="MyEntry.TEntry")
        self.pass_entry.grid(row=4, column=0, pady=5)
        self.pass_entry.config(font=fuente_entry)
        self.pass_entry.bind("<Return>", lambda event: self.attempt_login())

        btn_login = ttk.Button(login_frame, text="Iniciar Sesión", style="MyButton.TButton", command=self.attempt_login)
        btn_login.grid(row=5, column=0, pady=15)
        add_hover_effect(btn_login)

    def animate_banner(self):
        text = self._banner_text[:self._banner_index]
        color = self._banner_colors[self._color_index]
        self.banner.config(text=text, foreground=color)
        self._banner_index += 1
        if self._banner_index > len(self._banner_text):
            self._banner_index = 0
            self._color_index = (self._color_index + 1) % len(self._banner_colors)
        self.after(150, self.animate_banner)
    
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
        self._banner_colors = [color_primario, color_acento]
        self._color_index = 0
        self._buttons = [
            ("Reasignación de Tareas", self.open_reasignacion),
            ("Solicitud de Despachos", self.open_despacho),
            ("Seguimientos", self.open_seguimientos),
            ("Descargas OC", self.open_descargas_oc),
            ("Cotizador", self.open_cotizador),
            ("Configuración", self.open_config),
            ("Salir", self.master.quit),
        ]
        self._button_widgets: list[ttk.Button] = []
        self.create_widgets()
    
    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)
        
        self.banner = ttk.Label(container, text="Sistema de automatización - compras")
        self.banner.configure(font=fuente_banner, foreground=color_titulos)
        self.banner.pack(pady=(20,10))
        self.animate_banner()
        
        menu_frame = ttk.Frame(container, style="MyFrame.TFrame", padding=20)
        menu_frame.pack(pady=20)
        menu_frame.columnconfigure(0, weight=1)
        
        lbl_title = ttk.Label(menu_frame, text="Menú Principal", style="MyLabel.TLabel")
        lbl_title.configure(font=fuente_bold, foreground=color_titulos)
        lbl_title.grid(row=0, column=0, pady=15, sticky="n")
        
        self.menu_frame = menu_frame
        self.show_button(0)

    def animate_banner(self):
        color = self._banner_colors[self._color_index]
        self.banner.configure(foreground=color)
        self._color_index = (self._color_index + 1) % len(self._banner_colors)
        self.after(800, self.animate_banner)

    def show_button(self, index: int):
        if index >= len(self._buttons):
            return
        text, cmd = self._buttons[index]
        btn = ttk.Button(self.menu_frame, text=text, style="MyButton.TButton", command=cmd)
        btn.grid(row=index + 1, column=0, padx=20, pady=5, sticky="ew")
        add_hover_effect(btn)
        self._button_widgets.append(btn)
        self.after(120, self.show_button, index + 1)
    
    def open_reasignacion(self):
        reasignacion_gui.open_reasignacion(self.master, email_session)
    
    def open_despacho(self):
        despacho_gui.open_despacho(self.master, email_session)

    def open_seguimientos(self):
        seguimientos_gui.open_seguimientos(self.master, email_session)

    def open_descargas_oc(self):
        def launch_normal():
            if _DESCARGAS_ROOT is None:
                messagebox.showerror(
                    "Descargas OC",
                    "No se encontró la carpeta 'DescargasOC-main'.",
                )
                return
            script = _DESCARGAS_ROOT / "descargas_oc" / "ui.py"
            subprocess.Popen([sys.executable, str(script)])
            option_win.destroy()

        def open_abastecimiento():
#<<<<<<< codex/fix-email-scanning-for-descarga-normal-z71yhw
            if _DESCARGAS_ROOT is None:
                messagebox.showerror(
                    "Descargas OC",
                    "No se encontró la carpeta 'DescargasOC-main'.",
                )
                return
            script = _DESCARGAS_ROOT / "descargas_oc" / "ui_abastecimiento.py"
            try:
                subprocess.Popen([sys.executable, str(script)])
            except OSError as exc:
                messagebox.showerror(
                    "Error",
                    (
                        "No se pudo abrir el módulo de Abastecimiento. "
                        f"Detalle: {exc}"
                    ),
                )
                return
#=======
            script = (
                Path(__file__).resolve().parents[2]
                / "DescargasOC-main"
                / "descargas_oc"
                / "ui_abastecimiento.py"
            )
            subprocess.Popen([sys.executable, str(script)])
#>>>>>>> master
            option_win.destroy()

        option_win = tk.Toplevel(self.master)
        option_win.title("Descargas OC")
        option_win.transient(self.master)
        option_win.grab_set()
        center_window(option_win)

        ttk.Label(
            option_win,
            text="Seleccione el tipo de descarga:",
            style="MyLabel.TLabel",
        ).pack(padx=10, pady=10)
        btn_norm = ttk.Button(
            option_win,
            text="Descarga Normal",
            style="MyButton.TButton",
            command=launch_normal,
        )
        btn_norm.pack(padx=10, pady=5)
        add_hover_effect(btn_norm)
        btn_abast = ttk.Button(
            option_win,
            text="Abastecimiento",
            style="MyButton.TButton",
            command=open_abastecimiento,
        )
        btn_abast.pack(padx=10, pady=5)
        add_hover_effect(btn_abast)

    def open_config(self):
        config_gui.open_config_gui(self.master, email_session)
    
    def open_cotizador(self):
        messagebox.showinfo("Cotizador", "Esta opción se encuentra en desarrollo")

def main():
    db.init_db()
    root = tk.Tk()
    root.title("Sistema de Automatización")
    root.geometry("800x600")
    root.tk_setPalette(
        background=bg_base,
        foreground=color_texto,
        activeBackground=color_hover,
        activeForeground=color_texto,
        highlightColor=color_borde,
    )
    center_window(root)
    
    init_styles()
    
    def on_main_close():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                messagebox.showwarning("Aviso", "No puede cerrar la ventana principal mientras existan ventanas abiertas.")
                return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_main_close)
    
    container = ttk.Frame(root, style="MyFrame.TFrame")
    container.pack(fill="both", expand=True)

    status_bar = ResourceStatusBar(root)
    status_bar.pack(side="bottom", fill="x")
    
    def show_main_menu():
        for widget in container.winfo_children():
            widget.destroy()
        MainMenu(container).pack(fill="both", expand=True)
    
    LoginScreen(container, on_success=show_main_menu).pack(fill="both", expand=True)
    
    root.mainloop()

if __name__ == "__main__":
    main()
