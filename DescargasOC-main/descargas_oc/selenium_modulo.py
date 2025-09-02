from selenium import webdriver
import time
from tkinter import Tk, messagebox

try:  # allow running as script
    from .config import Config
    from .mover_pdf import mover_oc
except ImportError:  # pragma: no cover
    from config import Config
    from mover_pdf import mover_oc


def descargar_oc(numero_oc, fecha_aut=None, fecha_orden=None):
    cfg = Config()
    download_dir = cfg.carpeta_destino_local

    options = webdriver.ChromeOptions()
    if download_dir:
        prefs = {"download.default_directory": download_dir}
        options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)
    driver.get("https://www.google.com")
    time.sleep(5)
    driver.quit()

    root = Tk()
    root.attributes('-topmost', True)
    root.withdraw()
    messagebox.showinfo("Prueba Selenium", "✅ Script automático de Selenium terminó")
    root.destroy()

    return mover_oc(cfg, [numero_oc])

