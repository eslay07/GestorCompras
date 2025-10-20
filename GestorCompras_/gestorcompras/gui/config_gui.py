import tkinter as tk
import os
import tkinter.font as tkFont
import re
import threading
import poplib
import sys
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog, filedialog
from html import escape

# Claves compartidas con los módulos de reasignación
SERVICIOS_DEPARTAMENTO_KEY = "SERVICIOS_DEPARTAMENTO"
SERVICIOS_USUARIO_KEY = "SERVICIOS_USUARIO"
SERVICIOS_MENSAJE_KEY = "SERVICIOS_REASIGNACION_MSG"

# Garantiza que el paquete descargas_oc esté disponible incluso cuando la
# aplicación se ejecute desde el directorio GestorCompras_. Buscamos la carpeta
# "DescargasOC-main" ascendiendo en el árbol de directorios para soportar
# distribuciones donde ambos módulos viven como carpetas hermanas.
def _find_descargas_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "DescargasOC-main"
        if candidate.exists():
            return candidate
    return None


_DESCARGAS_ROOT = _find_descargas_root()
if _DESCARGAS_ROOT is not None:
    _path = str(_DESCARGAS_ROOT)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from gestorcompras.services import db
from gestorcompras.gui.html_editor import HtmlEditor
from gestorcompras.services.email_sender import send_email_custom
from descargas_oc.config import Config as DescargasConfig
from descargas_oc.escuchador import PROCESADOS_FILE


def _format_ruc(value: str | int) -> str:
    """Devuelve el RUC como cadena preservando ceros a la izquierda."""
    if isinstance(value, int):
        value = str(value)
    elif not isinstance(value, str):
        value = str(value)
    digits = value.strip()
    if digits.isdigit():
        if digits.startswith("0"):
            return digits
        if len(digits) == 12:
            return digits.zfill(13)
    return value

