"""Interfaz gráfica para comparar múltiples cotizaciones.

Esta ventana permite cargar varios archivos de cotización (PDF o Excel),
comparar los ítems detectados y recomendar el mejor precio disponible.  Los
resultados se registran en la base de datos para auditoría y análisis futuro.
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from gestorcompras.services import quote_comparator, market_search, db


class CotizadorGUI(tk.Toplevel):
    def __init__(self, master: tk.Misc | None = None):
        super().__init__(master)
        # Aseguramos que la base de datos tenga todas las tablas necesarias
        db.init_db()
        self.title("Comparar cotizaciones")
        self.geometry("700x500")
        self.files: list[str] = []
        self._create_widgets()

    def _create_widgets(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Agregar archivos", command=self.add_files).pack(side="left")
        ttk.Button(btn_frame, text="Comparar", command=self.compare).pack(side="left", padx=5)

        columns = ("item", "best_price", "source")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings")
        self.tree.heading("item", text="Item")
        self.tree.heading("best_price", text="Mejor precio")
        self.tree.heading("source", text="Fuente")
        self.tree.pack(fill="both", expand=True, pady=10)

    # ------------------ Acciones ------------------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Cotizaciones", "*.pdf *.xls *.xlsx"), ("Todos", "*.*")]
        )
        if not paths:
            return
        self.files.extend(paths)
        messagebox.showinfo("Información", f"Se agregaron {len(paths)} archivo(s).")

    def compare(self):
        if len(self.files) < 2:
            messagebox.showwarning(
                "Advertencia", "Agregue al menos dos cotizaciones para comparar."
            )
            return

        quotes = []
        for path in self.files:
            items = quote_comparator.parse_quote(path)
            quotes.append({"source": os.path.basename(path), "items": items})

        if not quotes or not quotes[0]["items"]:
            messagebox.showerror(
                "Error", "No se pudieron leer los ítems de las cotizaciones."
            )
            return

        reference = quotes[0]
        results = {}
        for item in reference["items"]:
            desc = item["description"]
            best_price = item["price"]
            best_source = reference["source"]
            details = {reference["source"]: best_price}

            for other in quotes[1:]:
                matches = quote_comparator.match_items([desc], other["items"])
                match = matches[0]
                if match["quoted"] is not None:
                    details[other["source"]] = match["quoted_price"]
                    if match["quoted_price"] < best_price:
                        best_price = match["quoted_price"]
                        best_source = other["source"]

            market = market_search.find_best_price(desc)
            if market and market.get("price") is not None:
                details[market["source"]] = market["price"]
                if market["price"] < best_price:
                    best_price = market["price"]
                    best_source = market["source"]

            results[desc] = {
                "best_price": best_price,
                "best_source": best_source,
                "details": details,
            }
            db.log_quote_comparison(desc, best_source, best_price, details)

        for row in self.tree.get_children():
            self.tree.delete(row)
        for desc, info in results.items():
            self.tree.insert("", "end", values=(desc, info["best_price"], info["best_source"]))

def open_cotizador(master: tk.Misc):
    """Abrir la ventana de comparación de cotizaciones."""
    window = CotizadorGUI(master)
    window.transient(master)
    window.grab_set()
    window.wait_window()
