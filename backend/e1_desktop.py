"""
E1 — Shell REAL de MATLAB (JavaScript Desktop) servido y proxeado en runtime.

Estrategia E1 del PARITY-PROGRAM: el usuario usa su propia instalación
licenciada de MATLAB. NADA de MathWorks se copia al repo:

  - /mw/ y /mw/{path}  → sirven `ui/webgui/src/` desde MATLAB_ROOT en runtime
                         (index-jsd.html = JSD desktop, sin login Online).
  - /ui/*, /toolbox/*, /sys/* → el JSD pide plugins/iconos con rutas ABSOLUTAS
                         en la raíz del origen; se sirven de MATLAB_ROOT y, si
                         el archivo no existe localmente, se proxean al
                         connector real.
  - /messageservice/*  → proxy directo al connector (el JSD habla el bus en
                         la raíz del origen, no bajo /mw/).
  - /matlab/messageservice/* → idem (el connector responde su 403 real si
                         pide apikey).
  - /msh/*, /matlab/*, /matlab_filesystem_datamodel/*, /connector/*, /rtc/*,
    /mw-*, /mwactions, /mwartifacts, /cmlink → proxy al connector real (sus
    404/403 auténticos); todo queda registrado en /api/e1/request-log.
  - /api/e1/*          → estado, request-log y mapa de canales capturados.

Requiere: MATLAB corriendo con `connector.ensureServiceOn` (matlab -nodesktop
-r "connector.ensureServiceOn; while true, pause(60); end"). Sin él, el proxy
devuelve 502 con pista y el evento queda registrado.
"""

from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from backend.local_assets import _assets_root, _resolve_under_root

_CONNECTOR_URL = os.environ.get("MATLAB_CONNECTOR_URL", "https://127.0.0.1:31515")
_WEBGUI_SRC = "ui/webgui/src"
# Subárboles de MATLAB_ROOT servibles en raíz para el JSD (runtime, sin copias).
_E1_DISK_PREFIXES = ("ui", "toolbox", "sys")

# Certificado autofirmado del connector (thisMatlab.pem); long-poll → timeout=None.
_proxy_client = httpx.AsyncClient(verify=False, timeout=None)

_LOG: deque[dict[str, Any]] = deque(maxlen=500)
_CHANNELS: dict[str, dict[str, Any]] = {}

router = APIRouter(tags=["e1-desktop"])


def _record(kind: str, path: str, payload: Any = None, status: int = 0) -> None:
    entry = {"ts": round(time.time(), 3), "kind": kind, "path": path, "status": status}
    if payload is not None:
        entry["payload"] = payload
    _LOG.append(entry)


def _record_channel(channel: str, payload: dict[str, Any]) -> None:
    slot = _CHANNELS.setdefault(channel, {"count": 0, "first_payload": None, "last_payload": None})
    slot["count"] += 1
    if slot["first_payload"] is None:
        slot["first_payload"] = payload
    slot["last_payload"] = payload


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------


@router.get("/api/e1")
def e1_index() -> dict[str, Any]:
    return {
        "strategy": "E1 — JSD desktop real servido + proxeado al connector MATLAB",
        "launch": {
            "jsd_desktop": "/mw/",
            "nologin_online": "/mw/index-nologin.html",
            "online_server": "/mw/index-matlabonlineserver.html",
        },
        "connector": _CONNECTOR_URL,
        "log": "/api/e1/request-log",
        "channel_map": "/api/e1/channels",
        "captured_requests": len(_LOG),
        "captured_channels": len(_CHANNELS),
    }


@router.get("/api/e1/request-log")
def e1_request_log() -> dict[str, Any]:
    return {"count": len(_LOG), "requests": list(_LOG)}


@router.get("/api/e1/channels")
def e1_channels() -> dict[str, Any]:
    return {"count": len(_CHANNELS), "channels": _CHANNELS}


@router.delete("/api/e1/request-log")
def e1_clear() -> dict[str, Any]:
    _LOG.clear()
    _CHANNELS.clear()
    return {"cleared": True}


# ---------------------------------------------------------------------------
# Proxy transparente al connector real
# ---------------------------------------------------------------------------


