"""
E1/E2 — Modo oráculo: proxy transparente al connector real de MATLAB.

Opt-in vía MATLAB_CONNECTOR_URL (p. ej. https://127.0.0.1:31515). Cuando está
activo, los paths de servicio del shell real se proxean al connector del MATLAB
instalado en vez de responderlos el emulador (e1_messageservice + bus). Sirve
para capturar el wire auténtico en /api/e1/request-log y compararlo con las
respuestas propias — el oráculo con el que se afinó el emulador.

Cuando la variable está vacía (default) este módulo no toca ninguna petición:
la app funciona 100% con el emulador.

Integración: middleware en app.py (corre antes del routing):

    from backend.e1_connector import oracle_middleware
    app.middleware("http")(oracle_middleware)

Paths proxeados cuando está activo:
  - /messageservice/*, /matlab/messageservice/*, /cometd  → bus del connector
  - /matlab/*, /msh/*, /rtc/*, /matlab_filesystem_datamodel/*, /connector/*,
    /mw-*, /mwactions*, /mwartifacts*, /cmlink/*          → servicios reales
  - /ui/*, /toolbox/*, /sys/*                            → solo si el archivo
    no existe en MATLAB_ROOT (los assets locales siempre ganan)

Notas del protocolo del connector (verificadas contra R2026b):
  - Rechaza Origin/Referer externos con 403 → se eliminan al reenviar.
  - Certificado autofirmado (thisMatlab.pem) → verify=False.
  - /meta/connect hace long-poll real → timeout=None.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response

from backend.e1_probe import _record
from backend.local_assets import _assets_root

_CONNECTOR_URL_ENV = "MATLAB_CONNECTOR_URL"
_PROXY_TIMEOUT_S = 300.0

_proxy_client = httpx.AsyncClient(verify=False, timeout=_PROXY_TIMEOUT_S)

# Prefijos de servicio: siempre al connector cuando el oráculo está activo.
_SERVICE_PREFIXES = (
    "messageservice",
    "matlab/messageservice",
    "matlab",
    "matlab_filesystem_datamodel",
    "connector",
    "cometd",
    "msh",
    "rtc",
    "mw-login",
    "mw-spf-ui",
    "mw-url-manager",
    "mwactions",
    "mwartifacts",
    "cmlink",
)

# Prefijos de assets: disco primero; al connector solo si el archivo falta.
_DISK_PREFIXES = ("ui", "toolbox", "sys")


def connector_url() -> str:
    return os.environ.get(_CONNECTOR_URL_ENV, "").rstrip("/")


def enabled() -> bool:
    return bool(connector_url())


def _local_asset(rel: str) -> Path | None:
    """Archivo bajo MATLAB_ROOT para prefijos de assets; None si no aplica."""
    root = _assets_root()
    if root is None:
        return None
    p = Path(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts:
        return None
    if p.parts[0].lower() not in _DISK_PREFIXES:
        return None
    target = (root / p).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target if target.is_file() else None


def should_proxy(path: str) -> bool:
    """True si el path debe ir al connector (modo oráculo activo ya comprobado)."""
    rel = path.lstrip("/")
    if not rel:
        return False
    first = rel.split("/", 1)[0]
    if rel in _SERVICE_PREFIXES or first in _SERVICE_PREFIXES:
        return True
    if first in _DISK_PREFIXES:
        return _local_asset(rel) is None
    return False


def _rewrite_connector_urls(node: Any, base: str, origin: str) -> Any:
    """Sustituye la URL del connector por el origen del proxy en respuestas JSON.

    El connector devuelve routingHost=https://127.0.0.1:31515/ en AcquireMatlab y
    el JSD pasa a llamar DIRECTO al connector (saltándose el proxy y fallando
    por el certificado autofirmado). Reescribiendo la URL al origen del proxy,
    todas las llamadas siguen por nosotros y el wire queda grabado.
    """
    if isinstance(node, dict):
        return {k: _rewrite_connector_urls(v, base, origin) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite_connector_urls(v, base, origin) for v in node]
    if isinstance(node, str) and base in node:
        return node.replace(base, origin)
    return node


async def proxy(request: Request) -> Response:
    """Reenvía la petición al connector real preservando método, query y cuerpo."""
    base = connector_url()
    rel = request.url.path.lstrip("/")
    body = await request.body()
    origin = str(request.base_url).rstrip("/")
    # El wire del bus (messageservice) es JSON pequeño: se registra íntegro
    # (req+resp) para el oráculo. Assets y servicios grandes solo status.
    _is_wire = rel.startswith(("messageservice", "matlab/messageservice"))
    try:
        upstream = await _proxy_client.request(
            request.method,
            f"{base}/{rel}",
            params=request.query_params.multi_items(),
            content=body or None,
            headers={
                k: v
                for k, v in request.headers.items()
                if k.lower()
                not in ("host", "content-length", "connection", "origin", "referer")
            },
        )
    except httpx.HTTPError as exc:
        _record(
            "proxy-error",
            f"{request.method} /{rel}",
            payload=str(exc),
            status=502,
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": "connector_unreachable",
                "connector": base,
                "detail": str(exc),
                "hint": "Lanza MATLAB y ejecuta connector.ensureServiceOn",
            },
        )
    _record("proxy", f"{request.method} /{rel}", status=upstream.status_code)
    content = upstream.content
    media_type = upstream.headers.get("content-type") or ""
    if "json" in media_type:
        import json as _json

        try:
            content = _json.dumps(
                _rewrite_connector_urls(_json.loads(content), base, origin)
            ).encode()
        except Exception:
            pass
    if _is_wire:
        import json as _json

        wire: dict[str, Any] = {"status": upstream.status_code}
        try:
            wire["request"] = _json.loads(body) if body else None
        except Exception:
            wire["request_raw"] = body[:2000].decode("utf-8", "replace")
        try:
            wire["response"] = _json.loads(content)
        except Exception:
            wire["response_raw"] = content[:2000].decode("utf-8", "replace")
        _record("wire", f"{request.method} /{rel}", payload=wire, status=upstream.status_code)
    excluded = ("transfer-encoding", "content-encoding", "connection", "content-length")
    return Response(
        content=content,
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() not in excluded},
        media_type=upstream.headers.get("content-type"),
    )


async def oracle_middleware(request: Request, call_next: Any) -> Response:
    """Despacha al connector si el oráculo está activo y el path es de servicio."""
    if enabled() and should_proxy(request.url.path):
        return await proxy(request)
    return await call_next(request)
