"""
E1 — Probe diagnóstico para arrancar el frontend REAL de MATLAB desde MATLAB_ROOT.

Objetivo (documentado en PARITY-PROGRAM §5, estrategia E1): poder cargar
`ui/webgui/src/index-nologin.html` de la instalación local contra nuestro backend
y descubrir, petición a petición, qué protocolo espera el shell real.

NO es una implementación del bus (eso es WO-05 de Codex). Este probe:
  - sirve como red de seguridad (catch-all) para prefijos que aún no existen;
  - responde un handshake Bayeux mínimo y `successful:true` a /meta/*;
  - REGISTRA cada canal suscrito/publicado y cada REST desconocido para generar
    el "mapa de endpoints" que deben implementar los workstreams del bus.

Precedencia: este router se incluye AL FINAL en app.py. Cualquier ruta real
registrada antes (p.ej. el /matlab/messageservice/async de WO-05) gana.

Nada del frontend de MathWorks se copia al repo: la página real se sirve en
runtime desde MATLAB_ROOT bajo el prefijo /mw/ (o /api/assets/matlab/...).
"""

from __future__ import annotations

import itertools
import json
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from backend.local_assets import _resolve_under_root

_LOG: deque[dict[str, Any]] = deque(maxlen=500)
_CHANNELS: dict[str, dict[str, Any]] = {}
_client_seq = itertools.count(1)

router = APIRouter(tags=["e1-probe"])


def _record(kind: str, path: str, payload: Any = None, status: int = 501) -> None:
    entry = {
        "ts": round(time.time(), 3),
        "kind": kind,
        "path": path,
        "status": status,
    }
    if payload is not None:
        entry["payload"] = payload
    _LOG.append(entry)


def _record_channel(channel: str, bayeux: dict[str, Any]) -> None:
    slot = _CHANNELS.setdefault(
        channel,
        {"count": 0, "first_payload": None, "last_payload": None},
    )
    slot["count"] += 1
    slim = {
        k: v
        for k, v in bayeux.items()
        if k not in ("id", "clientId", "channel")
    }
    if slot["first_payload"] is None:
        slot["first_payload"] = slim
    slot["last_payload"] = slim


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------


