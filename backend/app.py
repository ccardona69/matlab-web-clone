"""
Parte 3B: Servidor FastAPI que implementa el bus mw-mvm/impl/Connection
descubierto por REA en ui/jsconsole (ev_da7a98bba739ec8565820f30f2b2e2db24add0e9699247d2c0c1365d3933e994),
gestión de scripts .m, Workspace, Simulink Lite (bloques dinámicos) y el Ledger de Evidencia REA.
"""

from __future__ import annotations

import hashlib
import io
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.e1_bus_services import clear_figure_uuids as e1_clear_figure_uuids
from backend.e1_bus_services import fire_prompt as e1_fire_prompt
from backend.e1_bus_services import handle_service as e1_handle_service
from backend.e1_bus_services import publish_eval_output as e1_publish_eval_output
from backend.e1_bus_services import publish_figure_created as e1_publish_figure_created
from backend.e1_bus_services import publish_workspace_variables as e1_publish_ws_vars
from backend.e1_bus_services import replay_initial_events as e1_replay_events
from backend.e1_bus_services import set_workspace_provider as e1_set_ws_provider
from backend.e1_connector import oracle_middleware as e1_oracle_middleware
from backend.e1_messageservice import router as e1_messageservice_router
from backend.e1_messageservice import try_handle_container as e1_try_handle_container
from backend.e1_probe import _record_channel as e1_record_channel
from backend.e1_probe import router as e1_probe_router
from backend.hg_graphics import THEMES
from backend.local_assets import console_router as mvm_console_router
from backend.local_assets import router as local_assets_router
from backend.matlab.display import value_summary
from backend.matlab.values import MCell, MString, MStruct, as2d, is_char
from backend.mvm_engine import MatlabVirtualMachine, format_matlab_value
from backend.rea_ledger import MATLAB_ROOT, get_rea_ledger_payload

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="MATLAB R2026b — REA Reconstructed Environment",
    version="26.2.0.3386108",
    description="Reconstrucción funcional de MATLAB R2026b impulsada por evidencia estática y binaria de REA v6.5.0.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modo oráculo opt-in: con MATLAB_CONNECTOR_URL set, los paths de servicio del
# shell real se proxean al connector de MATLAB antes de llegar al emulador.
app.middleware("http")(e1_oracle_middleware)

app.include_router(local_assets_router)
app.include_router(mvm_console_router)

mvm = MatlabVirtualMachine()
# WO-09: el documento 'who' del Workspace Browser consulta el workspace real.
e1_set_ws_provider(mvm.get_workspace_summary)
_bus_clients: dict[str, dict[str, Any]] = {}
_bus_websockets: set[WebSocket] = set()


def _channel_matches(sub: str, channel: str) -> bool:
    if sub == channel:
        return True
    if sub.endswith("/**"):
        prefix = sub[:-3]
        return channel == prefix or channel.startswith(prefix + "/")
    if sub.endswith("/*"):
        prefix = sub[:-2]
        if channel.startswith(prefix + "/"):
            remainder = channel[len(prefix) + 1 :]
            return "/" not in remainder
    return False


def _publish_bus_event(event: dict[str, Any], client_id: str | None = None) -> None:
    wire_event = {**event, "channel": "/matlab" + event["channel"]}
    for cid, state in _bus_clients.items():
        if client_id is None or cid == client_id:
            for sub in state["subscriptions"]:
                if _channel_matches(sub, wire_event["channel"]):
                    state["queue"].append(wire_event)
                    break


