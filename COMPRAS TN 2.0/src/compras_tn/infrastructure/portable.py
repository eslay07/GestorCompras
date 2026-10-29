"""Portable configuration profiles: no sessions, credentials or mailbox history."""
from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from compras_tn.security import is_sensitive_key, sanitize_text

TABLES = {
    "suppliers": ("ruc", ("name", "ruc", "email_primary", "email_secondary", "nickname", "nickname_2", "nickname_3")),
    "assignments": ("subdepartment", ("subdepartment", "department", "person")),
    "email_templates": ("name", ("name", "html", "signature_path")),
    "workflow_definitions": ("name", ("name", "mode", "version", "enabled", "steps_json", "stop_on_error")),
}


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items() if not is_sensitive_key(key) and str(key).lower() not in {"clave", "credentials", "credential", "google_creds", "private_key", "client_secret"}}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, str):
        if "PRIVATE KEY-----" in value:
            return ""
        return sanitize_text(value)
    return value


def allowed_settings():
    from compras_tn.presentation.settings_page import SETTINGS
    return {(item.namespace, item.key) for item in SETTINGS if item.key != "google_creds"} | {("documents", "types")}


def setting_allowed(namespace, key):
    return (namespace, key) in allowed_settings() or (namespace == "automation" and key.startswith("actua_file_alias::"))


def normalize_setting(namespace, key, value):
    from compras_tn.presentation.settings_page import SETTINGS
    spec = next((item for item in SETTINGS if (item.namespace, item.key) == (namespace, key)), None)
    if spec and spec.kind == "bool" and isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "sí", "si", "yes", "on"}
    if spec and spec.kind == "number":
        return int(value)
    if spec and spec.kind == "lines" and isinstance(value, str):
        return [part.strip() for part in value.replace(",", "\n").splitlines() if part.strip()]
    return value


def export_profile(path: Path) -> dict:
    profile = {"format": 1, "tables": {}, "settings": []}
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute("BEGIN")
        existing = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, (_key, columns) in TABLES.items():
            if table not in existing:
                continue
            rows = []
            for record in source.execute(f'SELECT * FROM "{table}"'):
                row = {key: record[key] for key in columns if key in record.keys()}
                if table == "workflow_definitions":
                    row["steps_json"] = json.dumps(clean(json.loads(row["steps_json"])), ensure_ascii=False)
                rows.append(clean(row))
            profile["tables"][table] = rows
        if "settings" in existing:
            for row in source.execute("SELECT namespace,key,value_json FROM settings"):
                if setting_allowed(row["namespace"], row["key"]):
                    profile["settings"].append({"namespace": row["namespace"], "key": row["key"], "value": clean(json.loads(row["value_json"]))})
    return profile


def merge_profile(path: Path, profile: dict) -> dict:
    """Fill missing records only. Never replace an existing computer's preferences."""
    if profile.get("format") != 1:
        raise ValueError("El perfil de instalación tiene un formato no compatible.")
    counts = {"added": 0, "kept": 0}
    now = datetime.now(UTC).isoformat()
    with closing(sqlite3.connect(path)) as target, target:
        for table, (identity, permitted) in TABLES.items():
            for original in profile.get("tables", {}).get(table, []):
                row = clean({key: value for key, value in original.items() if key in permitted})
                if not row.get(identity):
                    raise ValueError(f"Perfil inválido: falta {identity} en {table}.")
                exists = target.execute(f'SELECT 1 FROM "{table}" WHERE "{identity}"=?', (row[identity],)).fetchone()
                if exists and table == "workflow_definitions":
                    def signature(value):
                        return json.dumps({"mode": value[0], "enabled": bool(value[1]), "steps": clean(json.loads(value[2])), "stop_on_error": bool(value[3])}, sort_keys=True, ensure_ascii=False)
                    incoming = signature((row.get("mode", "general"), row.get("enabled", True), row["steps_json"], row.get("stop_on_error", True)))
                    existing = target.execute('SELECT mode,enabled,steps_json,stop_on_error FROM workflow_definitions WHERE name=?', (row["name"],)).fetchone()
                    if signature(existing) != incoming:
                        # Preserve the identity of imports created before policies
                        # existed, when their effective policy was also Stop.
                        digest_data = json.loads(incoming)
                        if digest_data['stop_on_error']:
                            digest_data.pop('stop_on_error')
                        digest = hashlib.sha256(json.dumps(digest_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
                        base_name = row["name"][:120]
                        counter = 1
                        while True:
                            tag = digest if counter == 1 else f"{digest}-{counter}"
                            row["name"] = base_name + f" (importado {tag})"
                            imported = target.execute('SELECT mode,enabled,steps_json,stop_on_error FROM workflow_definitions WHERE name=?', (row["name"],)).fetchone()
                            if not imported or signature(imported) == incoming:
                                exists = imported
                                break
                            counter += 1
                if exists:
                    counts["kept"] += 1
                    continue
                row["updated_at"] = now
                if table == "suppliers":
                    row["created_at"] = now
                    for key in ("email_secondary", "nickname", "nickname_2", "nickname_3"):
                        row.setdefault(key, "")
                if table == "workflow_definitions":
                    row["steps_json"] = json.dumps(clean(json.loads(row["steps_json"])), ensure_ascii=False)
                columns = ",".join(f'"{key}"' for key in row)
                placeholders = ",".join("?" for _ in row)
                target.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', tuple(row.values()))
                counts["added"] += 1
        for item in profile.get("settings", []):
            namespace, key = item["namespace"], item["key"]
            if not setting_allowed(namespace, key):
                continue
            existing = target.execute("SELECT value_json FROM settings WHERE namespace=? AND key=?", (namespace, key)).fetchone()
            if existing:
                if (namespace, key) == ("documents", "types"):
                    types = json.loads(existing[0])
                    known = {definition["id"] for definition in types}
                    extra = [definition for definition in clean(item["value"]) if definition["id"] not in known]
                    if extra:
                        target.execute("UPDATE settings SET value_json=?, updated_at=? WHERE namespace=? AND key=?", (json.dumps(types + extra, ensure_ascii=False), now, namespace, key))
                counts["kept"] += 1
                continue
            value = normalize_setting(namespace, key, clean(item["value"]))
            target.execute("INSERT INTO settings(namespace,key,value_json,updated_at) VALUES (?,?,?,?)", (namespace, key, json.dumps(value, ensure_ascii=False), now))
            counts["added"] += 1
    return counts