def center_window(win: tk.Tk | tk.Toplevel):
    win.update_idletasks()
    w = win.winfo_width()
    h = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (w // 2)
    y = (win.winfo_screenheight() // 2) - (h // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")

class ConfigGUI(tk.Toplevel):
    def __init__(self, master=None, email_session=None):
        super().__init__(master)
        # Ensure the database has all required tables even if this
        # window is launched directly without going through main()
        db.init_db()
        self.title("Configuración")
        self.geometry("800x600")
        self.email_session = email_session
        self.descargas_cfg = DescargasConfig()
        self._oc_entries: dict[str, tk.Widget] = {}
        self._oc_vars: dict[str, tk.Variable] = {}
        self._procesados_status = tk.StringVar(value="Generado" if PROCESADOS_FILE.exists() else "Pendiente")
        self._procesados_button: ttk.Button | None = None
        self._abastecimiento_focus: tk.Widget | None = None
        self._oc_focus: tk.Widget | None = None
        self._oc_canvas: tk.Canvas | None = None
        self._oc_scrollable: tk.Widget | None = None
        self.create_widgets()
        center_window(self)

    def create_widgets(self):
        self.notebook = ttk.Notebook(self, style="MyNotebook.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.suppliers_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.assign_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.tracking_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.dispatch_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.oc_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.email_templates_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)

        self.notebook.add(self.suppliers_frame, text="Proveedores")
        self.notebook.add(self.assign_frame, text="Asignación")
        self.notebook.add(self.tracking_frame, text="Seguimientos")
        self.notebook.add(self.dispatch_frame, text="Despacho")
        self.notebook.add(self.oc_frame, text="Descargas OC")
        self.notebook.add(self.email_templates_frame, text="Formatos de Correo")

        self.create_suppliers_tab()
        self.create_assignment_tab()
        self.create_tracking_tab()
        self.create_dispatch_tab()
        self.create_oc_tab()
        self.create_email_templates_tab()
    
    def create_suppliers_tab(self):
        search_frame = ttk.Frame(self.suppliers_frame, style="MyFrame.TFrame")
        search_frame.pack(fill="x", pady=(0,5))
        ttk.Label(search_frame, text="Buscar:", style="MyLabel.TLabel").pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, style="MyEntry.TEntry")
        search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_var.trace_add("write", lambda *args: self.filter_suppliers())
        ttk.Button(search_frame, text="Limpiar", style="MyButton.TButton", command=lambda: self.search_var.set(""))\
            .pack(side="left", padx=5)

        # Contenedor para el Treeview y sus scrollbars
        container = ttk.Frame(self.suppliers_frame, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)
        
        # Creamos el Treeview
        self.suppliers_list = ttk.Treeview(
            container,
            style="MyTreeview.Treeview",
            columns=("ID", "Nombre", "RUC", "Correo", "Correo2"),
            show="headings",
        )
        for col in ("ID", "Nombre", "RUC", "Correo", "Correo2"):
            self.suppliers_list.heading(col, text=col)
        
        # Creamos las scrollbars vertical y horizontal
        v_scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.suppliers_list.yview)
        h_scrollbar = ttk.Scrollbar(container, orient="horizontal", command=self.suppliers_list.xview)
        
        self.suppliers_list.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Ubicamos el Treeview y las scrollbars en la grilla
        self.suppliers_list.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configuramos el contenedor para que se expanda
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        
        self.load_suppliers()
        
        btn_frame = ttk.Frame(self.suppliers_frame, style="MyFrame.TFrame", padding=5)
        btn_frame.pack(fill="x", pady=5)
        
        ttk.Button(btn_frame, text="Agregar",
                   style="MyButton.TButton",
                   command=self.add_supplier).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Editar",
                   style="MyButton.TButton",
                   command=self.edit_supplier).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Eliminar",
                   style="MyButton.TButton",
                   command=self.delete_supplier).pack(side="left", padx=5)
    
    def load_suppliers(self):
        term = getattr(self, "search_var", None)
        if term and term.get().strip():
            suppliers = db.search_suppliers(term.get().strip())
        else:
            suppliers = db.get_suppliers()
        self.suppliers_list.delete(*self.suppliers_list.get_children())
        for sup in suppliers:
            values = list(sup)
            if len(values) > 2:
                values[2] = _format_ruc(values[2])
            self.suppliers_list.insert("", "end", values=values)
        self.auto_adjust_columns()

    def filter_suppliers(self):
        self.load_suppliers()
    
    def auto_adjust_columns(self):
        style = ttk.Style()
        font_str = style.lookup("MyTreeview.Treeview", "font")
        if not font_str:
            font_str = "TkDefaultFont"
        font = tkFont.Font(font=font_str)
        for col in self.suppliers_list["columns"]:
            header_text = self.suppliers_list.heading(col, option="text")
            max_width = font.measure(header_text)
            for item in self.suppliers_list.get_children():
                cell_text = str(self.suppliers_list.set(item, col))
                cell_width = font.measure(cell_text)
                if cell_width > max_width:
                    max_width = cell_width
            self.suppliers_list.column(col, width=max_width + 20)
    
    def add_supplier(self):
        SupplierForm(self, "Agregar Proveedor", self.load_suppliers)
    
    def edit_supplier(self):
        selected = self.suppliers_list.selection()
        if not selected:
            messagebox.showwarning("Advertencia", "Seleccione un proveedor para editar.")
            return
        data = self.suppliers_list.item(selected[0])["values"]
        supplier_id = data[0]
        try:
            supplier_id_int = int(supplier_id)
        except (TypeError, ValueError):
            supplier_id_int = supplier_id
        supplier_data = db.get_supplier(supplier_id_int)
        if not supplier_data:
            messagebox.showerror("Error", "No se pudo cargar el proveedor seleccionado.")
            return
        supplier_values = list(supplier_data)
        if len(supplier_values) > 2:
            supplier_values[2] = _format_ruc(supplier_values[2])
        SupplierForm(self, "Editar Proveedor", self.load_suppliers, supplier_values)
    
    def delete_supplier(self):
        selected = self.suppliers_list.selection()
        if not selected:
            messagebox.showwarning("Advertencia", "Seleccione un proveedor para eliminar.")
            return
        supplier_id = self.suppliers_list.item(selected[0])["values"][0]
        db.delete_supplier(supplier_id)
        self.load_suppliers()
        messagebox.showinfo("Información", "Proveedor eliminado.")
    
    def create_assignment_tab(self):
        self.assign_list = ttk.Treeview(
            self.assign_frame,
            columns=("Subdepto", "Departamento", "Persona"),
            show="headings",
            style="MyTreeview.Treeview",
            height=10,
        )
        for col in ("Subdepto", "Departamento", "Persona"):
            self.assign_list.heading(col, text=col)
        self.assign_list.pack(fill="both", expand=True, pady=5)

        btn_frame = ttk.Frame(self.assign_frame, style="MyFrame.TFrame", padding=5)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Agregar", style="MyButton.TButton",
                   command=self.add_assignment).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Editar", style="MyButton.TButton",
                   command=self.edit_assignment).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Eliminar", style="MyButton.TButton",
                   command=self.delete_assignment).pack(side="left", padx=5)

        servicios_frame = ttk.LabelFrame(
            self.assign_frame,
            text="Parámetros Servicios",
            style="MyLabelFrame.TLabelframe",
            padding=10,
        )
        servicios_frame.pack(fill="x", pady=(10, 0))
        servicios_frame.columnconfigure(1, weight=1)
        servicios_frame.columnconfigure(3, weight=1)

        ttk.Label(servicios_frame, text="Departamento Telcos:", style="MyLabel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.servicios_dept_var = tk.StringVar(value=db.get_config(SERVICIOS_DEPARTAMENTO_KEY, ""))
        ttk.Entry(servicios_frame, textvariable=self.servicios_dept_var, style="MyEntry.TEntry").grid(
            row=0, column=1, padx=5, sticky="ew"
        )

        ttk.Label(servicios_frame, text="Usuario Telcos:", style="MyLabel.TLabel").grid(
            row=0, column=2, sticky="w"
        )
        self.servicios_usuario_var = tk.StringVar(value=db.get_config(SERVICIOS_USUARIO_KEY, ""))
        ttk.Entry(servicios_frame, textvariable=self.servicios_usuario_var, style="MyEntry.TEntry").grid(
            row=0, column=3, padx=5, sticky="ew"
        )

        ttk.Label(servicios_frame, text="Mensaje de reasignación:", style="MyLabel.TLabel").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.servicios_mensaje_var = tk.StringVar(
            value=db.get_config(SERVICIOS_MENSAJE_KEY, 'Taller Asignado "{proveedor}"')
        )
        ttk.Entry(
            servicios_frame,
            textvariable=self.servicios_mensaje_var,
            style="MyEntry.TEntry",
        ).grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=(8, 0))

        ttk.Button(
            servicios_frame,
            text="Guardar parámetros de Servicios",
            style="MyButton.TButton",
            command=self.save_servicios_params,
        ).grid(row=2, column=0, columnspan=4, sticky="e", pady=(12, 0))

        self.load_assignments()

    def load_assignments(self):
        for i in self.assign_list.get_children():
            self.assign_list.delete(i)
        for sub, dept, person in db.get_assignments():
            self.assign_list.insert("", "end", values=(sub, dept, person))

    def add_assignment(self):
        AssignmentForm(self, "Nueva Asignación", self.load_assignments).wait_window()

    def edit_assignment(self):
        sel = self.assign_list.selection()
        if not sel:
            messagebox.showwarning("Advertencia", "Seleccione un registro a editar.")
            return
        values = self.assign_list.item(sel[0])["values"]
        AssignmentForm(self, "Editar Asignación", self.load_assignments, tuple(values)).wait_window()

    def delete_assignment(self):
        sel = self.assign_list.selection()
        if not sel:
            messagebox.showwarning("Advertencia", "Seleccione un registro a eliminar.")
            return
        sub = self.assign_list.item(sel[0])["values"][0]
        if messagebox.askyesno("Confirmar", "¿Eliminar la asignación seleccionada?"):
            db.delete_assignment(sub)
            self.load_assignments()

    def save_servicios_params(self):
        dept = self.servicios_dept_var.get().strip()
        usuario = self.servicios_usuario_var.get().strip()
        mensaje = self.servicios_mensaje_var.get().strip()
        if not dept or not usuario:
            messagebox.showwarning(
                "Advertencia",
                "Debe definir el departamento y el usuario de reasignación para Servicios.",
            )
            return
        db.set_config(SERVICIOS_DEPARTAMENTO_KEY, dept)
        db.set_config(SERVICIOS_USUARIO_KEY, usuario)
        db.set_config(SERVICIOS_MENSAJE_KEY, mensaje or 'Taller Asignado "{proveedor}"')
        messagebox.showinfo("Configuración", "Parámetros de Servicios actualizados correctamente.")

    def create_tracking_tab(self):
        frame = self.tracking_frame

        ttk.Label(frame, text="Configuración Seguimientos",
                  style="MyLabel.TLabel").pack(pady=10)

        ttk.Label(frame, text="Credenciales Google (JSON):",
                  style="MyLabel.TLabel").pack(pady=5)

        self.google_creds_var = tk.StringVar()
        self.google_creds_var.set(db.get_config("GOOGLE_CREDS", ""))

        ttk.Entry(frame, textvariable=self.google_creds_var,
                  style="MyEntry.TEntry", width=50).pack(pady=5)

        ttk.Button(frame, text="Seleccionar Credenciales",
                   style="MyButton.TButton",
                   command=self.select_google_creds).pack(pady=5)

        ttk.Label(frame, text="ID de Spreadsheet:",
                  style="MyLabel.TLabel").pack(pady=5)

        self.sheet_id_var = tk.StringVar()
        self.sheet_id_var.set(db.get_config("GOOGLE_SHEET_ID", ""))

        ttk.Entry(frame, textvariable=self.sheet_id_var,
                  style="MyEntry.TEntry", width=50).pack(pady=5)

        ttk.Label(frame, text="Nombre de la Hoja:",
                  style="MyLabel.TLabel").pack(pady=5)

        self.sheet_name_var = tk.StringVar()
        self.sheet_name_var.set(db.get_config("GOOGLE_SHEET_NAME", ""))

        ttk.Entry(frame, textvariable=self.sheet_name_var,
                  style="MyEntry.TEntry", width=50).pack(pady=5)

        ttk.Label(frame, text="Correos CC Seguimiento (hasta 9, separados por ';'):",
                  style="MyLabel.TLabel").pack(pady=5)

        self.cc_tracking_var = tk.StringVar()
        self.cc_tracking_var.set(db.get_config("EMAIL_CC_SEGUIMIENTO", ""))

        ttk.Entry(frame, textvariable=self.cc_tracking_var,
                  style="MyEntry.TEntry", width=50).pack(pady=5)

        ttk.Button(frame, text="Guardar Configuración",
                   style="MyButton.TButton",
                   command=self.save_tracking_config).pack(pady=10)

    def create_dispatch_tab(self):
        frame = self.dispatch_frame

        ttk.Label(frame, text="Configuración Despacho",
                  style="MyLabel.TLabel").pack(pady=10)

        ttk.Label(frame, text="Ruta de la carpeta para PDFs:",
                  style="MyLabel.TLabel").pack(pady=5)

        self.pdf_path_var = tk.StringVar()
        self.pdf_path_var.set(db.get_config("PDF_FOLDER", os.path.join(os.path.dirname(__file__), "pdfs")))

        self.pdf_entry = ttk.Entry(frame, textvariable=self.pdf_path_var,
                                   style="MyEntry.TEntry", width=50)
        self.pdf_entry.pack(pady=5)

        ttk.Button(frame, text="Seleccionar Carpeta",
                   style="MyButton.TButton",
                   command=self.select_pdf_folder).pack(pady=5)

        ttk.Label(frame, text="Correos CC Despachos (hasta 9, separados por ';'):",
                  style="MyLabel.TLabel").pack(pady=5)

        self.cc_dispatch_var = tk.StringVar()
        self.cc_dispatch_var.set(db.get_config("EMAIL_CC_DESPACHO", ""))

        ttk.Entry(frame, textvariable=self.cc_dispatch_var,
                  style="MyEntry.TEntry", width=50).pack(pady=5)

        ttk.Button(frame, text="Guardar Configuración",
                   style="MyButton.TButton",
                   command=self.save_dispatch_config).pack(pady=10)
    
    def select_pdf_folder(self):
        folder_selected = filedialog.askdirectory(title="Seleccionar carpeta para PDFs")
        if folder_selected:
            self.pdf_path_var.set(folder_selected)

    def select_google_creds(self):
        path = filedialog.askopenfilename(title="Seleccionar archivo de credenciales", filetypes=[("JSON", "*.json")])
        if path:
            self.google_creds_var.set(path)
    
    def save_tracking_config(self):
        cc_text = self.cc_tracking_var.get().strip()
        emails = [e.strip() for e in re.split(r"[;,]+", cc_text) if e.strip()]
        if len(emails) > 9:
            messagebox.showwarning(
                "Advertencia", "Se permiten máximo 9 correos en CC.")
            return

        db.set_config("GOOGLE_CREDS", self.google_creds_var.get().strip())
        db.set_config("GOOGLE_SHEET_ID", self.sheet_id_var.get().strip())
        db.set_config("GOOGLE_SHEET_NAME", self.sheet_name_var.get().strip())
        db.set_config("EMAIL_CC_SEGUIMIENTO", ";".join(emails) if emails else "")
        messagebox.showinfo(
            "Información", "Configuración guardada correctamente.")

    def save_dispatch_config(self):
        pdf_folder = self.pdf_path_var.get().strip()
        if not pdf_folder:
            messagebox.showwarning(
                "Advertencia", "La ruta de la carpeta no puede estar vacía.")
            return

        cc_text = self.cc_dispatch_var.get().strip()
        emails = [e.strip() for e in re.split(r"[;,]+", cc_text) if e.strip()]
        if len(emails) > 9:
            messagebox.showwarning(
                "Advertencia", "Se permiten máximo 9 correos en CC.")
            return

        db.set_config("PDF_FOLDER", pdf_folder)
        db.set_config("EMAIL_CC_DESPACHO", ";".join(emails) if emails else "")
        messagebox.showinfo(
            "Información", "Configuración guardada correctamente.")

    def create_oc_tab(self):
        cfg = self.descargas_cfg

        canvas = tk.Canvas(self.oc_frame, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.oc_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scrollable = ttk.Frame(canvas, style="MyFrame.TFrame", padding=10)
        window_id = canvas.create_window((0, 0), window=scrollable, anchor="nw")

        def _update_scrollregion(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _resize_inner(event):
            canvas.itemconfigure(window_id, width=event.width)

        scrollable.bind("<Configure>", _update_scrollregion)
        canvas.bind("<Configure>", _resize_inner)

        self._oc_canvas = canvas
        self._oc_scrollable = scrollable

        def _str_var(key: str, value: str) -> tk.StringVar:
            var = tk.StringVar(value=value)
            self._oc_vars[key] = var
            return var

        def _bool_var(key: str, value: bool) -> tk.BooleanVar:
            var = tk.BooleanVar(value=value)
            self._oc_vars[key] = var
            return var

        remitente_cfg = cfg.data.get("remitente_adicional", "")
        if isinstance(remitente_cfg, (list, tuple, set)):
            remitente_txt = ", ".join(str(r).strip() for r in remitente_cfg if str(r).strip())
        else:
            remitente_txt = str(remitente_cfg or "")

        general_frame = ttk.LabelFrame(
            scrollable,
            text="Descargas OC (Normal)",
            style="MyLabelFrame.TLabelframe",
            padding=10,
        )
        general_frame.pack(fill="x", expand=False, pady=(0, 10))
        general_frame.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(general_frame, text="Servidor POP3:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        pop_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("pop_server", cfg.pop_server or ""),
            style="MyEntry.TEntry",
        )
        pop_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["pop_server"] = pop_entry
        self._oc_focus = pop_entry

        row += 1
        ttk.Label(general_frame, text="Puerto POP3:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(
            general_frame,
            textvariable=_str_var("pop_port", str(cfg.pop_port or 995)),
            width=10,
            style="MyEntry.TEntry",
        ).grid(row=row, column=1, sticky="w", padx=5, pady=2)

        row += 1
        ttk.Label(general_frame, text="Usuario:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        user_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("usuario", cfg.usuario or ""),
            style="MyEntry.TEntry",
        )
        user_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["usuario"] = user_entry

        row += 1
        ttk.Label(general_frame, text="Contraseña:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        pwd_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("password", cfg.password or ""),
            show="*",
            style="MyEntry.TEntry",
        )
        pwd_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["password"] = pwd_entry

        row += 1
        ttk.Label(
            general_frame,
            text="Carpeta de descarga principal:",
            style="MyLabel.TLabel",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        dest_frame = ttk.Frame(general_frame, style="MyFrame.TFrame")
        dest_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        dest_entry = ttk.Entry(
            dest_frame,
            textvariable=_str_var(
                "carpeta_destino_local", cfg.carpeta_destino_local or ""
            ),
            style="MyEntry.TEntry",
        )
        dest_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            dest_frame,
            text="Seleccionar",
            style="MyButton.TButton",
            command=lambda: self._browse_directory(self._oc_vars["carpeta_destino_local"]),
        ).pack(side="left", padx=(5, 0))
        self._oc_entries["carpeta_destino_local"] = dest_entry

        row += 1
        ttk.Label(
            general_frame,
            text="Carpeta de tareas Bienes:",
            style="MyLabel.TLabel",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        analizar_frame = ttk.Frame(general_frame, style="MyFrame.TFrame")
        analizar_frame.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        analizar_entry = ttk.Entry(
            analizar_frame,
            textvariable=_str_var("carpeta_analizar", cfg.carpeta_analizar or ""),
            style="MyEntry.TEntry",
        )
        analizar_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            analizar_frame,
            text="Seleccionar",
            style="MyButton.TButton",
            command=lambda: self._browse_directory(self._oc_vars["carpeta_analizar"]),
        ).pack(side="left", padx=(5, 0))
        self._oc_entries["carpeta_analizar"] = analizar_entry

        row += 1
        ttk.Label(general_frame, text="URL Telcodrive:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        url_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("seafile_url", cfg.seafile_url or ""),
            style="MyEntry.TEntry",
        )
        url_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["seafile_url"] = url_entry

        row += 1
        ttk.Label(general_frame, text="ID de carpeta principal:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        repo_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("seafile_repo_id", cfg.seafile_repo_id or ""),
            style="MyEntry.TEntry",
        )
        repo_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["seafile_repo_id"] = repo_entry

        row += 1
        ttk.Label(
            general_frame,
            text="Carpeta personal Telcodrive:",
            style="MyLabel.TLabel",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        sub_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("seafile_subfolder", cfg.seafile_subfolder or "/"),
            style="MyEntry.TEntry",
        )
        sub_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["seafile_subfolder"] = sub_entry

        row += 1
        ttk.Label(general_frame, text="Correo para reporte:", style="MyLabel.TLabel").grid(
            row=row, column=0, sticky="w", padx=5, pady=2
        )
        correo_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("correo_reporte", cfg.correo_reporte or ""),
            style="MyEntry.TEntry",
        )
        correo_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["correo_reporte"] = correo_entry

        row += 1
        ttk.Label(
            general_frame,
            text="Remitentes adicionales (separar con coma):",
            style="MyLabel.TLabel",
        ).grid(row=row, column=0, sticky="w", padx=5, pady=2)
        remitente_entry = ttk.Entry(
            general_frame,
            textvariable=_str_var("remitente_adicional", remitente_txt),
            style="MyEntry.TEntry",
        )
        remitente_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["remitente_adicional"] = remitente_entry

        row += 1
        headless_check = ttk.Checkbutton(
            general_frame,
            text="Ejecutar Chrome en modo oculto (headless)",
            style="MyCheckbutton.TCheckbutton",
            variable=_bool_var("headless", bool(cfg.headless)),
        )
        headless_check.grid(row=row, column=0, columnspan=2, sticky="w", padx=5, pady=4)
        self._oc_entries["headless"] = headless_check

        abas_frame = ttk.LabelFrame(
            scrollable,
            text="Abastecimiento",
            style="MyLabelFrame.TLabelframe",
            padding=10,
        )
        abas_frame.pack(fill="x", expand=False, pady=(0, 10))
        abas_frame.columnconfigure(1, weight=1)

        abas_row = 0
        ttk.Label(abas_frame, text="Carpeta de descarga:", style="MyLabel.TLabel").grid(
            row=abas_row, column=0, sticky="w", padx=5, pady=2
        )
        abas_dest_frame = ttk.Frame(abas_frame, style="MyFrame.TFrame")
        abas_dest_frame.grid(row=abas_row, column=1, sticky="ew", padx=5, pady=2)
        abas_dest_entry = ttk.Entry(
            abas_dest_frame,
            textvariable=_str_var(
                "abastecimiento_carpeta_descarga",
                cfg.abastecimiento_carpeta_descarga or cfg.carpeta_destino_local or "",
            ),
            style="MyEntry.TEntry",
        )
        abas_dest_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(
            abas_dest_frame,
            text="Seleccionar",
            style="MyButton.TButton",
            command=lambda: self._browse_directory(self._oc_vars["abastecimiento_carpeta_descarga"]),
        ).pack(side="left", padx=(5, 0))
        self._oc_entries["abastecimiento_carpeta_descarga"] = abas_dest_entry
        self._abastecimiento_focus = abas_dest_entry

        abas_row += 1
        ttk.Label(abas_frame, text="Correo para reporte:", style="MyLabel.TLabel").grid(
            row=abas_row, column=0, sticky="w", padx=5, pady=2
        )
        abas_correo_entry = ttk.Entry(
            abas_frame,
            textvariable=_str_var(
                "abastecimiento_correo_reporte",
                cfg.abastecimiento_correo_reporte or cfg.correo_reporte or "",
            ),
            style="MyEntry.TEntry",
        )
        abas_correo_entry.grid(row=abas_row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["abastecimiento_correo_reporte"] = abas_correo_entry

        abas_row += 1
        solicitantes_txt = ", ".join(cfg.abastecimiento_solicitantes or [])
        ttk.Label(
            abas_frame,
            text="Solicitantes (separa con coma o salto de línea):",
            style="MyLabel.TLabel",
        ).grid(row=abas_row, column=0, sticky="w", padx=5, pady=2)
        abas_sol_entry = ttk.Entry(
            abas_frame,
            textvariable=_str_var("abastecimiento_solicitantes", solicitantes_txt),
            style="MyEntry.TEntry",
        )
        abas_sol_entry.grid(row=abas_row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["abastecimiento_solicitantes"] = abas_sol_entry

        abas_row += 1
        autorizadores_txt = ", ".join(cfg.abastecimiento_autorizadores or [])
        ttk.Label(
            abas_frame,
            text="Autorizadores (separa con coma o salto de línea):",
            style="MyLabel.TLabel",
        ).grid(row=abas_row, column=0, sticky="w", padx=5, pady=2)
        abas_aut_entry = ttk.Entry(
            abas_frame,
            textvariable=_str_var("abastecimiento_autorizadores", autorizadores_txt),
            style="MyEntry.TEntry",
        )
        abas_aut_entry.grid(row=abas_row, column=1, sticky="ew", padx=5, pady=2)
        self._oc_entries["abastecimiento_autorizadores"] = abas_aut_entry

        abas_row += 1
        abas_headless_check = ttk.Checkbutton(
            abas_frame,
            text="Ejecutar Chrome en modo oculto (headless)",
            style="MyCheckbutton.TCheckbutton",
            variable=_bool_var(
                "abastecimiento_headless", bool(cfg.abastecimiento_headless)
            ),
        )
        abas_headless_check.grid(
            row=abas_row, column=0, columnspan=2, sticky="w", padx=5, pady=4
        )
        self._oc_entries["abastecimiento_headless"] = abas_headless_check

        button_frame = ttk.Frame(scrollable, style="MyFrame.TFrame")
        button_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(
            button_frame,
            text="Guardar Configuración",
            style="MyButton.TButton",
            command=self.save_descargas_config,
        ).pack(side="left", padx=5)

        ttk.Button(
            button_frame,
            text="Probar subida a Telcodrive",
            style="MyButton.TButton",
            command=self.test_seafile_upload,
        ).pack(side="left", padx=5)

        self._procesados_button = ttk.Button(
            button_frame,
            text="Generar procesados",
            style="MyButton.TButton",
            command=self.generate_processed_file,
        )
        self._procesados_button.pack(side="left", padx=5)

        ttk.Label(
            button_frame,
            textvariable=self._procesados_status,
            style="MyLabel.TLabel",
        ).pack(side="left", padx=5)

    def create_email_templates_tab(self):
        frame = self.email_templates_frame
        ttk.Label(frame, text="Seleccione el Formato de Correo Actual:",
                  style="MyLabel.TLabel").pack(pady=10)
        self.email_template_var = tk.StringVar()
        self.template_combo = ttk.Combobox(frame, textvariable=self.email_template_var,
                                           state="readonly")
        self.template_combo.pack(pady=5)
        ttk.Button(frame, text="Guardar Formato",
                   style="MyButton.TButton",
                   command=self.save_email_template).pack(pady=10)

        self.templates_list = ttk.Treeview(frame, style="MyTreeview.Treeview",
                                           columns=("ID", "Nombre"), show="headings",
                                           height=5)
        self.templates_list.heading("ID", text="ID")
        self.templates_list.heading("Nombre", text="Nombre")
        self.templates_list.column("ID", width=50)
        self.templates_list.pack(fill="x", pady=5)

        btn_frame = ttk.Frame(frame, style="MyFrame.TFrame", padding=5)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="Agregar",
                   style="MyButton.TButton",
                   command=self.agregar_nuevo_formato).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Editar",
                   style="MyButton.TButton",
                   command=self.editar_formato).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Eliminar",
                   style="MyButton.TButton",
                   command=self.eliminar_formato).pack(side="left", padx=5)

        self.load_email_templates()
    
    def save_email_template(self):
        formato = self.email_template_var.get().strip()
        if not formato:
            messagebox.showwarning("Advertencia", "Debe seleccionar un formato de correo.")
            return
        db.set_config("EMAIL_TEMPLATE", formato)
        messagebox.showinfo("Información", "Formato de correo guardado correctamente.")

    def load_email_templates(self):
        for i in self.templates_list.get_children():
            self.templates_list.delete(i)
        templates = db.get_email_templates()
        for tpl in templates:
            self.templates_list.insert("", "end", values=(tpl[0], tpl[1]))

        opciones = ["FORMATO"] + [tpl[1] for tpl in templates]
        self.template_combo["values"] = opciones
        current = db.get_config("EMAIL_TEMPLATE", "FORMATO")
        if current in opciones:
            self.email_template_var.set(current)
        else:
            self.email_template_var.set("FORMATO")

    def agregar_nuevo_formato(self):
        TemplateForm(self, "Nuevo Formato", self.load_email_templates, email_session=self.email_session).wait_window()

    def editar_formato(self):
        selected = self.templates_list.selection()
        if not selected:
            messagebox.showwarning("Advertencia", "Seleccione un formato para editar.")
            return
        tpl_id = self.templates_list.item(selected[0])["values"][0]
        data = db.get_email_template(tpl_id)
        TemplateForm(self, "Editar Formato", self.load_email_templates, data, email_session=self.email_session).wait_window()

    def eliminar_formato(self):
        selected = self.templates_list.selection()
        if not selected:
            messagebox.showwarning("Advertencia", "Seleccione un formato para eliminar.")
            return
        tpl_id = self.templates_list.item(selected[0])["values"][0]
        if messagebox.askyesno("Confirmar", "¿Eliminar el formato seleccionado?"):
            db.delete_email_template(tpl_id)
            self.load_email_templates()

    def _browse_directory(self, var: tk.StringVar):
        initial = var.get().strip() or os.getcwd()
        path = filedialog.askdirectory(initialdir=initial)
        if path:
            var.set(path)

    @staticmethod
    def _parse_list(value: str) -> list[str]:
        if not value:
            return []
        partes = [p.strip() for p in re.split(r"[;\n,]+", value) if p.strip()]
        return partes

    def _safe_int(self, key: str, default: int) -> int:
        raw = self._oc_vars.get(key)
        if raw is None:
            return default
        valor = raw.get()
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            return default

    def _collect_descargas_form(self) -> dict:
        cfg = self.descargas_cfg
        data = {
            "pop_server": self._oc_vars["pop_server"].get().strip(),
            "pop_port": self._safe_int("pop_port", cfg.data.get("pop_port", 995)),
            "usuario": self._oc_vars["usuario"].get().strip(),
            "password": self._oc_vars["password"].get(),
            "carpeta_destino_local": self._oc_vars["carpeta_destino_local"].get().strip(),
            "carpeta_analizar": self._oc_vars["carpeta_analizar"].get().strip(),
            "seafile_url": self._oc_vars["seafile_url"].get().strip(),
            "seafile_repo_id": self._oc_vars["seafile_repo_id"].get().strip(),
            "seafile_subfolder": self._oc_vars["seafile_subfolder"].get().strip() or "/",
            "correo_reporte": self._oc_vars["correo_reporte"].get().strip(),
            "headless": bool(self._oc_vars["headless"].get()),
            "abastecimiento_carpeta_descarga": self._oc_vars[
                "abastecimiento_carpeta_descarga"
            ].get().strip(),
            "abastecimiento_correo_reporte": self._oc_vars[
                "abastecimiento_correo_reporte"
            ].get().strip(),
            "abastecimiento_headless": bool(
                self._oc_vars["abastecimiento_headless"].get()
            ),
            "abastecimiento_solicitantes": self._parse_list(
                self._oc_vars["abastecimiento_solicitantes"].get()
            ),
            "abastecimiento_autorizadores": self._parse_list(
                self._oc_vars["abastecimiento_autorizadores"].get()
            ),
        }

        remitentes_texto = self._oc_vars["remitente_adicional"].get().strip()
        if remitentes_texto:
            remitentes = self._parse_list(remitentes_texto)
            data["remitente_adicional"] = ", ".join(remitentes) if remitentes else remitentes_texto
        else:
            data["remitente_adicional"] = ""
        return data

    def save_descargas_config(self):
        datos = self._collect_descargas_form()
        self.descargas_cfg.data.update(datos)
        try:
            self.descargas_cfg.validate()
        except Exception as exc:
            messagebox.showerror("Error", f"Configuración inválida: {exc}")
            return
        self.descargas_cfg.save()
        self._procesados_status.set("Generado" if PROCESADOS_FILE.exists() else "Pendiente")
        messagebox.showinfo("Información", "Configuración guardada correctamente.")

    def test_seafile_upload(self):
        datos = self._collect_descargas_form()
        self.descargas_cfg.data.update(datos)
        try:
            self.descargas_cfg.validate()
        except Exception as exc:
            messagebox.showerror("Error", f"Configuración inválida: {exc}")
            return
        archivo = filedialog.askopenfilename(title="Seleccionar archivo de prueba")
        if not archivo:
            return
        try:
            from descargas_oc.seafile_client import SeafileClient

            cliente = SeafileClient(
                self.descargas_cfg.seafile_url,
                self.descargas_cfg.usuario,
                self.descargas_cfg.password,
            )
            cliente.upload_file(
                self.descargas_cfg.seafile_repo_id,
                archivo,
                parent_dir=self.descargas_cfg.seafile_subfolder,
            )
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo subir el archivo: {exc}")
            return
        messagebox.showinfo("Información", "Archivo subido correctamente.")

    def generate_processed_file(self):
        datos = self._collect_descargas_form()
        servidor = datos["pop_server"]
        usuario = datos["usuario"]
        contrasena = datos["password"]
        puerto = datos["pop_port"]
        if not (servidor and usuario and contrasena):
            messagebox.showwarning(
                "Advertencia",
                "Debe completar servidor, usuario y contraseña para generar el archivo.",
            )
            return

        if self._procesados_button:
            self._procesados_button.config(state=tk.DISABLED)
        self._procesados_status.set("Generando...")

        def tarea():
            mensaje = ""
            estado = "Pendiente"
            try:
                conn = poplib.POP3_SSL(servidor, puerto)
                conn.user(usuario)
                conn.pass_(contrasena)
                total = len(conn.list()[1])
                PROCESADOS_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(PROCESADOS_FILE, "w", encoding="utf-8") as archivo:
                    for indice in range(total):
                        respuesta = conn.uidl(indice + 1)
                        linea = respuesta.decode() if isinstance(respuesta, bytes) else respuesta
                        uidl = linea.split()[2]
                        archivo.write(uidl + "\n")
                conn.quit()
                mensaje = f"Se generaron {total} UIDL(s)."
                estado = "Generado"
            except Exception as exc:  # pragma: no cover - interacción con servidor
                mensaje = f"No se pudo generar el archivo: {exc}"
                estado = "Error"

            def finalizar():
                if self._procesados_button:
                    self._procesados_button.config(state=tk.NORMAL)
                self._procesados_status.set(estado)
                if estado == "Generado":
                    messagebox.showinfo("Procesados", mensaje)
                else:
                    messagebox.showerror("Procesados", mensaje)

            self.after(0, finalizar)

        threading.Thread(target=tarea, daemon=True).start()

    def _scroll_to_widget(self, widget: tk.Widget):
        canvas = self._oc_canvas
        container = self._oc_scrollable
        if not canvas or not container:
            return
        try:
            canvas.update_idletasks()
            container.update_idletasks()
            widget.update_idletasks()
        except tk.TclError:  # pragma: no cover - widget destruido
            return

        frame_height = container.winfo_height()
        canvas_height = canvas.winfo_height()
        if frame_height <= canvas_height or canvas_height <= 0:
            return

        try:
            widget_top = widget.winfo_rooty() - container.winfo_rooty()
            widget_bottom = widget_top + widget.winfo_height()
        except tk.TclError:  # pragma: no cover - widget sin geometría
            return

        view_top, view_bottom = canvas.yview()
        view_top *= frame_height
        view_bottom *= frame_height

        if widget_top < view_top:
            destino = max(0, widget_top / frame_height)
            canvas.yview_moveto(destino)
        elif widget_bottom > view_bottom:
            destino = (widget_bottom - canvas_height) / frame_height
            destino = min(max(0, destino), 1)
            canvas.yview_moveto(destino)

    def focus_descargas_tab(self, section: str | None = None):
        try:
            self.notebook.select(self.oc_frame)
        except tk.TclError:  # pragma: no cover - defensive
            return
        objetivo: tk.Widget | None = self._oc_focus
        if section == "abastecimiento" and self._abastecimiento_focus:
            objetivo = self._abastecimiento_focus
        if objetivo:
            objetivo.focus_set()
            self.after(50, lambda: self._scroll_to_widget(objetivo))


