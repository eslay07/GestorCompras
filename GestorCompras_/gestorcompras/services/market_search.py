"""Herramientas básicas para consultar precios de mercado."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional, Dict, Any


def find_best_price(item_description: str) -> Optional[Dict[str, Any]]:
    """Busca el mejor precio disponible públicamente para un ítem.

    La implementación utiliza la API pública de MercadoLibre. Si la petición
    falla (por falta de conexión, timeouts u otros errores) simplemente retorna
    ``None``.  Esta función está pensada como un punto de partida que puede ser
    extendido con técnicas de *web scraping* controlado u otras APIs.
    """
    base_url = "https://api.mercadolibre.com/sites/MLA/search"
    params = {"q": item_description}
    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    results = data.get("results") or []
    if not results:
        return None

    best = min(results, key=lambda r: r.get("price", float("inf")))
    return {
        "source": "MercadoLibre",
        "title": best.get("title"),
        "price": best.get("price"),
        "link": best.get("permalink"),
    }

