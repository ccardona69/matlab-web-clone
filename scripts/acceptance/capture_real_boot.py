"""Captura el diálogo REAL de arranque del webgui contra el connector MATLAB.

Herramienta de acceptance (sprint pre-expiración): sirve `ui/webgui/src` desde
MATLAB_ROOT y proxea TODO lo demás al connector vivo (``https://127.0.0.1:31515``,
requiere MATLAB con ``connector.ensureServiceOn``), grabando cada intercambio
—petición y respuesta, cuerpos incluidos— en un JSONL FUERA del repo
(``ml-mirror/_captures/``; ``ml-mirror/`` está gitignored: nada de MathWorks
se commitea).

Objetivo: obtener el guion exacto (mensajes, canales y payloads) que el worker
real usa para pasar de "Initializing..." a "Ready" — el eslabón que falta en
nuestro motor emulado (``backend/e1_messageservice.py``).

Uso::

    MATLAB_ROOT="C:\\Program Files\\MATLAB\\R2026b" \\
      python scripts/acceptance/capture_real_boot.py --port 8021 \\
      --out ml-mirror/_captures/real-boot-jsd.jsonl

    # y en otra terminal (o headless):
    #   http://127.0.0.1:8021/mw/            -> index-jsd.html
    #   http://127.0.0.1:8021/mw/index-nologin.html

Diagnóstico mientras corre: ``GET /api/capture/status``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import httpx  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response  # noqa: E402

from backend.local_assets import _assets_root, _resolve_under_root  # noqa: E402

CONNECTOR = os.environ.get("MATLAB_CONNECTOR_URL", "https://127.0.0.1:31515")
WEBGUI_SRC = "ui/webgui/src"
DEFAULT_PAGE = "index-jsd.html"
DISK_PREFIXES = ("ui", "toolbox", "sys")
# Prefijos que NO son archivos locales: siempre al connector (paridad con la
# receta del proxy de mw-e1, que ya validó el flujo contra el connector real).
PROXY_PREFIXES = (
    "messageservice",
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

_capture_path = REPO / "ml-mirror" / "_captures" / f"real-boot-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
_records = 0
# El connector usa certificado autofirmado (thisMatlab.pem); long-poll => timeout=None.
_client = httpx.AsyncClient(verify=False, timeout=None)

app = FastAPI(title="E1 real-boot capture", docs_url=None, redoc_url=None)


def _clip(data: bytes, cap: int = 900_000) -> str:
    text = data[:cap].decode("utf-8", "replace")
    if len(data) > cap:
        text += f"…<TRUNCADO ({len(data)} bytes)>"
    return text


def _append(record: dict) -> None:
    global _records
    _records += 1
    try:
        _capture_path.parent.mkdir(parents=True, exist_ok=True)
        with _capture_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:  # la captura no debe tumbar el proxy
        print(f"[capture] ERROR al escribir: {exc}", file=sys.stderr)


async def _proxy_and_capture(request: Request, rel: str) -> Response:
    url = f"{CONNECTOR}/{rel}"
    body = await request.body()
    started = time.time()
    upstream = None
    error: str | None = None
    try:
        upstream = await _client.request(
            request.method,
            url,
            params=request.query_params.multi_items(),
            content=body or None,
            headers={
                k: v
                for k, v in request.headers.items()
                # El connector exige peticiones "first-party": un Origin/Referer
                # externo le hace responder 403. Se eliminan (receta mw-e1).
                if k.lower() not in ("host", "content-length", "connection", "origin", "referer")
            },
        )
    except httpx.HTTPError as exc:
        error = str(exc)

    record = {
        "ts": round(time.time(), 3),
        "method": request.method,
        "path": f"/{rel}",
        "query": str(request.query_params) or "",
        "ms": round((time.time() - started) * 1000),
        "req_ct": request.headers.get("content-type", ""),
        "req_body": _clip(body) if body else "",
    }
    if upstream is None:
        record["res_status"] = 502
        record["res_body"] = error or ""
        _append(record)
        return JSONResponse(
            status_code=502,
            content={
                "capture": True,
                "error": "connector_unreachable",
                "connector": CONNECTOR,
                "detail": error,
                "hint": "Lanza MATLAB con connector.ensureServiceOn",
            },
        )

    record["res_status"] = upstream.status_code
    record["res_ct"] = upstream.headers.get("content-type", "")
    record["res_body"] = _clip(upstream.content)
    _append(record)

    excluded = ("transfer-encoding", "content-encoding", "connection", "content-length")
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() not in excluded},
        media_type=upstream.headers.get("content-type"),
    )


@app.get("/api/capture/status")
def capture_status() -> dict:
    return {
        "records": _records,
        "file": str(_capture_path),
        "connector": CONNECTOR,
        "matlab_root": os.environ.get("MATLAB_ROOT", ""),
        "assets_root": str(_assets_root()) if _assets_root() else None,
    }


@app.get("/real")
def _redirect_real() -> Response:
    return RedirectResponse(url="/mw/", status_code=302)


_LOG_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


@app.api_route("/mw/", methods=_LOG_METHODS)
@app.api_route("/mw/{relpath:path}", methods=_LOG_METHODS)
async def serve_webgui(request: Request, relpath: str = "") -> Response:
    rel = relpath or DEFAULT_PAGE
    try:
        target = _resolve_under_root(f"{WEBGUI_SRC}/{rel}")
        return FileResponse(str(target))
    except Exception:  # noqa: BLE001 — no es archivo del disco: al connector
        return await _proxy_and_capture(request, rel)


def _register_disk_or_proxy(prefix: str) -> None:
    async def handler(request: Request, rest: str = "") -> Response:
        rel = f"{prefix}/{rest}" if rest else prefix
        try:
            target = _resolve_under_root(rel)
            if Path(str(target)).is_file():
                return FileResponse(str(target))
        except Exception:  # noqa: BLE001
            pass
        return await _proxy_and_capture(request, rel)

    app.add_api_route(f"/{prefix}/{{rest:path}}", handler, methods=_LOG_METHODS)
    app.add_api_route(f"/{prefix}", handler, methods=_LOG_METHODS)


for _prefix in DISK_PREFIXES:
    _register_disk_or_proxy(_prefix)

for _prefix in PROXY_PREFIXES:
    async def handler(request: Request, rest: str = "", _p: str = _prefix) -> Response:
        rel = f"{_p}/{rest}" if rest else _p
        return await _proxy_and_capture(request, rel)

    app.add_api_route(f"/{_prefix}/{{rest:path}}", handler, methods=_LOG_METHODS)
    app.add_api_route(f"/{_prefix}", handler, methods=_LOG_METHODS)


def main() -> None:
    global _capture_path
    parser = argparse.ArgumentParser(description="Captura el arranque real (E1) contra el connector.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8021)
    parser.add_argument("--out", default="", help="Ruta del JSONL de captura (def.: ml-mirror/_captures/...)")
    args = parser.parse_args()
    if args.out:
        _capture_path = Path(args.out)
        if not _capture_path.is_absolute():
            _capture_path = REPO / _capture_path

    import uvicorn

    print(f"[capture] connector   : {CONNECTOR}")
    print(f"[capture] MATLAB_ROOT : {os.environ.get('MATLAB_ROOT', '(NO SETEADO)')}")
    root = _assets_root()
    print(f"[capture] assets root : {root}")
    print(f"[capture] captura     : {_capture_path}")
    print(f"[capture] url         : http://{args.host}:{args.port}/mw/")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
