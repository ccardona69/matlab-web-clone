"""Genera oracle-apuntes.md a partir de capturas JSONL del profesor.

Curado de los "apuntes": por comando, la salida verbatim de mvmSinks/output
(RICH_OUTPUT decodificado a JSON legible) y data.error de eval/response.

Uso:
    python scripts/make_apuntes.py ml-mirror/_captures/wire-AAAA.jsonl \
        ml-mirror/_captures/_ronda2/wire-BBBB.jsonl \
        -o ml-mirror/_captures/oracle-apuntes.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diff_wire import load_commands


def render(commands, sources: list[str]) -> str:
    lines = [
        "# Apuntes del profesor (wire real R2026b, connector :31515)",
        "",
        "Por comando: salida verbatim de `{prefix}/mvmSinks/output` "
        "(stream 0=stdout, 1=stderr) y campo `data.error` de "
        "`{prefix}/eval/response` cuando existe.",
        "OJO: stderr puede aparecer en la ventana del comando siguiente "
        "(buffer asincrono, comportamiento real del connector).",
        f"Fuentes: {', '.join(sources)}",
        "",
    ]
    for c in commands:
        lines.append(f"## `{c['command']}`")
        for o in c["outputs"]:
            t = o["text"]
            if "<RICH_OUTPUT>" in t:
                pretty = t
                try:
                    inner = t.split("<RICH_OUTPUT>", 1)[1].rsplit("</RICH_OUTPUT>", 1)[0]
                    env = json.loads(inner)
                    pretty = json.dumps(
                        json.loads(env["outputsData"]),
                        ensure_ascii=False,
                        indent=1,
                    )
                    lines.append(
                        f"- stream={o['stream']} `<RICH_OUTPUT>` outputsData decodificado:"
                    )
                except Exception:  # noqa: BLE001 - se vuelca crudo
                    lines.append(f"- stream={o['stream']} `<RICH_OUTPUT>` crudo:")
                lines.append("```json\n" + pretty + "\n```")
            else:
                lines.append(f"- stream={o['stream']} texto: `{t!r}`")
        if c["error"]:
            lines.append(
                f"- eval/response.data.error: "
                f"`{json.dumps(c['error'], ensure_ascii=False)}`"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()

    commands = []
    for p in args.captures:
        commands.extend(load_commands(p))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(commands, [p.name for p in args.captures]), encoding="utf-8")
    print(f"{args.out}: {len(commands)} comandos, {args.out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