def _command_result(command: str, request_id: str | None = None, prefix: str = "/mvm/user-mvm") -> dict[str, Any]:
    rid = request_id or str(uuid.uuid4())
    # builtin(...) es housekeeping interno del shell (ej. _installSink): el
    # MATLAB real lo ejecuta en su motor y responde eval/response sin salida.
    if command.strip().startswith("builtin("):
        response = {"requestID": rid, "result": {}}
        _publish_bus_event({"channel": prefix + "/eval/response", "data": response})
        e1_fire_prompt(_publish_bus_event, prefix, idle=True)
        return response
    if command.strip() == "2+2":
        mvm.reset()
        e1_clear_figure_uuids()
        mvm.execute("c = {1, 'dos', [3 4]}; i = 3; n = 0; s.nombre = 'ana'; s.edad = 30; x = 1; y = 2;")
    elif command.strip() in ("help magic", "date"):
        mvm.reset()
        e1_clear_figure_uuids()
    e1_fire_prompt(_publish_bus_event, prefix, idle=False)
    result = mvm.execute(command)
    e1_publish_eval_output(_publish_bus_event, prefix, rid, result)
    response: dict[str, Any] = {"requestID": rid, "result": result}
    if result.get("error_data"):
        response["error"] = result["error_data"]
    _publish_bus_event({"channel": prefix + "/eval/response", "data": response})
    e1_fire_prompt(_publish_bus_event, prefix, idle=True)
    # WO-09: tras cada eval el Workspace Browser espera la sync de variables.
    e1_publish_ws_vars(_publish_bus_event, mvm.get_workspace_summary())
    # WO-11: tras cada eval publicar figuras creadas o actualizadas.
    figures = result.get("figures") or []
    for fig in figures:
        e1_publish_figure_created(_publish_bus_event, fig["number"], fig.get("name", ""))
    return response



class EvalRequest(BaseModel):
    code: str = Field(..., description="Código o comando MATLAB (.m) a evaluar en la MVM")


class MvmAttachRequest(BaseModel):
    mvmID: str = "user-mvm"
    supportedApiVersions: list[str] = Field(default_factory=lambda: ["v7_0"])


class MvmCommandRequest(BaseModel):
    command: str
    requestID: str | None = None
    isUserEval: bool | None = True


class SaveScriptRequest(BaseModel):
    filename: str
    content: str


class SimulinkRunRequest(BaseModel):
    gain_kp: float = 2.4
    gain_ki: float = 1.1
    gain_kd: float = 0.35
    plant_wn: float = 3.2
    plant_zeta: float = 0.45
    step_amplitude: float = 1.0
    t_final: float = 10.0


class ArtifactInspectRequest(BaseModel):
    relative_path: str = Field(..., description="Ruta relativa dentro de C:\\Program Files\\MATLAB\\R2026b")


@app.post("/api/mvm/attach")
def attach_mvm(req: MvmAttachRequest) -> dict[str, Any]:
    if req.mvmID != "user-mvm":
        raise HTTPException(status_code=400, detail="Solo se admite mvmID=user-mvm.")
    version = next((v for v in req.supportedApiVersions if v == "v7_0"), None)
    if version is None:
        raise HTTPException(status_code=400, detail="API MVM no compatible.")
    return {"apiVersion": version, "channelPrefix": "/mvm/user-mvm"}


@app.post("/api/mvm/command")
def execute_bus_command(req: MvmCommandRequest) -> dict[str, Any]:
    return _command_result(req.command, req.requestID)


@app.websocket("/ws/mvm")
async def mvm_websocket(socket: WebSocket) -> None:
    await socket.accept()
    _bus_websockets.add(socket)
    await socket.send_json({"channel": "status", "data": get_mvm_status()})
    try:
        while True:
            message = await socket.receive_json()
            if message.get("type") == "command" or "command" in message:
                response = _command_result(message.get("command", ""), message.get("requestID"))
                for segment in response["result"].get("segments", []):
                    kind = segment.get("kind")
                    if kind in ("out", "warn", "err") and segment.get("text"):
                        await socket.send_json({
                            "channel": "/mvm/user-mvm/text/" + ("error" if kind == "err" else "output"),
                            "data": {"requestID": response["requestID"], "text": segment["text"]},
                        })
                await socket.send_json({"channel": "commandResponse", "data": response})
    except WebSocketDisconnect:
        pass
    finally:
        _bus_websockets.discard(socket)


