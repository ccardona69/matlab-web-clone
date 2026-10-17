"""
E1 (WO-06) — Motor de respuestas del protocolo de "message containers" del shell real.

El webgui real (servido en runtime desde MATLAB_ROOT bajo /mw/) habla con su
backend mediante contenedores JSON:

    POST /messageservice/json
    {"uuid": "<id-transaccion>", "messages": {"<Tipo>": [ {"uuid": "<clasificador>", ...} ]}}

Evidencia (sin copiar implementación de MathWorks):
  - rea/reconstructed/modules/mw-remote/impl/ResponseManager.js: el cliente
    correlaciona cada entry de respuesta por su `uuid` (el mismo que envió) y lo
    entrega al handler "<Tipo>Response:<clasificador>" o al handler plano
    "<Tipo>Response" cuando la petición no llevaba uuid.
  - rea/reconstructed/modules/mw-remote/impl/JsonTransaction.js: la respuesta es
    {"uuid": ..., "messages": {...}} (o un mapa plano de tipos).
  - bundle.361.js (instalación, solo lectura): un entry sano lleva
    "messageFaults": [] — el shell revisa messageFaults[0].faultCode para decidir
    transiciones (p.ej. NO_WORKERS_AVAILABLE en AcquireMatlab).
  - capturas reales del arranque: docs/acceptance/ui/e1-request-map.md.

Los handlers aquí implementados responden al bootstrap observado del shell
(CurrentUser → ServiceRegistry → AcquireMatlab → worker). Los tipos desconocidos
reciben un acuse sano y quedan registrados en /api/e1/request-log para ampliar el
mapa en la siguiente captura.
"""

from __future__ import annotations

import uuid as _uuid
from collections import Counter
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from backend.e1_probe import _bayeux_probe, _record, _record_channel

router = APIRouter(tags=["e1-messageservice"])

# El cliente acepta este fallback exacto cuando CurrentUser no trae datos
# (bundle.361.js: resolve({userInfo:{firstName:"",userToken:{}}})), y
# _isAuthorized(exchange) exige userInfo.userToken truthy para dejar avanzar
# el bootstrap (AcquireMatlab → computeResourceReady).
_USER_INFO: dict[str, Any] = {"firstName": "", "lastName": "", "userToken": {}}

# Faults a nivel de transacción (JsonTransaction._processResponse lee n.fault;
# FaultManager.handleFault despacha por tipo de mensaje request). La máquina de
# estados (mw-login) transiciona "fault GetCurrentComputeResource" → acquireMatlab,
# cuyo onEnterState envía AcquireMatlab. (Una respuesta "success" sin computeInfo
# devolvía el target "acquireMATLAB", que no existe como estado → stall.)
_FAULTS: dict[str, dict[str, Any]] = {
    "GetCurrentComputeResource": {
        "faultCode": "ComputeService.NoWorkersAvailable",
        "message": "No current compute resource (E1 backend local).",
    },
}

_STATS: Counter[str] = Counter()

# Contexto por petición disponible para los handlers (origen desde el que se
# sirvió el shell; p.ej. el routingHost con el que el cliente rutea su
# WORKER_ENDPOINT en la respuesta de AcquireMatlab).
_Ctx = dict[str, str]


