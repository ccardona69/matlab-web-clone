"""
WO-02: Assets locales servidos en runtime desde la instalación de MATLAB (opt-in).

Si la variable de entorno MATLAB_ROOT apunta a una instalación existente
(ej. C:\\Program Files\\MATLAB\\R2026b), este router expone:

  GET /api/assets/matlab/{relpath}  → sirve un archivo dentro de MATLAB_ROOT
                                      (solo subárboles permitidos: ui/, sys/fonts)
  GET /api/assets/fonts.css         → CSS con @font-face para las fuentes woff
                                      descubiertas en ui/webgui/**/fonts

Sin MATLAB_ROOT los endpoints devuelven 404 / hoja vacía: el frontend queda
con sus fuentes e iconos de respaldo. NADA del contenido se copia al repo;
se lee del disco del usuario en cada petición.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

_ASSETS_ROOT_ENV = "MATLAB_ROOT"
_ALLOWED_PREFIXES = ("ui", "sys")

router = APIRouter(prefix="/api/assets", tags=["local-assets"])


def _assets_root() -> Path | None:
    raw = os.environ.get(_ASSETS_ROOT_ENV, "").strip()
    if not raw:
        return None
    root = Path(raw)
    return root if root.is_dir() else None


def _resolve_under_root(relpath: str) -> Path:
    root = _assets_root()
    if root is None:
        raise HTTPException(status_code=404, detail="MATLAB_ROOT no configurado; assets locales deshabilitados.")

    rel = Path(relpath.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise HTTPException(status_code=400, detail="Ruta relativa inválida.")
    if rel.parts[0].lower() not in _ALLOWED_PREFIXES:
        raise HTTPException(status_code=403, detail=f"Subárbol no permitido: {rel.parts[0]}")

    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Ruta relativa inválida.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Asset no encontrado: {rel}")
    return target


@router.get("/matlab/{relpath:path}")
def get_matlab_asset(relpath: str) -> FileResponse:
    """Sirve un archivo de la instalación local (ui/, sys/) sin copiarlo al repo."""
    target = _resolve_under_root(relpath)
    media_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(str(target), media_type=media_type or "application/octet-stream")


def _discover_fonts(root: Path) -> list[Path]:
    fonts_root = root / "ui" / "webgui" / "src" / "release"
    found: list[Path] = []
    if fonts_root.is_dir():
        for version_dir in sorted(fonts_root.iterdir()):
            fonts_dir = version_dir / "fonts"
            if fonts_dir.is_dir():
                found.extend(sorted(fonts_dir.glob("*.woff")))
                found.extend(sorted(fonts_dir.glob("*.woff2")))
    return found


@router.get("/fonts.css", response_class=Response)
def get_local_fonts_css() -> Response:
    """Genera @font-face para las fuentes de la instalación (vacío si no hay MATLAB_ROOT)."""
    root = _assets_root()
    rules: list[str] = []
    if root is not None:
        resolved_root = root.resolve()
        for font_path in _discover_fonts(root):
            rel = font_path.resolve().relative_to(resolved_root).as_posix()
            family = font_path.name.split("-")[0]
            style = "italic" if "italic" in font_path.name.lower() else "normal"
            weight = "bold" if "bold" in font_path.name.lower() else "normal"
            rules.append(
                "@font-face {"
                f'font-family: "{family}"; font-style: {style}; font-weight: {weight};'
                f'src: url("/api/assets/matlab/{rel}") format("woff");'
                "font-display: swap;}"
            )
    body = "\n".join(rules) + ("\n" if rules else "")
    return Response(content=body, media_type="text/css")