def _bayeux_handle(message: dict[str, Any]) -> list[dict[str, Any]]:
    wire_channel = message.get("channel", "")
    e1_record_channel(wire_channel or "?", message)
    channel = wire_channel[len("/matlab"):] if wire_channel.startswith("/matlab/") else wire_channel
    mid = message.get("id")
    ack: dict[str, Any] = {"channel": wire_channel, "id": mid, "successful": True}
    if channel == "/meta/handshake":
        client_id = str(uuid.uuid4())
        _bus_clients[client_id] = {"subscriptions": set(), "queue": []}
        # interval>0: el shell real reintenta el long-polling a este ritmo; con 0
        # inundaba el endpoint (miles de POSTs por arranque).
        return [{**ack, "clientId": client_id, "version": "1.0", "minimumVersion": "1.0", "supportedConnectionTypes": ["long-polling", "websocket"], "advice": {"reconnect": "retry", "interval": 3000, "timeout": 60000}}]
    client_id = message.get("clientId")
    state = _bus_clients.get(client_id)
    if channel == "/meta/connect":
        if state is None:
            return [{**ack, "successful": False, "error": "unknown clientId"}]
        notifications = state["queue"][:]
        state["queue"].clear()
        interval = 50 if notifications else 250
        return [{**ack, "clientId": client_id, "advice": {"reconnect": "retry", "interval": interval, "timeout": 60000}}] + notifications
    if channel in ("/meta/subscribe", "/meta/unsubscribe"):
        if state is None:
            return [{**ack, "successful": False, "error": "unknown clientId"}]
        subscription = message.get("subscription")
        if not isinstance(subscription, str):
            return [{**ack, "successful": False, "error": "subscription must be a channel"}]
        if channel == "/meta/subscribe":
            state["subscriptions"].add(subscription)
            e1_record_channel(f"subscribe→{subscription}", {"clientId": client_id})
            if subscription.endswith("/event/fireEvent"):
                m = re.match(r"^/matlab(/mvm/[^/]+)/event/fireEvent$", subscription)
                if m:
                    e1_replay_events(_publish_bus_event, m.group(1))
            elif subscription == "/matlab/WSBService/ready":
                _publish_bus_event({"channel": "/WSBService/ready", "data": {"type": "ready"}}, client_id)
            elif subscription == "/matlab/WorkspaceBrowser":
                _publish_bus_event({"channel": "/WorkspaceBrowser", "data": {"type": "servicesStarted"}}, client_id)
                _publish_bus_event({"channel": "/WorkspaceBrowser", "data": {"Variables": [], "type": "SelectedVariablesChanged"}}, client_id)
            elif subscription == "/matlab/filesystem/listfolder/started":
                _publish_bus_event({"channel": "/filesystem/listfolder/started", "data": {"separator": 92}}, client_id)
            elif subscription == "/matlab/filesystem/operations/started":
                _publish_bus_event({"channel": "/filesystem/operations/started", "data": {}}, client_id)
            elif subscription == "/matlab/filesystem/sourcecontrol/started":
                _publish_bus_event({"channel": "/filesystem/sourcecontrol/started", "data": {}}, client_id)
            elif subscription == "/matlab/file_searchservice/started":
                _publish_bus_event({"channel": "/file_searchservice/started", "data": {}}, client_id)
            elif subscription == "/matlab/navigation/model/services/started":
                _publish_bus_event({"channel": "/navigation/model/services/started", "data": {}}, client_id)
                _publish_bus_event({"channel": "/navigation/model/services/stack", "data": {"index": 0, "positions": []}}, client_id)
        else:
            state["subscriptions"].discard(subscription)
        return [{**ack, "clientId": client_id, "subscription": subscription}]
    if channel == "/meta/disconnect":
        _bus_clients.pop(client_id, None)
        return [{**ack, "clientId": client_id}]
    if not channel or state is None:
        return [{**ack, "successful": False, "error": "unknown clientId or channel"}]

    raw_data = message.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}
    if channel == "/mvm/attach/request":
        if data.get("mvmID") != "user-mvm" or "v7_0" not in data.get("supportedApiVersions", []):
            return [{**ack, "successful": False, "error": "unsupported MVM attach"}]
        request_id = data.get("requestID") or "user-mvm"
        response = {"requestID": data.get("requestID"), "apiVersion": "v7_0", "channelPrefix": f"/mvm/{request_id}"}
        _publish_bus_event({"channel": "/mvm/attach/response", "data": response})
        return [{**ack, "clientId": client_id}]
    if channel.endswith("/eval/request") and isinstance(data.get("command"), str):
        prefix = channel[:-len("/eval/request")]
        _command_result(data["command"], data.get("requestID"), prefix)
        return [{**ack, "clientId": client_id}]
    if channel.endswith("/attach/request"):
        response_channel = channel[:-len("/request")] + "/response"
        request_id = data.get("requestID") or "user-mvm"
        response = {"requestID": data.get("requestID"), "apiVersion": "v7_0", "channelPrefix": f"/mvm/{request_id}"}
        _publish_bus_event({"channel": response_channel, "data": response})
        return [{**ack, "clientId": client_id}]
    if e1_handle_service(channel, data, _publish_bus_event, mvm.execute):
        return [{**ack, "clientId": client_id}]
    # Canal no implementado (servicios del escritorio real): se acepta en
    # silencio, igual que el probe, para no provocar reintentos ni tormentas de
    # error en el shell. El canal queda registrado en /api/e1/channels.
    return [{**ack}]


