"""Examen de ciego: compara el wire del alumno (emulador) contra el profesor.

Toma dos capturas JSONL de scripts/harvest_wire.py (la del connector real y la
del backend emulado) y compara, por comando, lo que realmente ve el usuario:

- Salida del Command Window: mensajes {prefix}/mvmSinks/output y {prefix}/text/*
  (stream + texto verbatim).
- Errores estructurados: campo data.error de {prefix}/eval/response
  (id MATLAB:xxx, msg, status).

Uso:
    python scripts/diff_wire.py ml-mirror/_captures/wire-XXXX.jsonl \
                                  ml-mirror/_captures/_alumno/wire-YYYY.jsonl
    python scripts/diff_wire.py PROFESOR.jsonl ALUMNO.jsonl --only error
    python scripts/diff_wire.py PROFESOR.jsonl ALUMNO.jsonl --verbose
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

# El profesor (connector real) publica la salida del Command Window SOLO en
# {prefix}/mvmSinks/output; el alumno ademas repite en {prefix}/text/* (el JSD
# usa ambos). El examen compara el canal canonico: mvmSinks/output.
_OUTPUT_SUFFIXES = ("/mvmSinks/output",)


def load_commands(path: Path) -> list[dict[str, Any]]:
    """Reconstruye comando -> eventos de usuario entre 'command' y 'command-done'."""
    commands: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        if entry.get("dir") == "note":
            if entry.get("note") == "command":
                current = {"command": entry["command"], "outputs": [], "error": None}
            elif entry.get("note") == "command-done" and current is not None:
                commands.append(current)
                current = None
            continue
        if entry.get("dir") != "recv" or current is None:
            continue
        body = entry.get("body")
        for msg in body if isinstance(body, list) else []:
            channel = str(msg.get("channel", ""))
            data = msg.get("data") or {}
            if channel.endswith(_OUTPUT_SUFFIXES):
                current["outputs"].append(
                    {
                        "suffix": channel.rsplit("/", 2)[-2] + "/" + channel.rsplit("/", 1)[-1],
                        "stream": data.get("stream"),
                        "text": data.get("text", ""),
                    }
                )
            if channel.endswith("/eval/response") and data.get("error"):
                err = data["error"]
                current["error"] = {"id": err.get("id"), "msg": err.get("msg")}
    return commands


def normalize(text: str) -> str:
    """Limpieza minima para comparar texto: fin de linea y espacios finales."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def compare(prof_cmds: list[dict[str, Any]], alum_cmds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    # Emparejar por (comando, n-esima ocurrencia): el curriculum repite
    # comandos ('who', 'clear all', 'A') y un dict por texto colisiona.
    from collections import defaultdict, deque

    alum_by_cmd: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for c in alum_cmds:
        alum_by_cmd[c["command"]].append(c)
    for prof in prof_cmds:
        queue = alum_by_cmd.get(prof["command"])
        alum = queue.popleft() if queue else None
        prof_text = "".join(o["text"] for o in prof["outputs"])
        row = {
            "command": prof["command"],
            "prof_outputs": len(prof["outputs"]),
            "alum_outputs": len(alum["outputs"]) if alum else None,
            "prof_error": prof["error"],
            "alum_error": alum["error"] if alum else None,
            "text_match": None,
            "error_match": None,
        }
        if alum is not None:
            alum_text = "".join(o["text"] for o in alum["outputs"])
            row["text_match"] = normalize(prof_text) == normalize(alum_text)
            row["prof_text"] = prof_text
            row["alum_text"] = alum_text
            if prof["error"] or alum["error"]:
                row["error_match"] = (prof["error"] or {}).get("id") == (
                    alum["error"] or {}
                ).get("id") and (prof["error"] or {}).get("msg") == (
                    alum["error"] or {}
                ).get("msg")
        rows.append(row)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff wire profesor vs alumno")
    ap.add_argument("profesor", type=Path)
    ap.add_argument("alumno", type=Path)
    ap.add_argument("--only", help="filtra comandos que contengan el texto")
    ap.add_argument("--verbose", action="store_true", help="muestra diffs de texto")
    args = ap.parse_args()

    prof = load_commands(args.profesor)
    alum = load_commands(args.alumno)
    if not prof:
        print(f"sin comandos en {args.profesor}", file=sys.stderr)
        return 2
    rows = compare(prof, alum)
    if args.only:
        rows = [r for r in rows if args.only in r["command"]]

    ok_text = ok_err = missing = 0
    for r in rows:
        if r["alum_outputs"] is None:
            missing += 1
            print(f"  FALTA   {r['command']!r:50s}")
            continue
        t = r["text_match"]
        e = r["error_match"]
        ok_text += bool(t)
        if e is None or e:
            ok_err += 1
        status = "OK    " if t and (e is None or e) else "DIFF  "
        det = []
        if not t:
            det.append(f"texto ({r['prof_outputs']} vs {r['alum_outputs']} sinks)")
        if e is False:
            det.append(f"error {r['prof_error']} vs {r['alum_error']}")
        print(f"  {status} {r['command']!r:50s} {'; '.join(det)}")
        if args.verbose and not t:
            diff = difflib.unified_diff(
                normalize(r["prof_text"]).splitlines(),
                normalize(r["alum_text"]).splitlines(),
                fromfile="profesor",
                tofile="alumno",
                lineterm="",
            )
            for line in list(diff)[:20]:
                print("        " + line)

    total = len(rows) - missing
    print()
    print(
        f"texto: {ok_text}/{total} identicos | errores: {ok_err}/{total} | "
        f"sin respuesta del alumno: {missing}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
