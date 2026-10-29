from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    database: Path
    logs: Path
    diagnostics: Path
    assets: Path
    reports: Path
    migration_reports: Path

    @classmethod
    def default(cls) -> AppPaths:
        override = os.environ.get("COMPRAS_TN_DATA_DIR")
        if override:
            return cls.from_root(Path(override))
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        standard = local / "ComprasTN" / "2.0"
        candidates = {p.parent.resolve() for p in (local / "Packages").glob(
            "PythonSoftwareFoundation.Python.*/LocalCache/Local/ComprasTN/2.0/compras_tn.db"
        )}
        if (standard / "compras_tn.db").is_file():
            candidates.add(standard.resolve())
        if len(candidates) > 1:
            raise RuntimeError("Se encontraron varias bases ComprasTN. Defina COMPRAS_TN_DATA_DIR con la carpeta productiva; no se eligió una automáticamente.")
        return cls.from_root(next(iter(candidates)) if candidates else standard)

    @classmethod
    def from_root(cls, root: Path) -> AppPaths:
        root = root.resolve()
        return cls(
            root=root,
            database=root / "compras_tn.db",
            logs=root / "logs",
            diagnostics=root / "diagnostics",
            assets=root / "assets",
            reports=root / "reports",
            migration_reports=root / "migration_reports",
        )

    def ensure(self) -> None:
        for path in (
            self.root,
            self.logs,
            self.diagnostics,
            self.assets,
            self.reports,
            self.migration_reports,
        ):
            path.mkdir(parents=True, exist_ok=True)