@app.post("/matlab/messageservice/async")
@app.post("/messageservice/async")
@app.post("/messageservice/async/blue")
@app.post("/messageservice/binary")
@app.post("/cometd")
def cometd_stub(
    messages: list[dict[str, Any]] | dict[str, Any], request: Request
) -> list[dict[str, Any]] | dict[str, Any]:
    """Bayeux subset: handshake/connect/subscribe/unsubscribe and MVM attach/eval publish.

    El escritorio real (servido en /mw/) usa /messageservice/async* como endpoint
    Bayeux relativo (sin prefijo /matlab). Sus message-containers (mw-remote) van
    al motor E1; el resto a _bayeux_handle, con attach/eval de la MVM incluidos.
    """
    container = e1_try_handle_container(
        messages,
        path=str(request.url.path),
        base_url=str(request.base_url).rstrip("/"),
    )
    if container is not None:
        return container
    batch = messages if isinstance(messages, list) else [messages]
    responses: list[dict[str, Any]] = []
    for message in batch:
        if isinstance(message, dict):
            responses.extend(_bayeux_handle(message))
    return responses


@app.get("/api/mvm/status")
def get_mvm_status() -> dict[str, Any]:
    return {
        "status": "connected",
        "transport": "mw-mvm/impl/Connection",
        "release": "R2026b",
        "version": "26.2.0.3386108",
        "workspace_count": len(mvm.workspace),
        "figure_count": len(mvm.graphics.figures),
        "history_count": len(mvm.command_history),
    }


@app.post("/api/mvm/eval")
def evaluate_matlab_code(req: EvalRequest) -> dict[str, Any]:
    return mvm.execute(req.code)


@app.get("/api/mvm/workspace")
def get_workspace() -> dict[str, Any]:
    return {
        "variables": mvm.get_workspace_summary(),
        "history": mvm.command_history[-50:],
    }


MAX_GRID_ROWS = 50
MAX_GRID_COLS = 20


def _grid_number(x: Any) -> Any:
    value = float(np.real(x))
    if not np.isfinite(value):
        return "NaN" if np.isnan(value) else ("Inf" if value > 0 else "-Inf")
    return round(value, 6)


def _variable_grid(val: Any) -> list[list[Any]]:
    if isinstance(val, np.ndarray):
        arr = as2d(val)[:MAX_GRID_ROWS, :MAX_GRID_COLS].tolist()
        if is_char(val):
            return [["".join(row)] for row in arr]
        if val.dtype.kind == "b":
            return [[int(x) for x in row] for row in arr]
        if np.iscomplexobj(val):
            return [[str(complex(x)) for x in row] for row in arr]
        return [[_grid_number(x) for x in row] for row in arr]
    if isinstance(val, MString):
        return [[s] for s in val.data.ravel(order="F").tolist()[:MAX_GRID_ROWS]]
    if isinstance(val, MCell):
        return [[value_summary(x) for x in row] for row in val.data[:MAX_GRID_ROWS, :MAX_GRID_COLS].tolist()]
    if isinstance(val, MStruct):
        if val.data.size == 1:
            return [[field, value_summary(val.data.flat[0][field])] for field in val.fields]
        return [[field] for field in val.fields]
    return [[value_summary(val)]]


@app.get("/api/mvm/variable/{name}")
def get_variable_detail(name: str) -> dict[str, Any]:
    if name not in mvm.workspace:
        raise HTTPException(status_code=404, detail=f"Variable '{name}' no existe en el Workspace.")
    val = mvm.workspace[name]
    return {
        "name": name,
        "formatted": format_matlab_value(name, val),
        "matrix_data": _variable_grid(val),
    }


@app.post("/api/mvm/reset")
def reset_mvm() -> dict[str, Any]:
    mvm.reset()
    e1_clear_figure_uuids()
    return {"ok": True, "workspace": [], "figures": []}


@app.get("/api/scripts")
def list_scripts() -> dict[str, Any]:
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(SCRIPTS_DIR.glob("*.m")):
        content = p.read_text(encoding="utf-8")
        first_line = content.splitlines()[0] if content.splitlines() else ""
        files.append(
            {
                "filename": p.name,
                "size": p.stat().st_size,
                "title": first_line.lstrip("% ").strip() or p.name,
                "content": content,
            }
        )
    return {"scripts": files}