def _h_current_user(_entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    return {"userInfo": dict(_USER_INFO)}


def _h_acquire_matlab(_entry: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    # _handleAcquireMatlabResponse: _isAuthorized(entry) → setUserInfo(entry) →
    # _setSessionTimeouts lee sessionInfo.sessionTimeoutSeconds; sin messageFaults
    # el shell pasa a checkingMATLABHealth. computeInfo dispara
    # _handleAcquireComputeResourceResponse: setComputeToken(computeInfo.computeToken)
    # y setWorkerEndpoint(routingHost, routingKey). SecurityUtils.isAllowed acepta
    # el string (hace new URL() y compara same-origin; 127.0.0.1/localhost están
    # en la lista permitida), y SendMessageUtil.getRemoteUrlForEndPoint deja de
    # devolver "" (antes: "no handler for endPoint WORKER_ENDPOINT").
    return {
        "userInfo": dict(_USER_INFO),
        "sessionInfo": {"sessionTimeoutSeconds": 3600, "maxUnattendedCodeExecutionSeconds": 600},
        "computeInfo": {
            "computeToken": {"computeSessionId": "e1-local-compute"},
            "routingHost": ctx.get("base_url", ""),
            "routingKey": "",
        },
    }


def _h_get_matlab_status(_entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    # _doHealthCheckOnWorker (bundle.361.js 175743): c.send({GetMatlabStatus})
    # resuelve {GetMatlabStatus: entry} y lee o.GetMatlabStatus.status (es
    # decir, entry.status). Se incluye también la clave anidada por
    # compatibilidad con los tests existentes.
    return {"status": "IDLE", "GetMatlabStatus": {"status": "IDLE"}}


def _h_service_registry(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    # _handleServiceRegistryResponse itera cada entry `s` y evalúa
    # `s.properties.endpoint`; sin `properties` lanza TypeError y nunca emite
    # "serviceSet". Con endpoint="" conserva los endpoints por defecto.
    raw_props = entry.get("properties")
    props = dict(raw_props) if isinstance(raw_props, dict) else {}
    props.setdefault("endpoint", "")
    return {"properties": props}


def _h_client_type(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    raw_props = entry.get("properties")
    props = dict(raw_props) if isinstance(raw_props, dict) else {}
    return {"properties": props}


def _h_open_file(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    import os
    from pathlib import Path
    from backend.e1_bus_services import _fs_entry, _is_safe_path

    path = str(entry.get("path") or "")
    uuid_str = entry.get("uuid")
    if not path or not _is_safe_path(path) or not os.path.isfile(path):
        return {
            "apiVersion": "1.4",
            "isDebugEvent": False,
            "messageFaults": [
                {
                    "faultCode": "FileService.IOError",
                    "faultConditions": [{"faultId": "FileNotFound", "faultInfo": [path]}],
                    "message": f"{path} does not exist.",
                }
            ],
            "uuid": uuid_str,
        }
    try:
        content = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = Path(path).read_text(encoding="latin-1", errors="replace")
    return {
        "apiVersion": "1.4",
        "file": {
            "content": content,
            "fileInfo": _fs_entry(path),
        },
        "lineNumber": 1,
        "column": 1,
        "isDebugEvent": False,
        "messageFaults": [],
        "uuid": uuid_str,
    }


def _h_update_file(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    from pathlib import Path
    from backend.e1_bus_services import _is_safe_path

    file_obj = entry.get("file") or {}
    file_info = file_obj.get("fileInfo") or {}
    path = str(file_info.get("path") or entry.get("path") or "")
    uuid_str = entry.get("uuid")
    if path and _is_safe_path(path) and "content" in file_obj:
        Path(path).write_text(file_obj["content"], encoding="utf-8")
    return {
        "apiVersion": "1.4",
        "file": file_obj,
        "messageFaults": [],
        "uuid": uuid_str,
    }


def _h_create_file(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    import os
    from pathlib import Path
    from backend.e1_bus_services import _fs_entry, _is_safe_path

    file_obj = entry.get("file") or {}
    file_info = file_obj.get("fileInfo") or {}
    path = str(file_info.get("path") or entry.get("path") or "")
    uuid_str = entry.get("uuid")
    is_dir = bool(file_info.get("isDirectory"))
    if path and _is_safe_path(path):
        if is_dir:
            os.makedirs(path, exist_ok=True)
        else:
            Path(path).write_text(file_obj.get("content", ""), encoding="utf-8")
    return {
        "apiVersion": "1.4",
        "fileInfo": _fs_entry(path) if path else {},
        "lineNumber": 1,
        "column": 1,
        "messageFaults": [],
        "uuid": uuid_str,
    }


def _h_current_folder(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    import os
    from pathlib import Path

    cwd = os.getcwd()
    parent = str(Path(cwd).parent)
    return {
        "apiVersion": "1.0",
        "currentFolder": {
            "deleted": False,
            "filePermissions": {"canWrite": True},
            "isDirectory": True,
            "location": (parent + "\\") if parent else "\\",
            "name": Path(cwd).name,
            "separator": "\\",
            "type": "",
        },
        "messageFaults": [],
        "uuid": entry.get("uuid"),
    }


def _h_generic_ack(entry: dict[str, Any], _ctx: _Ctx) -> dict[str, Any]:
    return {"messageFaults": [], "uuid": entry.get("uuid")}


_HANDLERS: dict[str, Callable[[dict[str, Any], _Ctx], dict[str, Any]]] = {
    "CurrentUser": _h_current_user,
    "AcquireMatlab": _h_acquire_matlab,
    "GetMatlabStatus": _h_get_matlab_status,
    "ServiceRegistry": _h_service_registry,
    "ClientType": _h_client_type,
    "OpenFile": _h_open_file,
    "CreateFile": _h_create_file,
    "UpdateFile": _h_update_file,
    "CloseFile": _h_generic_ack,
    "DeleteFile": _h_generic_ack,
    "CurrentFolder": _h_current_folder,
    "ClientModulesStarted": _h_generic_ack,
    "GetLoginInfoMessage": lambda e, c: {
        "info": {"displayName": "", "emailAddress": "", "firstName": "", "lastName": "", "profileId": "", "userId": ""},
        "level": 0, "loggedIn": False, "messageFaults": [], "uuid": e.get("uuid"),
    },
    "GetLoginPrereqsMessage": lambda e, c: {
        "logoutAllowed": True, "message": "", "messageFaults": [], "messageType": "", "uuid": e.get("uuid"), "veto": False,
    },
    "AddStatusListenerMessage": _h_generic_ack,
}


def _new_container_uuid() -> str:
    return _uuid.uuid4().hex[:8].upper()


def _build_reply_entry(mtype: str, entry: dict[str, Any], ctx: _Ctx) -> dict[str, Any]:
    handler = _HANDLERS.get(mtype)
    body = dict(handler(entry, ctx)) if handler is not None else {}
    reply_uuid = entry.get("uuid")
    reply: dict[str, Any] = {}
    if isinstance(reply_uuid, str) and reply_uuid:
        reply["uuid"] = reply_uuid
    reply.update(body)
    reply.setdefault("messageFaults", [])
    return reply


def try_handle_container(
    payload: Any, path: str | None = None, base_url: str = ""
) -> dict[str, Any] | None:
    """Si `payload` es un message-container del shell, devuelve la respuesta.

    `base_url` es el origen desde el que se sirvió el shell (contexto de los
    handlers). Devuelve None si no es un contenedor (p.ej. cuerpo Bayeux), para
    que el llamante aplique su propio fallback.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), dict):
        return None
    ctx: _Ctx = {"base_url": base_url}
    messages: dict[str, Any] = payload["messages"]
    replies: dict[str, list[dict[str, Any]]] = {}
    types_seen: list[str] = []
    for mtype, entries in messages.items():
        if not isinstance(mtype, str):
            continue
        types_seen.append(mtype)
        batch = entries if isinstance(entries, list) else [entries]
        for entry in batch:
            if not isinstance(entry, dict):
                entry = {}
            _STATS[mtype] += 1
            reply_entry = _build_reply_entry(mtype, entry, ctx)
            replies.setdefault(f"{mtype}Response", []).append(reply_entry)
            _record_channel(
                f"container←{mtype}", {k: v for k, v in entry.items() if k != "uuid"}
            )
    _record(
        "container",
        path or "messageservice",
        payload={"types": types_seen, "uuid": payload.get("uuid")},
        status=200,
    )
    for mtype in types_seen:
        if mtype in _FAULTS:
            return {
                "uuid": _new_container_uuid(),
                "fault": dict(_FAULTS[mtype]),
                "messages": {},
            }
    return {"uuid": _new_container_uuid(), "messages": replies}


# ---------------------------------------------------------------------------
# Endpoints: el shell postea containers a /messageservice/<verbo> (con o sin
# prefijo /matlab). GET sin cuerpo se responde [] para no romper sondeos.
# ---------------------------------------------------------------------------

_CONTAINER_VERBS = ("json", "json/blue", "json/secure", "async", "async/blue", "binary")
_CONTAINER_PREFIXES = ("messageservice", "matlab/messageservice")


async def _container_endpoint(request: Request) -> Response:
    try:
        payload = await request.json()
    except Exception:
        payload = None
    handled = try_handle_container(
        payload,
        path=str(request.url.path),
        base_url=str(request.base_url).rstrip("/"),
    )
    if handled is not None:
        return JSONResponse(content=handled)
    # Cuerpo no-container (p.ej. lote Bayeux): el probe responde como hasta ahora.
    return await _bayeux_probe(request)


for _prefix in _CONTAINER_PREFIXES:
    for _verb in _CONTAINER_VERBS:
        router.add_api_route(
            f"/{_prefix}/{_verb}", _container_endpoint, methods=["GET", "POST"]
        )
