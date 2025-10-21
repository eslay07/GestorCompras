#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Actualiza los módulos relacionados con Descargas OC garantizando que respeten
la sesión del GestorCompras. Este script es un envoltorio ligero que reutiliza
la lógica principal de ``update_to_current.py`` para aplicar la versión actual
sobre una instalación existente.
"""
from __future__ import annotations

from pathlib import Path

import importlib
import sys


def _load_updater():
    base = Path(__file__).parent.resolve()
    sys.path.insert(0, str(base))
    try:
        return importlib.import_module('update_to_current')
    finally:
        try:
            sys.path.remove(str(base))
        except ValueError:
            pass


def main() -> None:
    updater = _load_updater()
    apply = getattr(updater, 'apply', None)
    if callable(apply):
        apply()
    else:
        raise RuntimeError('No se encontró la función apply en update_to_current.py')


if __name__ == '__main__':
    main()