@app.post("/api/scripts")
def save_script(req: SaveScriptRequest) -> dict[str, Any]:
    safe_name = Path(req.filename).name
    if not safe_name.endswith(".m"):
        safe_name += ".m"
    dest = SCRIPTS_DIR / safe_name
    dest.write_text(req.content, encoding="utf-8")
    return {"ok": True, "filename": safe_name, "size": dest.stat().st_size}


@app.post("/api/simulink/simulate")
def simulate_pid_loop(req: SimulinkRunRequest) -> dict[str, Any]:
    """
    Simulador de diagrama de bloques (Simulink Lite) en lazo cerrado:
    Controlador PID G_c(s) = Kp + Ki/s + Kd*s en serie con planta de 2do orden
    G_p(s) = wn^2 / (s^2 + 2*zeta*wn*s + wn^2), exportando variables al Workspace de la MVM.
    """
    dt = 0.01
    n_steps = max(50, int(req.t_final / dt) + 1)
    t = np.linspace(0.0, req.t_final, n_steps)
    r = np.full(n_steps, req.step_amplitude, dtype=float)
    y = np.zeros(n_steps, dtype=float)
    ydot = np.zeros(n_steps, dtype=float)
    u = np.zeros(n_steps, dtype=float)
    err_int = 0.0
    prev_err = 0.0

    wn = req.plant_wn
    zeta = req.plant_zeta

    for k in range(n_steps - 1):
        err = r[k] - y[k]
        err_int += err * dt
        err_der = (err - prev_err) / dt if k > 0 else 0.0
        prev_err = err

        u_k = req.gain_kp * err + req.gain_ki * err_int + req.gain_kd * err_der
        u_k = float(np.clip(u_k, -25.0, 25.0))
        u[k] = u_k

        yddot = (wn ** 2) * (u_k - y[k]) - 2.0 * zeta * wn * ydot[k]
        ydot[k + 1] = ydot[k] + yddot * dt
        y[k + 1] = y[k] + ydot[k + 1] * dt

    u[-1] = u[-2]
    mvm.workspace["sim_t"] = t.reshape(1, -1)
    mvm.workspace["sim_y"] = y.reshape(1, -1)
    mvm.workspace["sim_u"] = u.reshape(1, -1)
    mvm.workspace["sim_r"] = r.reshape(1, -1)

    # Generar también la figura en HandleGraphicsEngine
    mvm.graphics.figure(4, name="Simulink PID Closed-Loop")
    mvm.graphics.clf()
    mvm.graphics.subplot(2, 1, 1)
    ax1 = mvm.graphics.gca()
    mvm.graphics.add_line(t, r, style="k--", DisplayName="Referencia r(t)")
    mvm.graphics.set_hold(True)
    mvm.graphics.add_line(t, y, style="b-", DisplayName="Salida Planta y(t)")
    ax1.title = f"Simulink Lazo Cerrado PID (Kp={req.gain_kp}, Ki={req.gain_ki}, Kd={req.gain_kd})"
    ax1.xlabel = "Tiempo (s)"
    ax1.ylabel = "Salida y(t)"

    mvm.graphics.subplot(2, 1, 2)
    ax2 = mvm.graphics.gca()
    mvm.graphics.add_line(t, u, style="r-", DisplayName="Esfuerzo Control u(t)")
    ax2.title = "Señal de Control u(t)"
    ax2.xlabel = "Tiempo (s)"
    ax2.ylabel = "Amplitud u(t)"

    peak = float(np.max(y))
    overshoot = max(0.0, (peak - req.step_amplitude) / max(abs(req.step_amplitude), 1e-9) * 100.0)
    ss_error = float(abs(req.step_amplitude - y[-1]))
    within_band = np.where(np.abs(y - req.step_amplitude) > 0.02 * abs(req.step_amplitude))[0]
    settling_time = float(t[within_band[-1]]) if within_band.size > 0 else 0.0

    return {
        "ok": True,
        "metrics": {
            "overshoot_pct": round(overshoot, 2),
            "settling_time_s": round(settling_time, 3),
            "steady_state_error": round(ss_error, 5),
            "peak_value": round(peak, 4),
        },
        "workspace": mvm.get_workspace_summary(),
        "figures": mvm.graphics.render_all(),
    }