@router.get("/api/e1")
def e1_index() -> dict[str, Any]:
    """Punto de entrada E1: URLs para lanzar el shell real + estado del log."""
    return {
        "strategy": "E1 — frontend original asistido (runtime, opt-in MATLAB_ROOT)",
        "launch": {
            "desktop_nologin": "/mw/",
            "desktop_nologin_alt": "/mw/index-matlabonlineserver.html",
            "full_online": "/mw/index.html",
        },
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
    """Mapa deduplicado: cada canal/endpoint visto, cuántas veces, payload de muestra."""
    return {"count": len(_CHANNELS), "channels": _CHANNELS}


@router.delete("/api/e1/request-log")
def e1_clear() -> dict[str, Any]:
    _LOG.clear()
    _CHANNELS.clear()
    return {"cleared": True}


# ---------------------------------------------------------------------------
# Probe Bayeux mínimo (handshake + eco de suscripciones/publicaciones)
# ---------------------------------------------------------------------------

_BAYEUX_PREFIXES = ("matlab/messageservice", "messageservice", "mw/messageservice")


def _bayeux_reply(msg: dict[str, Any], ok: bool = True) -> dict[str, Any]:
    reply = {"channel": msg.get("channel"), "successful": ok}
    for key in ("id", "clientId", "subscription", "connectionId"):
        if key in msg:
            reply[key] = msg[key]
    ch = msg.get("channel", "")
    if ch == "/meta/handshake":
        # interval>0: el cliente real reintenta el long-polling a este ritmo;
        # con 0 martillaba /messageservice/async (miles de POSTs por arranque).
        reply.update(
            version="1.0",
            supportedConnectionTypes=["long-polling", "callback-polling"],
            advice={"reconnect": "retry", "interval": 3000, "timeout": 60000},
        )
    elif ch == "/meta/connect":
        reply["advice"] = {"reconnect": "retry", "interval": 3000, "timeout": 60000}
    return reply


async def _bayeux_probe(request: Request) -> Response:
    body = await request.body()
    text = body.decode("utf-8", errors="replace")[:4000]
    _record("raw", f"{request.method} {request.url.path}", payload=text or None)
    try:
        batch = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        batch = None
    msgs = batch if isinstance(batch, list) else [batch] if isinstance(batch, dict) else []

    replies: list[dict[str, Any]] = []
    for msg in msgs:
        ch = msg.get("channel", "?")
        if ch == "/meta/handshake" and "clientId" not in msg:
            msg["clientId"] = f"e1probe-{next(_client_seq)}"
        if ch.startswith("/meta/") or isinstance(msg, dict):
            _record_channel(ch, msg)
        replies.append(_bayeux_reply(msg))

    if not msgs:
        _record("bayeux-raw", str(request.url.path), payload=text or None)

    if not replies:
        # Respuesta Bayeux vacía válida — mejor que 501 para sondeos GET.
        return JSONResponse(content=[])
    return JSONResponse(content=replies)


for _prefix in _BAYEUX_PREFIXES:
    for _verb in ("async", "json", "json/blue", "json/secure", "binary", "async/blue"):
        router.add_api_route(
            f"/{_prefix}/{_verb}", _bayeux_probe, methods=["GET", "POST"]
        )


_WEBGUI_SRC = "ui/webgui/src"


@router.get("/mw/")
@router.get("/mw/{relpath:path}")
def serve_real_webgui(relpath: str = "") -> FileResponse:
    """Sirve el shell real de MATLAB (ui/webgui/src) bajo /mw/ desde MATLAB_ROOT.

    `/mw/` sin path devuelve index-nologin.html (modo desktop sin login); los
    recursos relativos `release/...` resuelven dentro del mismo prefijo, así el
    bundle de 18MB + CSS + fuentes funcionan sin copiar nada al repo.
    """
    rel = relpath or "index-nologin.html"
    try:
        target = _resolve_under_root(f"{_WEBGUI_SRC}/{rel}")
    except HTTPException as exc:
        if exc.status_code == 404:
            _record("http", f"GET /mw/{relpath}", status=404)
        raise
    return FileResponse(str(target))


@router.get("/real")
def e1_launch() -> Response:
    """Atajo: redirige a /mw/ (la URL canónica del shell real)."""
    return RedirectResponse(url="/mw/", status_code=302)


# ---------------------------------------------------------------------------
# Assets de runtime adicionales del frontend (mismo criterio que /mw/: se sirven
# desde MATLAB_ROOT, no se copia nada al repo):
#   - /ui/* → ui/* (p.ej. ui/icons/registry.json, que el toolstrip real pide
#     para resolver sus iconos; sin él: "Failed to fetch icon").
#   - /toolbox/matlab/rich_text_component/* → el bundle del componente de texto
#     enriquecido (mwBundle.rtc_R2026b.js) que el Command Window carga como chunk.
#   - /toolbox/matlab/rtc_addons/* → chunks de los addons del editor (copilot).
# ---------------------------------------------------------------------------

_INSTALL_PREFIXES = (
    "ui",
    "toolbox/matlab/rich_text_component",
    "toolbox/matlab/rtc_addons",
)


def _make_install_serve(prefix: str):
    def _serve(relpath: str = "") -> FileResponse:
        try:
            target = _resolve_under_root(f"{prefix}/{relpath}")
        except HTTPException as exc:
            if exc.status_code == 404:
                _record("http", f"GET /{prefix}/{relpath}", status=404)
            raise
        return FileResponse(str(target))

    _serve.__name__ = f"serve_install_{prefix.replace('/', '_')}"
    return _serve


for _prefix in _INSTALL_PREFIXES:
    router.add_api_route(
        f"/{_prefix}/{{relpath:path}}", _make_install_serve(_prefix), methods=["GET"]
    )



# ---------------------------------------------------------------------------
# Catch-all: todo lo que el shell real pida y aún no exista → 501 + registro.
# Prefijos observados en bundle.361.js (index-css/bundle de la instalación).
# ---------------------------------------------------------------------------

_PROBE_PREFIXES = (
    "matlab",
    "matlab_filesystem_datamodel",
    "messageservice",
    "connector",
    "mvm",
    "mw",
    "mwactions",
    "mwartifacts",
    "mw-login",
    "mw-spf-ui",
    "mw-url-manager",
    "cmlink",
    "rtc",
)


async def _catch_all(request: Request) -> JSONResponse:
    path = request.url.path.lstrip("/")
    body_text: str | None = None
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        raw = await request.body()
        if raw:
            body_text = raw.decode("utf-8", errors="replace")[:2000]
    _record(
        "http",
        f"{request.method} /{path}",
        payload=body_text or (str(request.query_params) or None),
    )
    _record_channel(f"{request.method} /{path.split('?')[0]}", {})
    return JSONResponse(
        status_code=501,
        content={
            "e1_probe": True,
            "error": "not_implemented",
            "method": request.method,
            "path": f"/{path}",
            "hint": "Endpoint real del shell MATLAB aún sin implementar; registrado en /api/e1/request-log",
        },
    )


for _prefix in _PROBE_PREFIXES:
    router.add_api_route(
        f"/{_prefix}/{{rest:path}}",
        _catch_all,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    router.add_api_route(
        f"/{_prefix}", _catch_all, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
    )
