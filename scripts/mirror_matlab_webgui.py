"""Mirror local de los assets HTTP del webgui real de MATLAB (uso personal).

Copia desde la instalación licenciada del usuario (MATLAB_ROOT o --source) los
recursos que el shell real pide por HTTP, para poder servirlo sin instalación
(modo standalone):

    ui/webgui/**                        shell: HTML, CSS, bundles, fuentes
    ui/icons/**                         iconos + registry.json del toolstrip
    sys/fonts/**                        fuentes compartidas de la instalación
    toolbox/matlab/rich_text_component  bundle del Command Window
    toolbox/matlab/rtc_addons/**        chunks del editor (copilot)

El destino por defecto es <repo>/ml-mirror (ignorado por git; NADA de
MathWorks se commitea). El backend lo usa automáticamente cuando MATLAB_ROOT
no está definido (ver backend/local_assets.py).

Uso:
    python scripts/mirror_matlab_webgui.py
    python scripts/mirror_matlab_webgui.py --source "C:\\Program Files\\MATLAB\\R2026b"
    python scripts/mirror_matlab_webgui.py --verify     # solo reporta diferencias
    python scripts/mirror_matlab_webgui.py --force      # recopia todo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path

DEFAULT_SUBDIRS = (
    "ui/webgui",
    "ui/icons",
    "sys/fonts",
    "toolbox/matlab/rich_text_component",
    "toolbox/matlab/rtc_addons",
)
_MIRROR_DIRNAME = "ml-mirror"
_VERSION_RE = re.compile(r"<version>\s*([^<\s]+)\s*</version>")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def read_matlab_version(src_root: Path) -> str | None:
    """Versión de MATLAB leída de VersionInfo.xml (None si no está)."""
    info = src_root / "VersionInfo.xml"
    if not info.is_file():
        return None
    match = _VERSION_RE.search(info.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None


def _iter_files(src_root: Path, rel_dir: str):
    base = src_root / rel_dir
    if not base.is_dir():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file():
            yield path


def mirror_tree(
    src_root: Path,
    dest_root: Path,
    subdirs: tuple[str, ...] = DEFAULT_SUBDIRS,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """Copia incremental por tamaño. Devuelve estadísticas y subdirs ausentes.

    `dry_run=True` calcula lo que se copiaría sin tocar el destino (--verify).
    """
    stats: dict = {
        "copied": 0,
        "skipped": 0,
        "bytes_copied": 0,
        "total_bytes": 0,
        "missing": [],
        "files": 0,
    }
    for rel_dir in subdirs:
        if not (src_root / rel_dir).is_dir():
            stats["missing"].append(rel_dir)
            continue
        for src_file in _iter_files(src_root, rel_dir):
            rel = src_file.relative_to(src_root)
            dest_file = dest_root / rel
            size = src_file.stat().st_size
            stats["files"] += 1
            stats["total_bytes"] += size
            if not force and dest_file.is_file() and dest_file.stat().st_size == size:
                stats["skipped"] += 1
                continue
            stats["copied"] += 1
            stats["bytes_copied"] += size
            if dry_run:
                continue
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
    return stats


def write_manifest(dest_root: Path, src_root: Path, stats: dict, version: str | None) -> None:
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": str(src_root),
        "matlab_version": version,
        "subdirs": list(DEFAULT_SUBDIRS),
        "file_count": stats["files"],
        "total_bytes": stats["total_bytes"],
        "note": (
            "Copia local de trabajo (no versionada, ver .gitignore). "
            "Regenerar con scripts/mirror_matlab_webgui.py."
        ),
    }
    (dest_root / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _resolve_source(arg: str | None) -> Path:
    raw = arg or os.environ.get("MATLAB_ROOT", "")
    if not raw:
        raise SystemExit(
            "Falta la instalación: define MATLAB_ROOT o pasa --source <ruta>."
        )
    src = Path(raw)
    if not src.is_dir():
        raise SystemExit(f"La ruta de instalación no existe: {src}")
    return src


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="Instalación de MATLAB (por defecto MATLAB_ROOT)")
    parser.add_argument(
        "--dest", help=f"Destino del mirror (por defecto <repo>/{_MIRROR_DIRNAME})"
    )
    parser.add_argument(
        "--verify", action="store_true", help="Solo reporta diferencias, sin copiar"
    )
    parser.add_argument("--force", action="store_true", help="Recopia todos los archivos")
    args = parser.parse_args(argv)

    src_root = _resolve_source(args.source)
    dest_root = Path(args.dest) if args.dest else repo_root() / _MIRROR_DIRNAME
    version = read_matlab_version(src_root)

    if args.verify:
        stats = mirror_tree(src_root, dest_root, force=False, dry_run=True)
        pending = stats["copied"]
        print(
            f"Verificación: {stats['files']} archivos ({stats['total_bytes'] / 1e6:.1f} MB), "
            f"{pending} pendientes de copiar/actualizar."
        )
        for rel in stats["missing"]:
            print(f"  aviso: subdirectorio ausente en la instalación: {rel}")
        return 0 if pending == 0 else 1

    stats = mirror_tree(src_root, dest_root, force=args.force)
    dest_root.mkdir(parents=True, exist_ok=True)
    write_manifest(dest_root, src_root, stats, version)
    print(f"Mirror: {dest_root}")
    print(f"  origen: {src_root} (MATLAB {version or 'desconocido'})")
    print(f"  archivos: {stats['files']} ({stats['total_bytes'] / 1e6:.1f} MB)")
    print(
        f"  copiados ahora: {stats['copied']} ({stats['bytes_copied'] / 1e6:.1f} MB), "
        f"sin cambios: {stats['skipped']}"
    )
    for rel in stats["missing"]:
        print(f"  aviso: subdirectorio ausente en la instalación: {rel}")
    print("  El backend lo usa automáticamente cuando MATLAB_ROOT no está definido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