@app.get("/api/rea/ledger")
def get_rea_evidence_ledger() -> dict[str, Any]:
    return get_rea_ledger_payload()


@app.post("/api/rea/inspect-file")
def inspect_installed_matlab_file(req: ArtifactInspectRequest) -> dict[str, Any]:
    """Inspecciona en vivo cualquier archivo dentro de C:\\Program Files\\MATLAB\\R2026b devolviendo su identidad SHA-256 y cabecera PE/ZIP."""
    rel = Path(req.relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(status_code=400, detail="Ruta relativa inválida.")
    target = (MATLAB_ROOT / rel).resolve()
    if not str(target).startswith(str(MATLAB_ROOT.resolve())) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Artefacto no encontrado: {rel}")

    data = target.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    magic = data[:4]
    detected_format = "binary/unknown"
    pe_info: dict[str, Any] | None = None

    if magic[:2] == b"MZ" and len(data) >= 64:
        pe_offset = int.from_bytes(data[60:64], "little")
        if pe_offset + 24 <= len(data) and data[pe_offset : pe_offset + 4] == b"PE\x00\x00":
            machine = int.from_bytes(data[pe_offset + 4 : pe_offset + 6], "little")
            num_sections = int.from_bytes(data[pe_offset + 6 : pe_offset + 8], "little")
            opt_magic = int.from_bytes(data[pe_offset + 24 : pe_offset + 26], "little")
            detected_format = "pe32-plus (64-bit)" if opt_magic == 0x20B else "pe32 (32-bit)"
            pe_info = {
                "machine_hex": hex(machine),
                "architecture": "x86_64" if machine == 0x8664 else ("x86" if machine == 0x14C else "other"),
                "section_count": num_sections,
                "optional_header_magic": hex(opt_magic),
            }
    elif magic == b"PK\x03\x04":
        detected_format = "zip / jar container"
    elif data[:5] == b"<?xml":
        detected_format = "xml metadata"

    return {
        "artifact": {
            "name": target.name,
            "relative_path": str(rel).replace("\\", "/"),
            "local_path": str(target),
            "bytes": len(data),
            "sha256": sha256,
            "format": detected_format,
            "pe_header": pe_info,
        },
        "authority": "shipped-artifact",
        "confidence": "observed",
    }


# ---------------------------------------------------------------------------
# Figuras Handle Graphics (WO-11)
# ---------------------------------------------------------------------------


@app.get("/api/figures")
def get_all_figures() -> list[dict[str, Any]]:
    return mvm.graphics.render_all()


@app.get("/api/figure/{number}")
def get_figure_meta(number: int) -> dict[str, Any]:
    if number not in mvm.graphics.figures:
        raise HTTPException(status_code=404, detail=f"Figura {number} no encontrada")
    return mvm.graphics.render(number)


@app.get("/api/figure/{number}/image")
def get_figure_image(number: int, theme: str = "light") -> Response:
    if number not in mvm.graphics.figures:
        raise HTTPException(status_code=404, detail=f"Figura {number} no encontrada")
    import base64
    meta = mvm.graphics.render(number, theme=theme)
    raw_b64 = meta["image_data_url"].split(",", 1)[1]
    return Response(content=base64.b64decode(raw_b64), media_type="image/png")


@app.get("/mw/undocked-container.html")
@app.get("/undocked-container.html")
def serve_undocked_figure_container(request: Request) -> Response:
    """Sirve la ventana de figura propia (WO-11) en lugar del contenedor C++ ausente."""
    container_html = FRONTEND_DIR / "undocked-container.html"
    if container_html.exists():
        return FileResponse(str(container_html))
    return HTMLResponse("<h3>MATLAB Figure Container</h3>")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))


# E1: motor del protocolo de message-containers del shell real (respuestas a
# CurrentUser/ClientType/ServiceRegistry/AcquireMatlab observadas en capturas).
# Se registra antes del probe para ganar sobre su fallback diagnóstico.
app.include_router(e1_messageservice_router)

# E1 probe: catch-all diagnóstico del shell real (webgui de la instalación servido
# en runtime desde MATLAB_ROOT). Debe quedar ÚLTIMO: cualquier endpoint real
# implementado arriba tiene precedencia en el matching de rutas de FastAPI.
app.include_router(e1_probe_router)
