import tkinter as tk
import os
import tkinter.font as tkFont
from tkinter import ttk, messagebox, simpledialog, filedialog
from gestorcompras.services import db

class ConfigGUI(tk.Toplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("Configuración")
        self.geometry("670x500")
        self.create_widgets()
    
    def create_widgets(self):
        self.notebook = ttk.Notebook(self, style="MyNotebook.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.suppliers_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.assign_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.general_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        self.email_templates_frame = ttk.Frame(self.notebook, style="MyFrame.TFrame", padding=10)
        
        self.notebook.add(self.suppliers_frame, text="Proveedores")
        self.notebook.add(self.assign_frame, text="Asignación")
        self.notebook.add(self.general_frame, text="General")
        self.notebook.add(self.email_templates_frame, text="Formatos de Correo")
        
        self.create_suppliers_tab()
        self.create_assignment_tab()
        self.create_general_tab()
        self.create_email_templates_tab()
    
    def create_suppliers_tab(self):
        # Contenedor para el Treeview y sus scrollbars
        container = ttk.Frame(self.suppliers_frame, style="MyFrame.TFrame")
        container.pack(fill="both", expand=True)
        
        # Creamos el Treeview
        self.suppliers_list = ttk.Treeview(container,
                                           style="MyTreeview.Treeview",
                                           columns=("ID", "Nombre", "RUC", "Correo"),
                                           show="headings")
        for col in ("ID", "Nombre", "RUC", "Correo"):
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
        for i in self.suppliers_list.get_children():
            self.suppliers_list.delete(i)
        for sup in db.get_suppliers():
            self.suppliers_list.insert("", "end", values=sup)
        self.auto_adjust_columns()
    
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
        SupplierForm(self, "Editar Proveedor", self.load_suppliers, data)
    
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
        ttk.Label(self.assign_frame, text="Seleccione el Departamento:",
                  style="MyLabel.TLabel").pack(pady=5)
        
        self.dept_var = tk.StringVar(value="GENERAL")
        self.dept_combo = ttk.Combobox(self.assign_frame,
                                       textvariable=self.dept_var,
                                       values=["GENERAL", "MOVILIZACIÓN", "OBRA CIVIL"],
                                       state="readonly")
        self.dept_combo.pack(pady=5)
        self.dept_combo.bind("<<ComboboxSelected>>", lambda e: self.load_assignment_config())
        
        ttk.Label(self.assign_frame, text="Persona asignada:",
                  style="MyLabel.TLabel").pack(pady=5)
        
        self.person_var = tk.StringVar()
        self.person_entry = ttk.Entry(self.assign_frame, textvariable=self.person_var,
                                      style="MyEntry.TEntry", width=50)
        self.person_entry.pack(pady=5)
        
        btn_frame = ttk.Frame(self.assign_frame, style="MyFrame.TFrame", padding=5)
        btn_frame.pack(pady=5)
        
        ttk.Button(btn_frame, text="Guardar",
                   style="MyButton.TButton",
                   command=self.save_assignment).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Eliminar",
                   style="MyButton.TButton",
                   command=self.delete_assignment).pack(side="left", padx=5)
        
        self.load_assignment_config()
    
    def load_assignment_config(self):
        dept = self.dept_var.get()
        config = db.get_assignment_config_single()
        if dept in config:
            self.person_var.set(config[dept])
        else:
            self.person_var.set("")
    
    def save_assignment(self):
        dept = self.dept_var.get()
        person = self.person_var.get().strip()
        if not person:
            messagebox.showwarning("Advertencia", "El campo persona no puede estar vacío.")
            return
        db.set_assignment_config(dept, person)
        messagebox.showinfo("Información", "Asignación guardada correctamente.")
    
    def delete_assignment(self):
        dept = self.dept_var.get()
        db.set_assignment_config(dept, "")
        self.person_var.set("")
        messagebox.showinfo("Información", "Asignación eliminada.")
    
    def create_general_tab(self):
        frame = self.general_frame
        
        ttk.Label(frame, text="Configuración General",
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
        
        ttk.Button(frame, text="Guardar Configuración",
                   style="MyButton.TButton",
                   command=self.save_general_config).pack(pady=10)
    
    def select_pdf_folder(self):
        folder_selected = filedialog.askdirectory(title="Seleccionar carpeta para PDFs")
        if folder_selected:
            self.pdf_path_var.set(folder_selected)
    
    def save_general_config(self):
        pdf_folder = self.pdf_path_var.get().strip()
        if not pdf_folder:
            messagebox.showwarning("Advertencia", "La ruta de la carpeta no puede estar vacía.")
            return
        db.set_config("PDF_FOLDER", pdf_folder)
        messagebox.showinfo("Información", "Configuración guardada correctamente.")
    
    def create_email_templates_tab(self):
        frame = self.email_templates_frame
        ttk.Label(frame, text="Seleccione el Formato de Correo Actual:",
                  style="MyLabel.TLabel").pack(pady=10)
        self.email_template_var = tk.StringVar()
        self.email_template_var.set(db.get_config("EMAIL_TEMPLATE", "Bienes"))
        self.template_combo = ttk.Combobox(frame, textvariable=self.email_template_var,
                                           values=["Bienes", "Servicios"], state="readonly")
        self.template_combo.pack(pady=5)
        ttk.Button(frame, text="Guardar Formato",
                   style="MyButton.TButton",
                   command=self.save_email_template).pack(pady=10)
        ttk.Button(frame, text="Agregar Nuevo Formato",
                   style="MyButton.TButton",
                   command=self.agregar_nuevo_formato).pack(pady=5)
    
    def save_email_template(self):
        formato = self.email_template_var.get().strip()
        if not formato:
            messagebox.showwarning("Advertencia", "Debe seleccionar un formato de correo.")
            return
        db.set_config("EMAIL_TEMPLATE", formato)
        messagebox.showinfo("Información", "Formato de correo guardado correctamente.")
    
    def agregar_nuevo_formato(self):
        messagebox.showinfo("Formato", "Funcionalidad para agregar nuevo formato pendiente de implementar.")

class SupplierForm(tk.Toplevel):
    def __init__(self, master, title, refresh_callback, supplier_data=None):
        super().__init__(master)
        self.title(title)
        self.refresh_callback = refresh_callback
        self.supplier_data = supplier_data
        self.create_widgets()
    
    def create_widgets(self):
        container = ttk.Frame(self, style="MyFrame.TFrame", padding=10)
        container.pack(fill="both", expand=True)
        
        self.name_var = tk.StringVar()
        self.ruc_var = tk.StringVar()
        self.email_var = tk.StringVar()
        
        ttk.Label(container, text="Nombre:", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.name_var, style="MyEntry.TEntry").pack(pady=5, fill="x")
        
        ttk.Label(container, text="RUC:", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.ruc_var, style="MyEntry.TEntry").pack(pady=5, fill="x")
        
        ttk.Label(container, text="Correo:", style="MyLabel.TLabel").pack(pady=5, anchor="w")
        ttk.Entry(container, textvariable=self.email_var, style="MyEntry.TEntry").pack(pady=5, fill="x")
        
        ttk.Button(container, text="Guardar",
                   style="MyButton.TButton",
                   command=self.save_supplier).pack(pady=10)
        
        if self.supplier_data:
            self.name_var.set(self.supplier_data[1])
            self.ruc_var.set(self.supplier_data[2])
            self.email_var.set(self.supplier_data[3])

    def save_supplier(self):
        name = self.name_var.get().strip()
        ruc = self.ruc_var.get().strip()
        email = self.email_var.get().strip()
        if not (name and ruc and email):
            messagebox.showwarning("Advertencia", "Todos los campos son obligatorios.")
            return
        if self.supplier_data:
            db.update_supplier(self.supplier_data[0], name, ruc, email)
        else:
            db.add_supplier(name, ruc, email)
        self.refresh_callback()
        self.destroy()

def open_config_gui(root):
    config_window = ConfigGUI(root)
    config_window.transient(root)
    config_window.grab_set()
    config_window.wait_window()
