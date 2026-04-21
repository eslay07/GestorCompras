"""Punto de entrada principal de la aplicación de escritorio."""
from __future__ import annotations

import smtplib
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from gestorcompras.core import config as core_config
from gestorcompras.services import db
from gestorcompras import theme
from gestorcompras.ui import router
from gestorcompras.ui.common import center_window, add_hover_effect

# Palette (imported from theme)
bg_base = theme.bg_base
bg_frame = theme.bg_frame
color_primario = theme.color_primario
color_hover = theme.color_hover
color_acento = theme.color_acento
color_texto = theme.color_texto
color_titulos = theme.color_titulos
color_borde = theme.color_borde
bg_input = theme.bg_input

# Fonts
fuente_normal = ("Segoe UI", 11)
fuente_bold = ("Segoe UI", 11, "bold")
fuente_banner = ("Segoe UI", 20, "bold")
fuente_entry = ("Segoe UI", 14)

email_session: dict[str, str] = {}


def test_email_connection(email_address: str, email_password: str) -> bool:
    try:
        with smtplib.SMTP("smtp.telconet.ec", 587) as server:
            server.starttls()
            server.login(email_address, email_password)
        return True
    except Exception:
        return False


def init_styles() -> None:
    style = ttk.Style()
    style.theme_use("clam")

    style.configure("MyFrame.TFrame", background=bg_frame, relief="flat", borderwidth=0)
    style.configure("MyLabel.TLabel", background=bg_frame, foreground=color_texto, font=fuente_normal)
    style.map(
        "MyLabel.TLabel",
        background=[("active", bg_frame)],
        foreground=[("active", color_texto)],
    )
    style.configure(
        "MyButton.TButton",
        font=fuente_bold,
        foreground="#FFFFFF",
        background=color_primario,
        padding=12,
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "MyButtonHover.TButton",
        font=fuente_bold,
        foreground="#FFFFFF",
        background=color_hover,
        padding=12,
        relief="flat",
        borderwidth=0,
    )
    style.map(
        "MyButton.TButton",
        background=[("active", color_hover), ("disabled", color_borde)],
        foreground=[("active", "#FFFFFF"), ("disabled", "#9CA3AF")],
    )
    style.map(
        "MyButtonHover.TButton",
        background=[("active", color_hover)],
        foreground=[("active", "#FFFFFF")],
    )
    style.configure("MyCheckbutton.TCheckbutton", background=bg_frame, foreground=color_texto, font=fuente_normal)
    style.configure(
        "MyEntry.TEntry",
        font=fuente_entry,
        padding=6,
        relief="solid",
        borderwidth=1,
        foreground=color_texto,
        fieldbackground=bg_input,
        background=bg_input,
        insertcolor=color_texto,
    )
    style.configure(
        "TCombobox",
        foreground=color_texto,
        fieldbackground=bg_input,
        background=bg_input,
        arrowcolor=color_texto,
    )
    style.configure("MyNotebook.TNotebook", background=bg_base, borderwidth=0)
    style.configure("MyNotebook.TNotebook.Tab", padding=[14, 8], font=fuente_bold)
    style.map(
        "MyNotebook.TNotebook.Tab",
        background=[("selected", color_primario), ("active", color_hover)],
        foreground=[("selected", "#FFFFFF"), ("active", "#FFFFFF")],
    )
    style.configure(
        "MyTreeview.Treeview",
        background="#FFFFFF",
        foreground=color_texto,
        rowheight=30,
        fieldbackground="#FFFFFF",
        font=fuente_normal,
    )
    style.configure(
        "MyTreeview.Treeview.Heading",
        background="#E5E7EB",
        foreground=color_titulos,
        font=fuente_bold,
        relief="flat",
    )
    style.map("MyTreeview.Treeview.Heading", background=[("active", "#D1D5DB")])
    style.configure(
        "MyVertical.TScrollbar",
        gripcount=0,
        background="#D1D5DB",
        troughcolor=bg_base,
        bordercolor=bg_base,
        arrowcolor=color_texto,
    )
    style.map("MyVertical.TScrollbar", background=[("active", "#9CA3AF")], arrowcolor=[("active", color_texto)])
    style.configure("MyLabelFrame.TLabelframe", background=bg_frame, relief="groove", bordercolor=color_borde)
    style.configure("MyLabelFrame.TLabelframe.Label", background=bg_frame, foreground=color_texto, font=fuente_bold)
    style.configure("Banner.TLabel", background=bg_frame, foreground=color_titulos, font=fuente_banner)
    style.configure("WizardStep.TLabel", background=bg_frame, foreground=color_texto, font=fuente_bold)


