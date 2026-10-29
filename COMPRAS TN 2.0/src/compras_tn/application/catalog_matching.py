from __future__ import annotations

from collections.abc import Sequence

from compras_tn.domain.models import Supplier


def normalized_nickname(value: str) -> str:
    """Normalize whitespace and case only; accents remain significant."""
    return " ".join(str(value or "").split()).casefold()


def match_supplier_nickname(
    nickname: str,
    suppliers: Sequence[Supplier],
) -> tuple[Supplier | None, str]:
    """Resolve a Sheet supplier name or any of its three aliases to a local RUC."""
    raw = " ".join(str(nickname or "").split())
    if not raw:
        return None, "Falta el nombre o sobrenombre del proveedor en la columna E."
    key = normalized_nickname(raw)
    matches = [
        supplier
        for supplier in suppliers
        if key
        in {
            normalized
            for value in (
                supplier.name,
                supplier.nickname,
                supplier.nickname_2,
                supplier.nickname_3,
            )
            if (normalized := normalized_nickname(value))
        }
    ]
    if len(matches) == 1:
        return matches[0], ""
    if len(matches) > 1:
        return None, (
            f"El nombre o sobrenombre '{raw}' coincide con varios proveedores en la base."
        )
    return None, (
        f"No existe el nombre o sobrenombre '{raw}' en Configuración > Proveedores; "
        "registre uno de sus tres sobrenombres para asociar el RUC."
    )
