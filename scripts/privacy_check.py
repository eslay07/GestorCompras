"""Auditoría local de privacidad para el contenido versionable."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}
TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".css",
    ".csv",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

BLOCKED_TERMS = tuple(
    "".join(parts)
    for parts in (
        ("tel", "conet"),
        ("tel", "cos"),
        ("telco", "drive"),
        ("sea", "drive"),
        ("joto", "apanta"),
        ("omar", "777j"),
    )
)
BLOCKED_ACRONYMS = tuple("".join(parts) for parts in (("n", "af"), ("c", "as"), ("s", "so")))
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
URL_PATTERN = re.compile("ht" + r"tps?://[^\s)\]}>]+", re.IGNORECASE)
LOCAL_PATH_PATTERN = re.compile(r"\b[A-Za-z]" + ":" + r"\\[^\r\n\"'<>|]*")
IDENTIFIER_PATTERN = re.compile(r"(?<!\d)\d{13}(?!\d)")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b(" + "|".join(("pass" + "word", "pass" + "wd", "to" + "ken", "api" + "_key", "client" + "_secret")) + r")\b\s*[:=]\s*[\"']([^\"']{4,})",
    re.IGNORECASE,
)
LONG_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_\-]{40,}(?![A-Za-z0-9])")
PRIVATE_KEY_MARKER = "BEGIN " + "PRIVATE KEY"
SAFE_LOCAL_PREFIX = "C:" + "\\Demo\\GestorCompras\\"
BLOCKED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pem", ".key", ".pfx", ".p12"}


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    category: str
    line: int | None = None


def _relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("/", "\\")


def _is_skipped(path: Path, root: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part in SKIP_DIRECTORIES or part.endswith(".egg-info") for part in relative_parts)


def _scan_name(path: Path, root: Path) -> list[Finding]:
    relative = _relative(path, root)
    folded = relative.casefold()
    findings: list[Finding] = []
    if any(term in folded for term in BLOCKED_TERMS):
        findings.append(Finding(relative, "término prohibido en nombre o ruta"))
    for acronym in BLOCKED_ACRONYMS:
        if re.search(rf"(?<![a-z0-9]){re.escape(acronym)}(?![a-z0-9])", folded):
            findings.append(Finding(relative, "acrónimo corporativo en nombre o ruta"))
            break
    if path.suffix.casefold() in BLOCKED_SUFFIXES:
        findings.append(Finding(relative, "artefacto sensible por extensión"))
    filename = path.name.casefold()
    if filename == ".env" or (filename.startswith(".env.") and filename != ".env.example"):
        findings.append(Finding(relative, "archivo de entorno no permitido"))
    suspicious_names = (
        "credentials" + ".json",
        "client" + "_secret",
        "service" + "-account",
        "config" + ".local.",
    )
    if any(item in filename for item in suspicious_names):
        findings.append(Finding(relative, "nombre asociado a credenciales o configuración local"))
    return findings


def _scan_text(path: Path, root: Path) -> list[Finding]:
    if path.suffix.casefold() not in TEXT_SUFFIXES and path.name != ".env.example":
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [Finding(_relative(path, root), "archivo de texto no legible")]

    relative = _relative(path, root)
    findings: list[Finding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        folded = line.casefold()
        if any(term in folded for term in BLOCKED_TERMS):
            findings.append(Finding(relative, "término prohibido", line_number))
        for acronym in BLOCKED_ACRONYMS:
            if re.search(rf"(?<![a-z0-9]){re.escape(acronym)}(?![a-z0-9])", folded):
                findings.append(Finding(relative, "acrónimo corporativo", line_number))
                break
        for email in EMAIL_PATTERN.findall(line):
            if email.rpartition("@")[2].casefold() != "example.com":
                findings.append(Finding(relative, "correo fuera del dominio sintético", line_number))
        if URL_PATTERN.search(line):
            findings.append(Finding(relative, "URL que requiere revisión explícita", line_number))
        for local_path in LOCAL_PATH_PATTERN.findall(line):
            normalized = local_path.replace("\\\\", "\\")
            if not normalized.casefold().startswith(SAFE_LOCAL_PREFIX.casefold()):
                findings.append(Finding(relative, "ruta local no permitida", line_number))
        for identifier in IDENTIFIER_PATTERN.findall(line):
            if identifier != "0000000000000":
                findings.append(Finding(relative, "identificador numérico de 13 dígitos", line_number))
        if SECRET_ASSIGNMENT_PATTERN.search(line):
            findings.append(Finding(relative, "posible secreto asignado", line_number))
        long_token = next(
            (
                token
                for token in LONG_TOKEN_PATTERN.findall(line)
                if any(char.islower() for char in token)
                and any(char.isupper() for char in token)
                and any(char.isdigit() for char in token)
                and len(set(token)) >= 16
            ),
            None,
        )
        if PRIVATE_KEY_MARKER in line or long_token is not None:
            findings.append(Finding(relative, "posible secreto de alta entropía", line_number))
    return findings


def scan_repository(root: Path = PROJECT_ROOT) -> tuple[list[Finding], int, int]:
    findings: list[Finding] = []
    files_scanned = 0
    text_files_scanned = 0
    for path in sorted(root.rglob("*")):
        if _is_skipped(path, root):
            continue
        if path.is_symlink():
            findings.append(Finding(_relative(path, root), "enlace simbólico no permitido"))
            continue
        if not path.is_file():
            continue
        files_scanned += 1
        findings.extend(_scan_name(path, root))
        if path.suffix.casefold() in TEXT_SUFFIXES or path.name == ".env.example":
            text_files_scanned += 1
            findings.extend(_scan_text(path, root))
    unique = sorted(set(findings), key=lambda item: (item.path.casefold(), item.line or 0, item.category))
    return unique, files_scanned, text_files_scanned


def main() -> int:
    parser = argparse.ArgumentParser(description="Revisa privacidad sin mostrar valores detectados.")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    findings, files_scanned, text_files_scanned = scan_repository(root)

    print("Informe de privacidad")
    print(f"Archivos revisados: {files_scanned}")
    print(f"Archivos de texto revisados: {text_files_scanned}")
    safe_path_label = "C" + ":" + "\\Demo"
    print(f"Excepciones sintéticas permitidas: example.com, ruta {safe_path_label} y 0000000000000")
    if findings:
        print(f"Resultado: FALLÓ ({len(findings)} hallazgos)")
        for finding in findings:
            location = f":{finding.line}" if finding.line is not None else ""
            print(f"- {finding.path}{location} [{finding.category}]")
        return 1
    print("Resultado: APROBADO (sin hallazgos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