async def _proxy_to_connector(request: Request, rel: str) -> Response:
    url = f"{_CONNECTOR_URL}/{rel}"
    body = await request.body()
    try:
        upstream = await _proxy_client.request(
            request.method,
            url,
            params=request.query_params.multi_items(),
            content=body or None,
            headers={
                k: v
                for k, v in request.headers.items()
                # El connector exige peticiones "first-party": un Origin/Referer
                # externo (nuestro :8010) le hace responder 403. Se eliminan.
                if k.lower() not in ("host", "content-length", "connection", "origin", "referer")
            },
        )
    except httpx.HTTPError as exc:
        _record("proxy-error", f"{request.method} /{rel}", payload=str(exc), status=502)
        return JSONResponse(
            status_code=502,
            content={
                "e1_probe": True,
                "error": "connector_unreachable",
                "connector": _CONNECTOR_URL,
                "detail": str(exc),
                "hint": "Lanza MATLAB y ejecuta connector.ensureServiceOn",
            },
        )
    _record("proxy", f"{request.method} /{rel}", status=upstream.status_code)
    excluded = ("transfer-encoding", "content-encoding", "connection", "content-length")
    headers = {k: v for k, v in upstream.headers.items() if k.lower() not in excluded}
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=upstream.headers.get("content-type"),
    )


def _register_connector_prefix(prefix: str) -> None:
    async def handler(request: Request, rest: str = "") -> Response:
        return await _proxy_to_connector(request, f"{prefix}/{rest}" if rest else prefix)

    router.add_api_route(
        f"/{prefix}/{{rest:path}}",
        handler,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    router.add_api_route(f"/{prefix}", handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])


def _resolve_e1_file(rel: str) -> Path | None:
    """Como _resolve_under_root pero con prefijos E1 (ui/, toolbox/, sys/).
    Devuelve None si el archivo no existe o la ruta no es válida."""
    root = _assets_root()
    if root is None:
        return None
    p = Path(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    if p.parts[0].lower() not in _E1_DISK_PREFIXES:
        return None
    target = (root / p).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def _register_disk_or_proxy_prefix(prefix: str) -> None:
    async def handler(request: Request, rest: str = "") -> Response:
        rel = f"{prefix}/{rest}" if rest else prefix
        target = _resolve_e1_file(rel)
        if target is not None:
            _record("disk", f"{request.method} /{rel}", status=200)
            return FileResponse(str(target))
        return await _proxy_to_connector(request, rel)

    router.add_api_route(
        f"/{prefix}/{{rest:path}}",
        handler,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    router.add_api_route(f"/{prefix}", handler, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])


# El JSD habla el bus en la raíz del origen; matlab/messageservice también
# (el connector responde su comportamiento real, incluido el 403 con apikey).
for _p in ("messageservice", "matlab/messageservice"):
    _register_connector_prefix(_p)


# ---------------------------------------------------------------------------
# Shell real servido desde MATLAB_ROOT + fallback a proxy
# ---------------------------------------------------------------------------


@router.api_route("/mw/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
@router.api_route("/mw/{relpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def serve_real_webgui(request: Request, relpath: str = ""):
    """Sirve ui/webgui/src desde MATLAB_ROOT bajo /mw/; lo que no sea archivo
    del disco se proxea al connector real (messageservice, matlab/*, etc.)."""
    rel = relpath or "index-jsd.html"
    try:
        target = _resolve_under_root(f"{_WEBGUI_SRC}/{rel}")
    except HTTPException:
        target = None
    if target is not None:
        return FileResponse(str(target))
    return await _proxy_to_connector(request, rel)


@router.get("/real")
def e1_launch() -> Response:
    return RedirectResponse(url="/mw/", status_code=302)


# ---------------------------------------------------------------------------
# Rutas raíz del JSD: archivos de la instalación → disco; servicios → connector
# ---------------------------------------------------------------------------

# Plugins/iconos que el JSD pide con path absoluto en la raíz del origen.
for _p in _E1_DISK_PREFIXES:
    _register_disk_or_proxy_prefix(_p)

# Servicios reales de MATLAB que no son archivos locales: todo al connector.
_PROXY_ONLY_PREFIXES = (
    "matlab",
    "matlab_filesystem_datamodel",
    "connector",
    "msh",
    "mwactions",
    "mwartifacts",
    "mw-login",
    "mw-spf-ui",
    "mw-url-manager",
    "cmlink",
    "rtc",
)

for _prefix in _PROXY_ONLY_PREFIXES:
    _register_connector_prefix(_prefix)
