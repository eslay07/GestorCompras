from collections import OrderedDict
from collections.abc import Sequence

from compras_tn.domain.models import PurchaseOrderArticle, PurchaseOrderDraft


def consolidate_orders(drafts: Sequence[PurchaseOrderDraft], *, split_observations: bool = True) -> list[PurchaseOrderDraft]:
    groups: dict[tuple[str, str, str], list[PurchaseOrderDraft]] = OrderedDict()
    unresolved = []
    for draft in drafts:
        if not draft.ruc:
            unresolved.append(draft)
            continue
        key = (draft.ruc, draft.department.strip(), draft.requester.strip())
        groups.setdefault(key, []).extend(draft.original_drafts)
    result = []
    for (_ruc, department, requester), originals in groups.items():
        sources = []
        seen: dict[int, tuple[str, PurchaseOrderArticle]] = {}
        errors = [error for source in originals for error in source.validation_errors]
        contexts: dict[str, tuple[str, str]] = {}
        for source in originals:
            context = (source.pedido, source.detail)
            if source.task_number in contexts and contexts[source.task_number] != context:
                errors.append(f"La tarea {source.task_number} tiene cabeceras contradictorias.")
            contexts[source.task_number] = context
        for source in sorted(originals, key=lambda d: min(d.source_rows or [a.source_row for a in d.articles])):
            articles = []
            for article in source.articles:
                identity = (source.task_number, article)
                if article.source_row in seen:
                    if seen[article.source_row] != identity:
                        errors.append(f"Datos distintos para la fila {article.source_row}.")
                    continue
                seen[article.source_row] = identity
                articles.append(article)
            if articles:
                sources.append(source.model_copy(update={"sources": [], "articles": articles,
                    "source_rows": [a.source_row for a in articles]}, deep=True))
        if not sources:
            continue
        lines: dict[str, PurchaseOrderArticle] = OrderedDict()
        contributions: dict[str, list[str]] = {}
        for source in sources:
            for article in source.articles:
                contributions.setdefault(article.code, []).append(
                    f"tarea {source.task_number}, fila {article.source_row}, precio {article.unit_price}")
                if article.code not in lines:
                    lines[article.code] = article.model_copy(deep=True)
                else:
                    lines[article.code].quantity += article.quantity
        for code in lines:
            prices = {a.unit_price for s in sources for a in s.articles if a.code == code}
            if len(prices) > 1:
                errors.append(f"Precios distintos para {code}: " + "; ".join(contributions[code]))
        result.append(sources[0].model_copy(update={
            "department": department, "requester": requester, "sources": sources, "split_part": 0, "split_total": 0,
            "articles": list(lines.values()), "source_rows": sorted(seen),
            "validation_errors": list(dict.fromkeys(errors)),
        }, deep=True))
    if split_observations:
        result = [part for draft in result for part in split_order_observations(draft)]
    return [*result, *unresolved]


def split_order_observations(draft: PurchaseOrderDraft) -> list[PurchaseOrderDraft]:
    """Partition whole source rows; no quantities or descriptions are truncated."""
    from compras_tn.domain.purchase_order_observations import OBSERVATION_LIMIT, build_observation, observation_length
    if observation_length(build_observation(draft)) <= OBSERVATION_LIMIT:
        return [draft]

    def assemble(sources):
        originals = OrderedDict()
        for source in sources:
            key = (source.task_number, source.supplier, source.supplier_reference,
                   source.ruc, source.requester, source.pedido, source.department, source.detail)
            if key not in originals:
                originals[key] = source.model_copy(deep=True)
            else:
                originals[key].articles.extend(source.articles)
                originals[key].source_rows.extend(source.source_rows)
        return consolidate_orders(list(originals.values()), split_observations=False)[0]

    parts = []
    pending = []
    for source in draft.original_drafts:
        for article in source.articles:
            unit = source.model_copy(update={'sources': [], 'articles': [article],
                'source_rows': [article.source_row], 'split_part': 0, 'split_total': 0}, deep=True)
            if observation_length(build_observation(unit)) > OBSERVATION_LIMIT:
                error = (f'Fila {article.source_row}: la cabecera y un solo artículo superan los 2000 caracteres. '
                         'No se puede dividir esta fila sin alterar su contenido; revise la descripción en GENERAL.')
                return [draft.model_copy(update={'validation_errors': list(dict.fromkeys([*draft.validation_errors, error]))})]
            candidate = assemble([*pending, unit])
            if pending and observation_length(build_observation(candidate)) > OBSERVATION_LIMIT:
                parts.append(assemble(pending))
                pending = []
            pending.append(unit)
    if pending:
        parts.append(assemble(pending))
    for index, part in enumerate(parts, 1):
        part.split_part = index
        part.split_total = len(parts)
        part.validation_errors = list(dict.fromkeys([*draft.validation_errors, *part.validation_errors]))
    return parts
