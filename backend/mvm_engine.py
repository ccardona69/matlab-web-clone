"""
Fachada de la MATLAB Virtual Machine del clon.

Envuelve el intérprete de `backend.matlab` (lexer, parser, ops, interpreter) con la
biblioteca de builtins de `backend.matlab.library` y el motor gráfico Handle Graphics.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from backend.hg_graphics import HandleGraphicsEngine
from backend.matlab.display import FormatState, display, value_summary
from backend.matlab.errors import MatlabError
from backend.matlab.interpreter import Interpreter
from backend.matlab.library import BUILTINS
from backend.matlab.values import bytes_of, class_of, is_char, size_text

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def format_matlab_value(name: str | None, val: Any) -> str:
    return display(name or "ans", val, FormatState())


def _summary_stat(val: Any, reducer: Any) -> str:
    if not isinstance(val, np.ndarray) or val.size == 0 or is_char(val) or val.dtype.kind == "b":
        return "-"
    flat = np.real(val).astype(float).ravel()
    finite = flat[np.isfinite(flat)]
    if finite.size == 0:
        return "-"
    return f"{reducer(finite):.4g}"


class MatlabVirtualMachine:
    """Sesión MATLAB: un intérprete con su workspace base, figuras e historial."""

    def __init__(self, folder: Path = SCRIPTS_DIR) -> None:
        self.graphics = HandleGraphicsEngine()
        self.command_history: list[dict[str, Any]] = []
        self.interpreter = self._new_interpreter(folder)

    def _new_interpreter(self, folder: Path) -> Interpreter:
        return Interpreter(BUILTINS, folder, self.graphics)

    @property
    def workspace(self) -> dict[str, Any]:
        return self.interpreter.base

    def reset(self) -> None:
        self.graphics.close("all")
        self.command_history.clear()
        self.interpreter = self._new_interpreter(self.interpreter.folder)

    def execute(self, code: str) -> dict[str, Any]:
        interp = self.interpreter
        interp.segments = []
        interp.events = []
        interp.warning_log = []
        t0 = time.perf_counter()
        error_msg: str | None = None
        error_id: str | None = None
        try:
            interp.run_source(code)
        except MatlabError as exc:
            error_msg = exc.render()
            error_id = exc.identifier
        except Exception as exc:  # noqa: BLE001 - cualquier fallo interno se muestra como error legible
            logger.exception("Error interno del motor MATLAB")
            error_msg = f"Error interno del clon: {exc}"
        if error_msg is not None:
            interp.segments.append({"kind": "err", "text": error_msg + "\n"})
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        output_text = "".join(seg["text"] for seg in interp.segments if seg["kind"] in ("out", "warn"))
        figures = self.graphics.render_all()
        ws_summary = self.get_workspace_summary()
        if code.strip():
            self.command_history.append({
                "timestamp": time.strftime("%H:%M:%S"),
                "code": code.strip(),
                "output": output_text,
                "error": error_msg,
                "elapsed_ms": elapsed_ms,
            })
        return {
            "ok": error_msg is None,
            "output": output_text,
            "error": error_msg,
            "error_id": error_id,
            "warnings": [dict(w) for w in interp.warning_log],
            "elapsed_ms": elapsed_ms,
            "workspace": ws_summary,
            "figures": figures,
            "history_count": len(self.command_history),
            "segments": [dict(seg) for seg in interp.segments],
            "events": list(interp.events),
        }

    def get_workspace_summary(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name in sorted(self.workspace.keys()):
            val = self.workspace[name]
            item: dict[str, Any] = {
                "name": name,
                "class": class_of(val),
                "size": size_text(val),
                "bytes": bytes_of(val),
                "min": _summary_stat(val, np.min),
                "max": _summary_stat(val, np.max),
                "preview": value_summary(val),
            }
            if isinstance(val, np.ndarray) and np.iscomplexobj(val):
                item["complex"] = True
            items.append(item)
        return items

