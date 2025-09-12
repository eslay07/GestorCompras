import os
import re
from typing import List, Dict, Any

import pandas as pd


def parse_quote(file_path: str) -> List[Dict[str, Any]]:
    """Parsea una cotización y retorna una lista de ítems con precio.

    La función intenta detectar automáticamente el tipo de archivo. Si es un
    Excel, se usa :func:`pandas.read_excel`.  Si es un PDF, se intenta extraer
    texto mediante :mod:`pdfplumber` y se buscan patrones simples de
    ``descripcion precio``.

    Debido a que un flujo de OCR/LLM real está fuera del alcance del proyecto
    actual, este procedimiento usa heurísticas básicas para lograr una
    extracción aproximada de información.
    """
    ext = os.path.splitext(file_path)[1].lower()
    items: List[Dict[str, Any]] = []

    if ext in {".xls", ".xlsx"}:
        df = pd.read_excel(file_path)
        # Buscamos columnas habituales; si no existen tomamos las dos primeras
        columns = [c.lower() for c in df.columns]
        if "item" in columns and "price" in columns:
            item_col = columns.index("item")
            price_col = columns.index("price")
            for _, row in df.iterrows():
                desc = str(row.iloc[item_col]).strip()
                try:
                    price = float(row.iloc[price_col])
                except Exception:
                    continue
                items.append({"description": desc, "price": price})
        else:
            # Heurística: asumimos que la primera columna es descripción y la
            # segunda precio
            for _, row in df.iloc[:, :2].iterrows():
                desc = str(row.iloc[0]).strip()
                try:
                    price = float(row.iloc[1])
                except Exception:
                    continue
                items.append({"description": desc, "price": price})
    elif ext == ".pdf":
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            # Patrón muy simple: cualquier cosa seguida de un número con
            # decimales opcionales
            pattern = re.compile(r"(.+?)\s+([\d.,]+)")
            for line in text.splitlines():
                match = pattern.search(line)
                if not match:
                    continue
                desc = match.group(1).strip()
                price_str = match.group(2).replace(".", "").replace(",", ".")
                try:
                    price = float(price_str)
                except Exception:
                    continue
                items.append({"description": desc, "price": price})
        except Exception:
            # Si la extracción falla simplemente devolvemos lo obtenido hasta
            # ahora (que será la lista vacía)
            pass
    else:
        # Otros formatos no soportados en esta implementación.
        pass

    return items


def match_items(requested_items: List[str], quoted_items: List[Dict[str, Any]], threshold: float = 0.6) -> List[Dict[str, Any]]:
    """Realiza un emparejamiento semántico básico entre ítems solicitados y
    cotizados.

    Se utiliza :class:`difflib.SequenceMatcher` para medir la similitud entre
    descripciones.  En un escenario real se podría reemplazar por embeddings o
    un modelo semántico avanzado.
    """
    from difflib import SequenceMatcher

    matches = []
    for req in requested_items:
        best_match: Dict[str, Any] | None = None
        best_score = 0.0
        for item in quoted_items:
            score = SequenceMatcher(None, req.lower(), item["description"].lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = item
        if best_score >= threshold and best_match is not None:
            matches.append({
                "requested": req,
                "quoted": best_match["description"],
                "quoted_price": best_match["price"],
                "score": best_score,
            })
        else:
            matches.append({
                "requested": req,
                "quoted": None,
                "quoted_price": None,
                "score": best_score,
            })
    return matches

