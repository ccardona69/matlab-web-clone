"""WO-13 — Examen permanente: replay de apuntes del profesor (wire JSONL) en pytest.

Reproduce cada comando capturado del connector real de MATLAB R2026b contra
`MatlabVirtualMachine.execute` con workspace persistente por sesión de captura,
verificando tanto la salida visible (`mvmSinks/output`) como los errores
estructurados (`eval/response.data.error`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.e1_bus_services import _wrap_rich_output
from backend.mvm_engine import MatlabVirtualMachine
from scripts.diff_wire import load_commands, normalize

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CAPTURES_DIR = _REPO_ROOT / "ml-mirror" / "_captures"

# Comandos cuya salida varía según reloj, temporizador, RNG o estado de archivos.
_NON_DETERMINISTIC_REASONS: dict[str, str] = {
    "date": "No determinista: devuelve la fecha actual del reloj del sistema",
    "now": "No determinista: datenum depende de la fecha/hora actual",
    "datetime('now')": "No determinista: timestamp al segundo depende del reloj actual",
    "tic; toc": "No determinista: tiempo transcurrido depende de la CPU",
    "randperm(5)": "No determinista: permutación sujeta al estado del generador aleatorio",
}

_FILESYSTEM_PREFIXES: tuple[str, ...] = (
    "save(",
    "load(",
    "delete(",
    "fopen(",
    "fid = fopen(",
    "fclose(",
)

# En la captura R2026b de ronda 1, el connector acumulaba variables de una
# corrida previa en la misma sesión de MATLAB (`c`, `i`, `n`, `s`, `x`, `y`),
# y el canal `mvmSinks/output` entregó stderr/stdout asíncronos rezagados en la
# ventana del comando siguiente (documentado en WO-08).
_SESSION_XFAILS: dict[tuple[str, int, str], str] = {
    (
        "wire-20261016-220151.jsonl",
        2,
        "a",
    ): "WO-08 stderr asíncrono: arrastra error de undefined_fn_xyz en la ventana de 'a'",
    (
        "wire-20261016-220151.jsonl",
        4,
        "format long; pi",
    ): "WO-08 stderr asíncrono: arrastra error de sintaxis de 'b = ' en la ventana siguiente",
    (
        "wire-20261016-220151.jsonl",
        6,
        "format rat; pi",
    ): "WO-08 stderr asíncrono: arrastra 'Arrays have incompatible sizes' en la ventana siguiente",
    (
        "wire-20261016-220151.jsonl",
        51,
        "who",
    ): "Estado de sesión: la captura del profesor arrastraba variables previas (c, i, n, s, x, y)",
    (
        "wire-20261016-220151.jsonl",
        52,
        "whos",
    ): "Estado de sesión: la captura del profesor arrastraba variables previas (c, i, n, s, x, y)",
    (
        "wire-20261016-220151.jsonl",
        56,
        "who",
    ): "Estado de sesión: tras 'clear a' persisten en el profesor variables de sesión previa",
    (
        "wire-20261016-220151.jsonl",
        68,
        "mean([1 2 3 4])",
    ): "WO-08 stderr asíncrono: arrastra \"Undefined function 'A'\" en la ventana siguiente",
    (
        "wire-20261016-220151.jsonl",
        70,
        "max([3 1 4 1 5])",
    ): "WO-08 stderr asíncrono: arrastra \"Undefined variable 'A'\" en la ventana siguiente",
    (
        "wire-20261016-220151.jsonl",
        71,
        "sort([3 1 4 1 5])",
    ): "WO-08 buffer asíncrono: incluye warning/output rezagado de inv([1 2; 2 4])",
    (
        "wire-20261016-220151.jsonl",
        73,
        "mod(10, 3)",
    ): "WO-08 stderr asíncrono: arrastra 'Error using sqrt' de comando previo",
    (
        "wire-20261016-221912.jsonl",
        5,
        "exist('magic')",
    ): "WO-08 buffer asíncrono: incluye salida rezagada de 'c' del connector en la ventana",
    (
        "wire-20261016-221912.jsonl",
        40,
        "B = [4 2; 2 3]; chol(B)",
    ): "WO-08 buffer asíncrono: incluye salida rezagada \"ans = 'dos'\" del connector",
}


def discover_capture_files(captures_dir: Path = _CAPTURES_DIR) -> list[Path]:
    """Descubre capturas JSONL en `ml-mirror/_captures/wire-*.jsonl` y `_ronda*/wire-*.jsonl`.

    Si en un mismo directorio de ronda existen varios intentos de captura,
    selecciona el último cronológico de esa ronda (las 3 rondas suman 258 comandos).
    """
    if not captures_dir.is_dir():
        return []
    root_captures = sorted(captures_dir.glob("wire-*.jsonl"))
    ronda_captures = sorted(captures_dir.glob("_ronda*/wire-*.jsonl"))
    latest_by_round: dict[Path, Path] = {}
    for path in root_captures + ronda_captures:
        latest_by_round[path.parent] = path
    return list(latest_by_round.values())


def _render_sink_output(result: dict[str, Any]) -> str:
    """Reconstruye el texto publicado en `mvmSinks/output` a partir de `result['segments']`."""
    chunks: list[str] = []
    for segment in result.get("segments") or []:
        kind = segment.get("kind")
        if kind not in ("out", "warn", "err"):
            continue
        if not (segment.get("text") or segment.get("rich") or segment.get("sink_text")):
            continue
        rich = segment.get("rich")
        if isinstance(rich, list):
            chunks.append("".join(_wrap_rich_output(r) for r in rich))
        elif isinstance(rich, dict):
            chunks.append(_wrap_rich_output(rich))
        else:
            chunks.append(segment.get("sink_text") or segment.get("text", ""))
    return "".join(chunks)


def _xfail_reason(capture_name: str, index: int, command: str) -> str | None:
    key = (capture_name, index, command)
    if key in _SESSION_XFAILS:
        return _SESSION_XFAILS[key]
    if command in ("date", "datetime('now')", "tic; toc"):
        return _NON_DETERMINISTIC_REASONS[command]
    return None


def _fallback_xfail_reason(command: str) -> str | None:
    if command in _NON_DETERMINISTIC_REASONS:
        return _NON_DETERMINISTIC_REASONS[command]
    if command in ("who", "whos") or command.startswith(("who ", "whos ")):
        return "Estado de sesión: salida de who/whos depende del workspace acumulado"
    if command.startswith(_FILESYSTEM_PREFIXES):
        return "Comando de filesystem real dependiente del entorno de ejecución"
    return None


def _build_params() -> list[Any]:
    files = discover_capture_files()
    params: list[Any] = []
    for capture_path in files:
        commands = load_commands(capture_path)
        for idx, entry in enumerate(commands):
            cmd = entry["command"]
            reason = _xfail_reason(capture_path.name, idx, cmd)
            marks = [pytest.mark.xfail(reason=reason, strict=False)] if reason else []
            params.append(
                pytest.param(
                    capture_path.name,
                    idx,
                    cmd,
                    entry,
                    id=cmd,
                    marks=marks,
                )
            )
    return params


_PARAMS = _build_params()
_SESSION_VMS: dict[str, MatlabVirtualMachine] = {}


@pytest.mark.skipif(
    not _PARAMS,
    reason="Sin capturas wire-*.jsonl en ml-mirror/_captures/ (entorno CI sin apuntes locales)",
)
@pytest.mark.parametrize(
    ("capture_name", "cmd_index", "command", "expected"),
    _PARAMS or [pytest.param("", 0, "", {}, id="no-captures")],
)
def test_oracle_replay(
    capture_name: str,
    cmd_index: int,
    command: str,
    expected: dict[str, Any],
) -> None:
    if not capture_name:
        pytest.skip("Sin capturas del profesor disponibles")

    vm = _SESSION_VMS.get(capture_name)
    if vm is None or cmd_index == 0:
        vm = MatlabVirtualMachine()
        _SESSION_VMS[capture_name] = vm

    result = vm.execute(command)

    actual_sink_text = _render_sink_output(result)
    expected_sink_text = "".join(o["text"] for o in expected["outputs"])

    expected_err = expected.get("error")
    actual_err = result.get("error_data")

    text_matches = normalize(actual_sink_text) == normalize(expected_sink_text)
    error_matches = True
    if expected_err is not None or actual_err is not None:
        error_matches = (
            (actual_err or {}).get("id") == (expected_err or {}).get("id")
            and (actual_err or {}).get("msg") == (expected_err or {}).get("msg")
        )

    if not (text_matches and error_matches):
        fallback_reason = _fallback_xfail_reason(command)
        if fallback_reason is not None:
            pytest.xfail(fallback_reason)

    assert normalize(actual_sink_text) == normalize(expected_sink_text), (
        f"[{capture_name}#{cmd_index}] Salida mvmSinks/output distinta para {command!r}"
    )
    if expected_err is not None or actual_err is not None:
        assert (actual_err or {}).get("id") == (expected_err or {}).get("id"), (
            f"[{capture_name}#{cmd_index}] error.id distinto para {command!r}"
        )
        assert (actual_err or {}).get("msg") == (expected_err or {}).get("msg"), (
            f"[{capture_name}#{cmd_index}] error.msg distinto para {command!r}"
        )
