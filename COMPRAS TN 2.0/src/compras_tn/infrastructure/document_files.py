"""Typed task documents shared by the organizer and workflow preflight."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_ROOT = r"E:\Seadrive\jotoapan_1\My Libraries\Mi Biblioteca\BD_TN"
DEFAULT_TYPES = (
    {"id": "cotizacion", "name": "Cotización", "words": ["cotización", "cotizacion", "proforma"]},
    {"id": "orden", "name": "Orden", "words": ["orden", "orden de compra", "OC"]},
    {"id": "ficha_tecnica", "name": "Ficha técnica", "words": ["ficha técnica", "ficha tecnica", "datasheet"]},
    {"id": "otros", "name": "Otros", "words": ["otros"]},
)


def plain(value: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).casefold().split())


def file_types(settings) -> list[dict[str, Any]]:
    value = settings.get("documents", "types", None)
    if value is None:
        return [normalize_type(dict(row, words=list(row["words"]))) for row in DEFAULT_TYPES]
    if not isinstance(value, list) or any(not isinstance(r, dict) or not r.get("id") or not r.get("name") or not isinstance(r.get("words"), list) or not r["words"] or any(not isinstance(w, str) or not w.strip() for w in r["words"]) for r in value):
        raise ValueError("El catálogo de tipos de documentos no es válido.")
    if len({r["id"] for r in value}) != len(value):
        raise ValueError("Los tipos de documentos tienen identificadores repetidos.")
    return [normalize_type(row) for row in value]


def normalize_type(row: dict) -> dict:
    result = dict(row)
    result.setdefault("extensions", [])
    result.setdefault("copies", "latest_identical" if row["id"] == "orden" else "all")
    result.setdefault("comparison", "pdf_text" if row["id"] == "orden" else "exact")
    if result["copies"] not in {"all", "latest_identical"} or result["comparison"] not in {"exact", "pdf_text"}:
        raise ValueError("Política de documentos no válida.")
    if not isinstance(result["extensions"], list):
        raise ValueError("Las extensiones deben ser una lista.")
    result["extensions"] = list(dict.fromkeys("." + str(e).strip().lower().lstrip(".") for e in result["extensions"] if str(e).strip()))
    return result


def add_type(settings, name: str, words: str, *, identifier: str = "", extensions=None, copies="all", comparison="exact") -> dict[str, Any]:
    name = name.strip()
    keywords = list(dict.fromkeys(w.strip() for w in re.split(r"[,;\n]", words) if w.strip()))
    if not name or not keywords:
        raise ValueError("Escriba un nombre y al menos una palabra identificadora.")
    types = file_types(settings)
    if any(plain(r["name"]) == plain(name) and r["id"] != identifier for r in types):
        raise ValueError("Ya existe un tipo con ese nombre.")
    if identifier and not any(r["id"] == identifier for r in types):
        raise ValueError("El tipo ya no existe.")
    row = normalize_type({"id": identifier or uuid4().hex, "name": name, "words": keywords,
                          "extensions": extensions or [], "copies": copies, "comparison": comparison})
    settings.set("documents", "types", [r for r in types if r["id"] != row["id"]] + [row])
    return row


def matches_type(path: Path, definition: dict) -> bool:
    if definition.get("extensions") and path.suffix.lower() not in definition["extensions"]:
        return False
    name = plain(path.stem)
    for raw in [definition["name"], *definition["words"]]:
        word = plain(str(raw))
        if word and ((len(word) > 3 and word in name) or (len(word) <= 3 and re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", name))):
            return True
    return False


def task_folder(name: str, number: str) -> bool:
    return bool(re.fullmatch(re.escape(number) + r"(?:\s*[-–—]\s*.+|\s+.+)?", name))


def inspect_file(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.name.lower().endswith((".part", ".crdownload", ".tmp")):
        raise ValueError(f"El archivo no está completo o no existe: {path}")
    before = path.stat()
    if not before.st_size:
        raise ValueError(f"El archivo está vacío: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f"El archivo cambió durante la validación: {path}")
    return {"path": str(path.resolve()), "size": after.st_size, "sha256": digest, "mtime_ns": after.st_mtime_ns}


def pdf_content_key(path: Path):
    """Conservative equality: scanned/partially readable PDFs remain distinct."""
    if path.suffix.casefold() != ".pdf":
        return None
    import pdfplumber
    from compras_tn.infrastructure.orders import ORDER_PATTERN
    try:
        with pdfplumber.open(path) as pdf:
            texts = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                if not text.strip():
                    return None
                images = []
                for image in page.images:
                    stream = image.get("stream")
                    if not stream:
                        return None
                    images.append((tuple(round(float(image[k]), 3) for k in ("x0", "x1", "top", "bottom")),
                                   hashlib.sha256(stream.get_data()).hexdigest()))
                texts.append(" ".join(unicodedata.normalize("NFC", text).split()) + "\nIMAGES:" + repr(sorted(images)))
        content = "\n".join(texts)
        match = ORDER_PATTERN.search(content)
        if not match:
            match = re.search(r"(?:ORDEN DE COMPRA|N[o°º]\.?)\s*[:#-]?\s*(\d{4,14})\b", content, re.I)
        if match:
            return (match.group(1), hashlib.sha256(content.encode()).hexdigest())
    except Exception:
        return None
    return None


def select_copies(items: list[dict], definition: dict) -> tuple[list[dict], list[dict]]:
    if definition.get("copies") != "latest_identical":
        return items, []
    # Exact duplicates always share a group; text equivalence is an additional,
    # conservative grouping criterion. Metadata-only differences may be ignored.
    groups: dict[tuple, list[dict]] = {}
    exact: dict[str, tuple] = {}
    for item in items:
        key = exact.get(item["sha256"])
        if key is None:
            text_key = pdf_content_key(Path(item["path"])) if definition.get("comparison") == "pdf_text" else None
            key = ("text", *text_key) if text_key else ("exact", item["sha256"])
            exact[item["sha256"]] = key
        groups.setdefault(key, []).append(item)
    selected, omitted = [], []
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (-item["mtime_ns"], item["path"].casefold()))
        selected.append(ordered[0])
        omitted.extend({**item, "reason": "Copia idéntica; se conserva la más reciente", "kept_path": ordered[0]["path"]} for item in ordered[1:])
    return selected, omitted


class FolderChoiceRequired(ValueError):
    def __init__(self, candidates: list[str], step: int):
        self.candidates, self.step = candidates, step
        super().__init__("Hay varias carpetas para esta tarea. Elija una antes de ejecutar.")


class DocumentFileResolver:
    def __init__(self, settings):
        self.settings = settings

    def root(self, params: dict) -> Path:
        value = str(params.get("carpeta_base") or self.settings.get("automation", "actua_tareas_carpeta_base", "") or DEFAULT_ROOT)
        root = Path(value).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"No existe la carpeta general: {root}")
        return root

    def folders(self, root: Path, number: str) -> list[Path]:
        if not re.fullmatch(r"[0-9]{1,14}", number):
            raise ValueError("El número de tarea no es válido.")
        result = []
        for path in [root, *root.rglob("*")]:
            if path.is_dir() and task_folder(path.name, number) and path.resolve().is_relative_to(root):
                result.append(path.resolve())
        return sorted(set(result), key=lambda p: str(p).casefold())

    def prepare(self, workflow, task) -> dict[str, Any]:
        manifests = {}
        types = {r["id"]: r for r in file_types(self.settings)}
        choices = task.payload.get("document_folder_choices", {})
        previous = task.payload.get("document_file_manifests", {})
        if not isinstance(choices, dict) or not isinstance(previous, dict):
            raise ValueError("La selección anterior no es válida; valide nuevamente los archivos.")
        for index, step in enumerate(workflow.steps, 1):
            if step.action_id != "seleccionar_archivo" or step.params.get("modo_archivo") != "tipos":
                continue
            ids = step.params.get("tipos_archivo", [])
            if not isinstance(ids, list) or not ids or any(i not in types for i in ids):
                raise ValueError(f"Paso {index}: elija tipos de archivo válidos.")
            root = self.root(step.params)
            if str(index) in previous:
                manifest = previous[str(index)]
                folder = Path(manifest["folder"]).resolve()
                if not folder.is_relative_to(root) or not task_folder(folder.name, task.task_number):
                    raise ValueError("La carpeta validada no corresponde a esta tarea.")
                self.verify(manifest)
                if not any(matches_type(Path(item["path"]), types[identifier]) for item in manifest["files"] for identifier in ids):
                    raise ValueError("Los archivos validados no coinciden con ningún tipo solicitado; valide nuevamente.")
                if set(manifest.get("types", [])) != set(ids):
                    raise ValueError("Los tipos cambiaron desde la validación; valide nuevamente.")
                if manifest.get("type_policies") is not None and manifest["type_policies"] != [types[i] for i in ids]:
                    raise ValueError("La configuración de documentos cambió; valide nuevamente antes de ejecutar.")
                manifests[str(index)] = manifest
                continue
            candidates = self.folders(root, task.task_number)
            selected = choices.get(str(index))
            if selected:
                folder = Path(selected).resolve()
                if folder not in candidates:
                    raise ValueError("La carpeta elegida ya no está disponible para esta tarea.")
            elif len(candidates) > 1:
                raise FolderChoiceRequired([str(p) for p in candidates], index)
            elif candidates:
                folder = candidates[0]
            else:
                raise FileNotFoundError(f"No se encontró una carpeta para la tarea {task.task_number}.")
            paths = sorted(p for p in folder.rglob("*") if p.is_file() and p.resolve().is_relative_to(folder)
                           and not any(re.match(r"^\d{6,14}(?:\s|[-–—])", ancestor.name) and not task_folder(ancestor.name, task.task_number)
                                       for ancestor in p.parents if ancestor != folder and ancestor.is_relative_to(folder)))
            picked: dict[str, dict] = {}
            omitted = []
            missing = []
            for identifier in ids:
                matches = [p for p in paths if matches_type(p, types[identifier])]
                if not matches:
                    missing.append(types[identifier]["name"])
                inspected = [inspect_file(path) for path in matches]
                selected_files, excluded = select_copies(inspected, types[identifier])
                omitted.extend(dict(item, type_id=identifier) for item in excluded)
                for item in selected_files:
                    key = item["path"]
                    if key not in picked:
                        picked[key] = item
                    picked[key].setdefault("types", []).append(identifier)
            if not picked:
                raise FileNotFoundError("No hay archivos de ninguno de los tipos seleccionados: " + ", ".join(missing) + f". Carpeta: {folder}")
            manifests[str(index)] = {"folder": str(folder), "types": ids, "files": list(picked.values()),
                                     "type_policies": [dict(types[i]) for i in ids],
                                     "omitted": [item for item in omitted if item["path"] not in picked]}
        return manifests

    @staticmethod
    def verify(manifest: dict) -> None:
        if not manifest.get("files"):
            raise ValueError("La selección de archivos está vacía.")
        folder = Path(manifest["folder"]).resolve()
        for item in manifest["files"]:
            path = Path(item["path"]).resolve()
            if not path.is_relative_to(folder):
                raise ValueError("Un archivo salió de la carpeta validada.")
            current = inspect_file(path)
            if (current["size"], current["sha256"]) != (item["size"], item["sha256"]):
                raise ValueError(f"El archivo cambió desde la validación: {path}")
