"""Punto de entrada principal de la aplicación de escritorio."""
from __future__ import annotations

import smtplib
import tkinter as tk
from tkinter import ttk, messagebox

from gestorcompras.core import config as core_config
from gestorcompras.core.smtp_config import get_smtp_settings
from gestorcompras.gui.status_bar import ResourceStatusBar
from gestorcompras.services import db
from gestorcompras import theme
from gestorcompras.ui import router
from gestorcompras.ui.common import center_window, add_hover_effect

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

email_session: dict[str, str] = {}


def test_email_connection(email_address: str, email_password: str) -> bool:
    try:
        server_host, server_port, starttls = get_smtp_settings()
        with smtplib.SMTP(server_host, server_port) as server:
            if starttls:
                server.starttls()
            server.login(email_address, email_password)
        return True
    except Exception:
        return False


def init_styles() -> None:
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
        foreground=color_titulos,
        background=color_primario,
        padding=10,
        relief="raised",
        borderwidth=1,
    )
    style.configure(
        "MyButtonHover.TButton",
        font=fuente_bold,
        foreground=color_titulos,
        background=color_hover,
        padding=10,
        relief="raised",
        borderwidth=1,
    )
    style.map(
        "MyButton.TButton",
        background=[("active", color_acento), ("disabled", color_borde)],
        foreground=[("active", bg_frame)],
    )
    style.map(
        "MyButtonHover.TButton",
        background=[("active", color_acento)],
        foreground=[("active", color_titulos)],
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
    style.map(
        "MyNotebook.TNotebook.Tab",
        background=[("selected", color_primario), ("active", color_hover)],
        foreground=[("selected", color_texto), ("active", color_texto)],
    )
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
    style.configure(
        "MyVertical.TScrollbar",
        gripcount=0,
        background=color_primario,
        troughcolor=bg_frame,
        bordercolor=bg_frame,
        arrowcolor=color_texto,
    )
    style.map("MyVertical.TScrollbar", background=[("active", color_hover)], arrowcolor=[("active", color_texto)])
    style.configure("MyLabelFrame.TLabelframe", background=bg_frame, relief="groove")
    style.configure("MyLabelFrame.TLabelframe.Label", background=bg_frame, foreground=color_texto, font=fuente_bold)
    style.configure("Banner.TLabel", background=bg_frame, foreground=color_titulos, font=fuente_banner)


class LoginScreen(tk.Frame):
    def __init__(self, master: tk.Misc, on_success):
        super().__init__(master)
        self.on_success = on_success
        self._banner_text = "COMPRAS TELCONET S.A"
        self._banner_index = 0
        self._banner_colors = [color_primario, color_acento]
        self._color_index = 0
        self.create_widgets()
        self.animate_banner()

    def create_widgets(self) -> None:
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)

        self.banner = ttk.Label(container, text="", style="Banner.TLabel")
        self.banner.pack(pady=(20, 10))

        login_frame = ttk.Frame(container, style="MyFrame.TFrame", padding=20)
        login_frame.place(relx=0.5, rely=0.5, anchor="center")

        lbl_title = ttk.Label(login_frame, text="Inicio de Sesión", style="MyLabel.TLabel")
        lbl_title.configure(font=fuente_bold, foreground=color_titulos)
        lbl_title.grid(row=0, column=0, pady=15)

        ttk.Label(login_frame, text="Usuario Telcos:", style="MyLabel.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.user_entry = ttk.Entry(login_frame, style="MyEntry.TEntry")
        self.user_entry.grid(row=2, column=0, pady=5)
        self.user_entry.config(font=fuente_entry)

        ttk.Label(login_frame, text="Contraseña:", style="MyLabel.TLabel").grid(row=3, column=0, sticky="w", pady=(5, 0))
        self.pass_entry = ttk.Entry(login_frame, show="*", style="MyEntry.TEntry")
        self.pass_entry.grid(row=4, column=0, pady=5)
        self.pass_entry.config(font=fuente_entry)
        self.pass_entry.bind("<Return>", lambda event: self.attempt_login())

        btn_login = ttk.Button(login_frame, text="Iniciar Sesión", style="MyButton.TButton", command=self.attempt_login)
        btn_login.grid(row=5, column=0, pady=15)
        add_hover_effect(btn_login)

    def animate_banner(self) -> None:
        text = self._banner_text[: self._banner_index]
        color = self._banner_colors[self._color_index]
        self.banner.config(text=text, foreground=color)
        self._banner_index += 1
        if self._banner_index > len(self._banner_text):
            self._banner_index = 0
            self._color_index = (self._color_index + 1) % len(self._banner_colors)
        self.after(150, self.animate_banner)

    def attempt_login(self) -> None:
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Debe ingresar usuario y contraseña.", parent=self)
            return
        email_address = f"{username}@telconet.ec"
        if test_email_connection(email_address, password):
            email_session["address"] = email_address
            email_session["password"] = password
            core_config.set_user_email(email_address)
            messagebox.showinfo("Éxito", "Inicio de sesión correcto.", parent=self)
            self.on_success()
        else:
            messagebox.showerror("Error", "Usuario o contraseña incorrectos.", parent=self)


def main() -> None:
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
                messagebox.showwarning(
                    "Aviso",
                    "No puede cerrar la ventana principal mientras existan ventanas abiertas.",
                    parent=root,
                )
                return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_main_close)

    container = ttk.Frame(root, style="MyFrame.TFrame")
    container.pack(fill="both", expand=True)

    status_bar = ResourceStatusBar(root)
    status_bar.pack(side="bottom", fill="x")

    def show_home() -> None:
        router.configure(container, email_session)

    LoginScreen(container, on_success=show_home).pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