class TemplateForm(tk.Toplevel):
    def __init__(self, master, title, refresh_callback, template_data=None, email_session=None):
        super().__init__(master)
        self.title(title)
        self.geometry("800x600")
        self.transient(master)
        self.grab_set()
        self.focus()
        self.refresh_callback = refresh_callback
        self.template_data = template_data
        self.email_session = email_session
        self.create_widgets()
        center_window(self)

    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=10)
        container.pack(fill="both", expand=True)

        container.columnconfigure(0, weight=1)

        self.name_var = tk.StringVar()
        self.signature_var = tk.StringVar()

        row = 0
        ttk.Label(container, text="Nombre:", style="MyLabel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        row += 1
        ttk.Entry(container, textvariable=self.name_var, style="MyEntry.TEntry").grid(row=row, column=0, sticky="ew", pady=5)
        row += 1

        ttk.Label(container, text="Imagen de firma:", style="MyLabel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        row += 1
        frame_img = ttk.Frame(container, style="MyFrame.TFrame")
        frame_img.grid(row=row, column=0, sticky="ew")
        frame_img.columnconfigure(0, weight=1)
        ttk.Entry(frame_img, textvariable=self.signature_var, style="MyEntry.TEntry").grid(row=0, column=0, sticky="ew", pady=5)
        ttk.Button(frame_img, text="Seleccionar", style="MyButton.TButton", command=self.select_image).grid(row=0, column=1, padx=5)
        row += 1
        ttk.Button(container, text="Guardar", style="MyButton.TButton", command=self.save_template).grid(row=row, column=0, pady=(5,10), sticky="w")
        row += 1

        ttk.Label(container, text="Contenido HTML:", style="MyLabel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        row += 1
        self.editor = HtmlEditor(container)
        self.editor.grid(row=row, column=0, sticky="nsew", pady=5)
        container.rowconfigure(row, weight=1)
        row += 1

        ttk.Label(container, text="Correo de prueba:", style="MyLabel.TLabel").grid(row=row, column=0, sticky="w", pady=5)
        row += 1
        test_frame = ttk.Frame(container, style="MyFrame.TFrame")
        test_frame.grid(row=row, column=0, sticky="ew")
        test_frame.columnconfigure(0, weight=1)
        self.test_email_var = tk.StringVar()
        ttk.Entry(test_frame, textvariable=self.test_email_var, style="MyEntry.TEntry").grid(row=0, column=0, sticky="ew", pady=5)
        ttk.Button(test_frame, text="Enviar prueba", style="MyButton.TButton", command=self.send_test_email).grid(row=0, column=1, padx=5, pady=5)

        if self.template_data:
            self.name_var.set(self.template_data[1])
            self.editor.set_html(self.template_data[2])
            if self.template_data[3]:
                self.signature_var.set(self.template_data[3])

    def select_image(self):
        path = filedialog.askopenfilename(title="Seleccionar imagen", filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif")])
        if path:
            self.signature_var.set(path)

    def save_template(self):
        # Recreate missing tables if the database was not initialized
        db.init_db()
        name = self.name_var.get().strip()
        self.editor.text.tag_remove("sel", "1.0", "end")
        raw_text = self.editor.text.get("1.0", "end-1c").strip()
        html = self.editor.get_html().strip()
        if not html and raw_text:
            html = escape(raw_text).replace("\n", "<br>")
        signature = self.signature_var.get().strip()
        if not (name and raw_text):
            messagebox.showwarning(
                "Advertencia",
                "El nombre y el contenido son obligatorios.",
            )
            return
        if self.template_data:
            db.update_email_template(self.template_data[0], name, html, signature)
        else:
            db.add_email_template(name, html, signature)
        self.refresh_callback()
        self.destroy()

    def send_test_email(self):
        email = self.test_email_var.get().strip()
        if not email:
            messagebox.showwarning("Advertencia", "Ingrese un correo para la prueba.")
            return
        if not self.email_session:
            messagebox.showerror("Error", "No hay sesión de correo configurada.")
            return
        name = self.name_var.get().strip() or "Formato"
        self.editor.text.tag_remove("sel", "1.0", "end")
        raw_text = self.editor.text.get("1.0", "end-1c").strip()
        html = self.editor.get_html().strip()
        if not html and raw_text:
            html = escape(raw_text).replace("\n", "<br>")
        try:
            send_email_custom(
                self.email_session,
                subject=f"Prueba {name}",
                html_template=html,
                context={"email_to": email},
                signature_path=self.signature_var.get().strip() or None,
            )
            messagebox.showinfo("Información", "Correo de prueba enviado correctamente.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar el correo: {e}")
    

class SupplierForm(tk.Toplevel):
    def __init__(self, master, title, refresh_callback, supplier_data=None):
        super().__init__(master)
        self.title(title)
        self.refresh_callback = refresh_callback
        self.supplier_data = supplier_data
        self.create_widgets()
        center_window(self)
    
    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=10)
        container.pack(fill="both", expand=True)
        
        self.name_var = tk.StringVar()
        self.ruc_var = tk.StringVar()
        self.email_var = tk.StringVar()
        self.email2_var = tk.StringVar()
        
        ttk.Label(container, text="Nombre:", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.name_var, style="MyEntry.TEntry").pack(pady=5, fill="x")
        
        ttk.Label(container, text="RUC:", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.ruc_var, style="MyEntry.TEntry").pack(pady=5, fill="x")
        
        ttk.Label(container, text="Correo:", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.email_var, style="MyEntry.TEntry").pack(pady=5, fill="x")

        ttk.Label(container, text="Correo 2 (opcional):", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.email2_var, style="MyEntry.TEntry").pack(pady=5, fill="x")
        
        ttk.Button(container, text="Guardar",
                   style="MyButton.TButton",
                   command=self.save_supplier).pack(pady=10)
        
        if self.supplier_data:
            self.name_var.set(self.supplier_data[1])
            self.ruc_var.set(self.supplier_data[2])
            self.email_var.set(self.supplier_data[3])
            if len(self.supplier_data) > 4:
                self.email2_var.set(self.supplier_data[4])

    def save_supplier(self):
        name = self.name_var.get().strip()
        ruc = self.ruc_var.get().strip()
        email = self.email_var.get().strip()
        email2 = self.email2_var.get().strip()
        if not (name and ruc and email):
            messagebox.showwarning(
                "Advertencia",
                "Nombre, RUC y el primer correo son obligatorios.",
            )
            return
        if self.supplier_data:
            db.update_supplier(self.supplier_data[0], name, ruc, email, email2)
        else:
            db.add_supplier(name, ruc, email, email2)
        self.refresh_callback()
        self.destroy()


class AssignmentForm(tk.Toplevel):
    def __init__(self, master, title, refresh_callback, data=None):
        super().__init__(master)
        self.title(title)
        self.refresh_callback = refresh_callback
        self.data = data
        self.create_widgets()
        center_window(self)

    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=10)
        container.pack(fill="both", expand=True)

        self.sub_var = tk.StringVar()
        self.dept_var = tk.StringVar()
        self.person_var = tk.StringVar()

        ttk.Label(container, text="Subdepartamento:", style="MyLabel.TLabel").pack(anchor="w")
        ttk.Entry(container, textvariable=self.sub_var, style="MyEntry.TEntry").pack(fill="x", pady=5)

        ttk.Label(container, text="Departamento:", style="MyLabel.TLabel").pack(anchor="w")
        ttk.Entry(container, textvariable=self.dept_var, style="MyEntry.TEntry").pack(fill="x", pady=5)

        ttk.Label(container, text="Persona:", style="MyLabel.TLabel").pack(anchor="w")
        ttk.Entry(container, textvariable=self.person_var, style="MyEntry.TEntry").pack(fill="x", pady=5)

        ttk.Button(container, text="Guardar", style="MyButton.TButton", command=self.save).pack(pady=10)

        if self.data:
            self.sub_var.set(self.data[0])
            self.dept_var.set(self.data[1])
            self.person_var.set(self.data[2])

    def save(self):
        sub = self.sub_var.get().strip().upper()
        dept = self.dept_var.get().strip()
        person = self.person_var.get().strip()
        if not (sub and dept and person):
            messagebox.showwarning("Advertencia", "Todos los campos son obligatorios.")
            return
        if self.data and self.data[0] != sub:
            db.delete_assignment(self.data[0])
        db.set_assignment_config(sub, dept, person)
        self.refresh_callback()
        self.destroy()

def open_config_gui(root, email_session, *, focus_descargas: bool = False, section: str | None = None):
    config_window = ConfigGUI(root, email_session)
    if focus_descargas:
        config_window.focus_descargas_tab(section)
    config_window.transient(root)
    config_window.grab_set()
    config_window.wait_window()
