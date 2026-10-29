"""NAF observation formatting shared by planning and browser automation."""
import unicodedata
import re
from decimal import Decimal

from compras_tn.domain.models import PurchaseOrderDraft

OBSERVATION_LIMIT = 2000

def observation_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def normalize_observation(value: str) -> str:
    replacements = str.maketrans({
        "“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "…": "...",
        "\u00a0": " ", "½": "1/2", "¼": "1/4", "¾": "3/4",
        "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8", "⁄": "/",
        "×": "x", "Ø": "DIA", "ø": "dia", "‐": "-", "‑": "-", "−": "-",
        "²": "2", "³": "3", "′": "'", "″": '"', "ℓ": "l",
    })
    value = re.sub(r'(?<=\d)(?=[½¼¾⅛⅜⅝⅞])', ' ', value)
    normalized = unicodedata.normalize("NFC", value.translate(replacements))
    lines = []
    for line in normalized.splitlines():
        clean = "".join(character for character in line if character == "\t" or not unicodedata.category(character).startswith("C"))
        lines.append(" ".join(clean.replace("\t", " ").split()))
    return "\n".join(lines).strip()


def format_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def build_observation(draft: PurchaseOrderDraft) -> str:
    if draft.sources:
        tasks: dict[str, PurchaseOrderDraft] = {}
        for source in draft.sources:
            if source.task_number not in tasks:
                tasks[source.task_number] = source.model_copy(deep=True)
            else:
                tasks[source.task_number].articles.extend(source.articles)
        return "\n".join(build_observation(source) for source in tasks.values())
    supplier = draft.supplier_reference or draft.supplier
    header = (
        f"TAREA #{draft.task_number}//PEDIDO:{draft.pedido or 'S/N'}//"
        f"{draft.department}:{draft.detail}// SOLIC. {draft.requester} // REFER. "
        f"COTIZ. {supplier} DETALLE:"
    )
    details = [
        f"{article.description} {format_decimal(article.quantity).rstrip('0').rstrip('.')} "
        f"{article.source_supplier or supplier} ${format_decimal(article.unit_price)}"
        for article in draft.articles
    ]
    return normalize_observation("\n".join([header, "", *details]))