class LoginScreen(tk.Frame):
    def __init__(self, master: tk.Misc, on_success):
        super().__init__(master, bg=bg_base)
        self.on_success = on_success
        self.create_widgets()

    def create_widgets(self) -> None:
        container = ttk.Frame(self, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)

        banner = ttk.Label(container, text="COMPRAS TELCONET S.A.", style="Banner.TLabel")
        banner.pack(pady=(40, 20))

        card = ttk.Frame(container, style="MyFrame.TFrame", padding=30)
        card.place(relx=0.5, rely=0.5, anchor="center")

        lbl_title = ttk.Label(card, text="Inicio de Sesion", style="MyLabel.TLabel")
        lbl_title.configure(font=fuente_bold, foreground=color_titulos)
        lbl_title.grid(row=0, column=0, pady=(0, 20))

        ttk.Label(card, text="Usuario Telcos:", style="MyLabel.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.user_entry = ttk.Entry(card, style="MyEntry.TEntry", width=30)
        self.user_entry.grid(row=2, column=0, pady=5, sticky="ew")
        self.user_entry.config(font=fuente_entry)

        ttk.Label(card, text="Contrasena:", style="MyLabel.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.pass_entry = ttk.Entry(card, show="*", style="MyEntry.TEntry", width=30)
        self.pass_entry.grid(row=4, column=0, pady=5, sticky="ew")
        self.pass_entry.config(font=fuente_entry)
        self.pass_entry.bind("<Return>", lambda event: self.attempt_login())

        self.btn_login = ttk.Button(card, text="Iniciar Sesion", style="MyButton.TButton", command=self.attempt_login)
        self.btn_login.grid(row=5, column=0, pady=(20, 10), sticky="ew")
        add_hover_effect(self.btn_login)

        self.lbl_status = ttk.Label(card, text="", style="MyLabel.TLabel")
        self.lbl_status.grid(row=6, column=0, pady=(0, 5))

    def attempt_login(self) -> None:
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Error", "Debe ingresar usuario y contrasena.", parent=self)
            return
        email_address = f"{username}@telconet.ec"

        self.btn_login.config(state="disabled")
        self.user_entry.config(state="disabled")
        self.pass_entry.config(state="disabled")
        self.lbl_status.config(text="Conectando...")

        def _do_login():
            success = test_email_connection(email_address, password)
            self.after(0, lambda: self._on_login_result(success, email_address, password))

        threading.Thread(target=_do_login, daemon=True).start()

    def _on_login_result(self, success: bool, email_address: str, password: str) -> None:
        try:
            self.btn_login.config(state="normal")
            self.user_entry.config(state="normal")
            self.pass_entry.config(state="normal")
            self.lbl_status.config(text="")
        except tk.TclError:
            return

        if success:
            email_session["address"] = email_address
            email_session["password"] = password
            core_config.set_user_email(email_address)
            messagebox.showinfo("Bienvenido", "Inicio de sesion correcto.", parent=self)
            self.on_success()
        else:
            messagebox.showerror("Error", "Usuario o contrasena incorrectos.", parent=self)


def main() -> None:
    root = tk.Tk()
    root.title("Gestor Compras - Telconet")
    root.geometry("1100x700")
    root.tk_setPalette(
        background=bg_base,
        foreground=color_texto,
        activeBackground=color_hover,
        activeForeground="#FFFFFF",
        highlightColor=color_borde,
    )
    center_window(root)

    init_styles()

    def on_main_close():
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                messagebox.showwarning(
                    "Aviso",
                    "Cierre las ventanas abiertas antes de cerrar la aplicacion.",
                    parent=root,
                )
                return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_main_close)

    login_container = ttk.Frame(root, style="MyFrame.TFrame")
    login_container.pack(fill="both", expand=True)

    def show_main_layout() -> None:
        login_container.destroy()

        from gestorcompras.ui.sidebar import Sidebar

        sidebar = Sidebar(root, email_session, on_navigate=_on_sidebar_navigate)
        sidebar.pack(side="left", fill="y")

        content = ttk.Frame(root, style="MyFrame.TFrame")
        content.pack(side="left", fill="both", expand=True)

        router.configure(content, email_session, sidebar=sidebar)
        router.show_welcome()

    def _on_sidebar_navigate(module_id: str) -> None:
        router.open_module(module_id)

    LoginScreen(login_container, on_success=show_main_layout).pack(fill="both", expand=True)

    root.mainloop()


if __name__ == "__main__":
    main()
