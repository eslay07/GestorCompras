#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SeaDrive Auto-Resync (Windows) - TelcoDrive preset
--------------------------------------------------
Config adaptada para:
- Host: telcodrive.telconet.net (HTTPS 443)
- Ejecutable: C:\\Program Files\\SeaDrive\\bin\\seadrive-gui.exe
- Unidad: E:
Solo librerías estándar.
"""

import os
import sys
import time
import socket
import subprocess
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

# --------------- CONFIGURACIÓN ---------------
# Se acepta con o sin esquema (http/https); se extrae hostname automáticamente
SEAFILE_HOST_RAW = "https://telcodrive.telconet.net"
SEAFILE_PORT = 443
SEADRIVE_EXE = r"C:\\Program Files\\SeaDrive\\bin\\seadrive-gui.exe"
DRIVE_LETTER = "E:"
MOUNT_RETRIES = 5
RETRY_DELAY = 5
NETWORK_TIMEOUT = 2
NETWORK_TRIES = 60

# --------------- LOGGING ---------------
def _log_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or Path.home())
    return base / "seadrive_autoresync.log"

logger = logging.getLogger("seadrive_autoresync")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(_log_path(), maxBytes=256_000, backupCount=2, encoding="utf-8")
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(fmt)
logger.addHandler(handler)

def log_console(msg):
    try:
        print(msg, flush=True)
    except Exception:
        pass
    logger.info(msg)

# --------------- UTILIDADES ---------------
def normalize_host(host_raw: str) -> str:
    """Admite 'https://host', 'http://host' o 'host' y devuelve solo hostname."""
    try:
        parsed = urlparse(host_raw)
        if parsed.scheme and parsed.hostname:
            return parsed.hostname
    except Exception:
        pass
    # Si no parseó como URL, devuelve tal cual (pero sin barras finales)
    return host_raw.replace("/", "").strip()

SEAFILE_HOST = normalize_host(SEAFILE_HOST_RAW)

def check_network(host: str, port: int, timeout: float = NETWORK_TIMEOUT) -> bool:
    """True si se puede abrir socket TCP al host:port."""
    try:
        socket.gethostbyname(host)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def wait_for_network(host: str, port: int, tries: int = NETWORK_TRIES, delay: float = 2.0) -> bool:
    for i in range(tries):
        if check_network(host, port):
            return True
        time.sleep(delay)
    return False

def is_process_running(image_name: str) -> bool:
    try:
        out = subprocess.check_output(["tasklist"], creationflags=subprocess.CREATE_NO_WINDOW)
        return image_name.lower().encode() in out.lower()
    except Exception:
        return False

def start_seadrive(exe_path: str) -> None:
    if not Path(exe_path).exists():
        log_console(f"[WARN] No se encuentra {exe_path}. Ajusta SEADRIVE_EXE.")
        return
    if is_process_running("seadrive-gui.exe"):
        return
    subprocess.Popen([exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    log_console("[INFO] seadrive-gui iniciado")

def kill_seadrive() -> None:
    for imagen in ("seadrive-gui.exe", "seafile-applet.exe", "seaf-daemon.exe"):
        try:
            subprocess.run(["taskkill", "/IM", imagen, "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
    time.sleep(2)
    log_console("[INFO] SeaDrive reiniciado (kill)")

def is_drive_mounted(letter: str) -> bool:
    p = Path(letter + "\\")
    try:
        return p.exists()
    except Exception:
        return False

def kick_scan(letter: str) -> None:
    try:
        _ = os.listdir(letter + "\\")
        log_console("[INFO] Kick scan OK (listado raíz)")
    except Exception as e:
        log_console(f"[WARN] Kick scan falló: {e}")

def ensure_mounted(letter: str, exe_path: str, retries: int, delay: float) -> bool:
    if is_drive_mounted(letter):
        return True
    for i in range(retries):
        kill_seadrive()
        start_seadrive(exe_path)
        time.sleep(delay)
        if is_drive_mounted(letter):
            return True
    return False

# --------------- MAIN ---------------
def main() -> int:
    log_console("========== SeaDrive Auto-Resync (TelcoDrive) ==========")
    log_console(f"Host objetivo: {SEAFILE_HOST}:{SEAFILE_PORT} | Unidad: {DRIVE_LETTER}")
    if not wait_for_network(SEAFILE_HOST, SEAFILE_PORT):
        log_console("[WARN] Sin red hacia Seafile tras espera. Intento plan B: reiniciar SeaDrive.")
        kill_seadrive()
        start_seadrive(SEADRIVE_EXE)
        time.sleep(RETRY_DELAY)

    start_seadrive(SEADRIVE_EXE)
    time.sleep(2)

    if not ensure_mounted(DRIVE_LETTER, SEADRIVE_EXE, retries=MOUNT_RETRIES, delay=RETRY_DELAY):
        log_console(f"[ERROR] No se montó la unidad {DRIVE_LETTER} tras reintentos.")
        return 2

    kick_scan(DRIVE_LETTER)

    log_console("[OK] Sincronización forzada lista.")
    return 0

if __name__ == "__main__":
    try:
        rc = main()
        sys.exit(rc)
    except Exception as e:
        try:
            logger.exception("Excepción no controlada")
        except Exception:
            pass
        try:
            print(f"[FATAL] {e}", file=sys.stderr)
        except Exception:
            pass
        sys.exit(1)
