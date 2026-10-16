"""Deep-detail extractor for REA JS application evidence files.

Writes ui-components-details.json with, per component:
  - namespaces histogram (module label prefix)
  - endpoints / workers / chunks / source maps
  - notable module labels
  - coverage limits
"""

from __future__ import annotations

import glob
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

KEEP_PREFIXES = (
    "mw-",
    "MW/",
    "jsconsole",
    "academy",
    "trainer",
    "help",
    "install",
    "builtins",
    "equationrenderer",
    "webgui",
    "appshell",
)


def extract(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    name = os.path.splitext(os.path.basename(path))[0]
    if "normalized_result" not in d:
        return {"component": name, "error": "no normalized_result"}
    nr = d["normalized_result"]
    g = nr["graph"]
    modules, endpoints, others = [], [], {}
    for n in g["nodes"]:
        kind = n["kind"]
        label = n["observations"][0]["label"] if n.get("observations") else None
        if kind == "javascript-module":
            modules.append(label)
        elif kind == "endpoint":
            endpoints.append(label)
        elif kind in ("worker", "javascript-chunk", "source-map", "storage"):
            others.setdefault(kind, []).append(label)
    pref = Counter(
        (l.split("/")[0] if l else "NONE") for l in modules
    )
    notable = sorted(
        l for l in modules if l and any(l.startswith(p) for p in KEEP_PREFIXES)
    )
    limits = g.get("coverage", {}).get("limits", [])
    return {
        "component": name,
        "evidence_id": d.get("evidence_id"),
        "module_count": len(modules),
        "namespace_histogram": dict(pref.most_common(40)),
        "endpoints": sorted({e for e in endpoints if e}),
        "other_nodes": {k: sorted({v for v in vals if v}) for k, vals in others.items()},
        "notable_modules": sorted(set(notable))[:200],
        "coverage_limits": limits,
    }


def main() -> None:
    results = []
    for path in sorted(glob.glob(os.path.join(HERE, "*.json"))):
        base = os.path.basename(path)
        if base in ("ui-components-digest.json", "ui-components-details.json"):
            continue
        try:
            results.append(extract(path))
        except json.JSONDecodeError:
            continue  # still being written
        except Exception as exc:  # noqa: BLE001
            results.append({"component": base, "error": repr(exc)})
    out = os.path.join(HERE, "ui-components-details.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("wrote", out, "components:", len(results))


if __name__ == "__main__":
    main()
