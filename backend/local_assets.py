"""
WO-02: Assets locales servidos en runtime desde la instalación de MATLAB (opt-in).

Si la variable de entorno MATLAB_ROOT apunta a una instalación existente
(ej. C:\\Program Files\\MATLAB\\R2026b), este router expone:

  GET /api/assets/matlab/{relpath}  → sirve un archivo dentro de MATLAB_ROOT
                                      (subárboles permitidos: ui/, sys/ y los
                                      componentes de UI toolbox/matlab/
                                      {rich_text_component,rtc_addons})
  GET /api/assets/fonts.css         → CSS con @font-face para las fuentes woff
                                      descubiertas en ui/webgui/**/fonts

Raíz de assets (en orden): MATLAB_ROOT → MATLAB_MIRROR → <repo>/ml-mirror. El
mirror local lo genera scripts/mirror_matlab_webgui.py desde la instalación
licenciada del usuario (modo standalone). Sin ninguna raíz los endpoints
devuelven 404 / hoja vacía. NADA del contenido se copia al repo: se lee del
disco del usuario en cada petición (ml-mirror/ está en .gitignore).
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from backend.matlab.library import BUILTINS

_ASSETS_ROOT_ENV = "MATLAB_ROOT"
_MIRROR_ROOT_ENV = "MATLAB_MIRROR"
_MIRROR_DIRNAME = "ml-mirror"
_ALLOWED_PREFIXES = ("ui", "sys", "toolbox")
# Subárboles puntuales fuera de ui/sys que el shell real también carga en
# runtime (componentes de UI bajo toolbox/matlab/: el bundle del texto
# enriquecido del Command Window y los chunks de rtc_addons/copilot).
_ALLOWED_SUBTREES = (
    ("toolbox", "matlab", "rich_text_component"),
    ("toolbox", "matlab", "rtc_addons"),
)

router = APIRouter(prefix="/api/assets", tags=["local-assets"])
console_router = APIRouter(tags=["mvm"])


def _default_mirror_root() -> Path | None:
    """Mirror local del frontend (<repo>/ml-mirror); lo genera el usuario.

    Ver scripts/mirror_matlab_webgui.py. Nunca va al repo (.gitignore): es una
    copia local de trabajo hecha desde la instalación licenciada del usuario.
    """
    candidate = Path(__file__).resolve().parent.parent / _MIRROR_DIRNAME
    return candidate if candidate.is_dir() else None


def _assets_roots() -> list[Path]:
    """Raíces candidatas, en orden: instalación → mirror explícito → mirror del repo."""
    roots: list[Path] = []
    for raw in (os.environ.get(_ASSETS_ROOT_ENV, ""), os.environ.get(_MIRROR_ROOT_ENV, "")):
        raw = raw.strip()
        if not raw:
            continue
        candidate = Path(raw)
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    default = _default_mirror_root()
    if default is not None and default not in roots:
        roots.append(default)
    return roots


def _assets_root() -> Path | None:
    """Primera raíz disponible (para consumidores de una sola raíz)."""
    roots = _assets_roots()
    return roots[0] if roots else None


def _resolve_under_root(relpath: str) -> Path:
    rel = Path(relpath.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise HTTPException(status_code=400, detail="Ruta relativa inválida.")
    lower_parts = tuple(part.lower() for part in rel.parts)
    allowed = rel.parts[0].lower() in _ALLOWED_PREFIXES or any(
        lower_parts[: len(subtree)] == subtree for subtree in _ALLOWED_SUBTREES
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=f"Subárbol no permitido: {rel.parts[0]}")

    roots = _assets_roots()
    if not roots:
        raise HTTPException(status_code=404, detail="MATLAB_ROOT no configurado; assets locales deshabilitados.")
    for root in roots:
        target = (root / rel).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Ruta relativa inválida.")
        if target.is_file():
            return target
    raise HTTPException(status_code=404, detail=f"Asset no encontrado: {rel}")


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


@console_router.get("/api/mvm/completions")
def get_mvm_completions() -> dict[str, Any]:
    """Nombres completables con Tab en la Command Window.

    Devuelve los builtins registrados; el frontend suma las variables del
    Workspace que ya recibe en cada evaluación (res.workspace)."""
    return {"names": sorted(BUILTINS)}
