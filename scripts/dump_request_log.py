"""Vuelca /api/e1/request-log del oráculo (:8004) a disco INMEDIATAMENTE.

Uso: python scripts/dump_request_log.py [salida.jsonl] [filtro-regex]

Cada línea de salida es un evento wire del request log. Con --filtro solo se
escriben los eventos que contengan el patrón (útil para cosechas por tema).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "ml-mirror/_captures_paneles/wire-live.jsonl"
    pattern = sys.argv[2] if len(sys.argv) > 2 else None
    data = json.loads(urllib.request.urlopen("http://127.0.0.1:8004/api/e1/request-log").read())
    items = data["requests"]
    rx = re.compile(pattern) if pattern else None
    kept = 0
    with open(out, "w", encoding="utf-8", errors="replace") as fh:
        for entry in items:
            text = json.dumps(entry)
            if rx and not rx.search(text):
                continue
            fh.write(text + "\n")
            kept += 1
    print(f"{kept}/{len(items)} eventos -> {out}")


if __name__ == "__main__":
    main()
