import tkinter as tk
from tkinter import ttk

def open_descarga_oc(master, email_session):
    """Placeholder window for Descarga de OC module."""
    window = tk.Toplevel(master)
    window.title("Descarga de OC")
    window.geometry("600x400")
    window.transient(master)
    window.grab_set()

    frame = ttk.Frame(window, padding=10, style="MyFrame.TFrame")
    frame.pack(fill="both", expand=True)

    label = ttk.Label(frame,
                      text="Módulo Descarga de OC en desarrollo",
                      style="MyLabel.TLabel")
    label.pack(pady=20)
