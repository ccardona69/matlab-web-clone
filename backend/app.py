"""
Parte 3B: Servidor FastAPI que implementa el bus mw-mvm/impl/Connection
descubierto por REA en ui/jsconsole (ev_da7a98bba739ec8565820f30f2b2e2db24add0e9699247d2c0c1365d3933e994),
gestión de scripts .m, Workspace, Simulink Lite (bloques dinámicos) y el Ledger de Evidencia REA.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.e1_desktop import router as e1_desktop_router
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

app.include_router(local_assets_router)
app.include_router(mvm_console_router)
# E1 probe: catch-all diagnóstico del shell real — debe quedar ÚLTIMO para que
# cualquier endpoint real implementado arriba tenga precedencia.
app.include_router(e1_desktop_router)

mvm = MatlabVirtualMachine()


class EvalRequest(BaseModel):
    code: str = Field(..., description="Código o comando MATLAB (.m) a evaluar en la MVM")


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


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(str(FRONTEND_DIR / "index.html"))
