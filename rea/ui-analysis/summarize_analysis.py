"""Summarize REA analyze-javascript-application evidence for MATLAB R2026b UI components.

Reads rea/ui-analysis/*.json (full CLI evidence envelopes) and writes:
  - ui-components-digest.json : compact machine-readable digest
  - prints a human summary to stdout
"""

from __future__ import annotations

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def summarize(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    name = os.path.splitext(os.path.basename(path))[0]
    if "normalized_result" not in d:
        return {"component": name, "error": str(d)[:300]}
    nr = d["normalized_result"]
    st = nr.get("statistics", {})
    g = nr.get("graph", {})
    sg = nr.get("semantic_graph", {}) or {}
    partial = sorted(
        {
            o["label"]
            for n in g.get("nodes", [])
            for o in n.get("observations", [])
            if o.get("properties", {}).get("parse_status") == "partial"
            and o.get("label") is not None
        }
    )
    roots = [
        {
            "kind": n["kind"],
            "label": (n["observations"][0]["label"] if n.get("observations") else None),
        }
        for n in g.get("nodes", [])
        if n["node_id"] in set(g.get("root_node_ids", []))
    ]
    entry_modules = sorted(
        {
            o["label"]
            for n in g.get("nodes", [])
            if n.get("kind") == "javascript-module"
            for o in n.get("observations", [])
            if o.get("label") is not None
        }
    )
    return {
        "component": name,
        "evidence_id": d.get("evidence_id"),
        "predicate_type": d.get("predicate_type"),
        "operation": d.get("operation"),
        "input_path": nr.get("input_path"),
        "root_artifact_sha256": nr.get("root_artifact_sha256"),
        "inventory_manifest_id": nr.get("inventory_manifest_id"),
        "integrity_contradictions": len(nr.get("integrity_contradictions", [])),
        "statistics": {
            k: st.get(k)
            for k in (
                "relevant_files",
                "parsed_javascript_files",
                "modules",
                "findings",
                "visited_ast_nodes",
                "parse_failures",
                "text_bytes_read",
                "invalid_utf8_files",
            )
        },
        "graph": {
            "nodes": len(g.get("nodes", [])),
            "edges": len(g.get("edges", [])),
            "coverage_status": g.get("coverage", {}).get("status"),
            "truncated": g.get("coverage", {}).get("truncated"),
            "root_nodes": roots,
            "entry_modules": entry_modules[:50],
        },
        "semantic_graph": (
            {
                "nodes": len(sg.get("nodes", [])),
                "relations": len(sg.get("relations", [])),
                "coverage_status": sg.get("coverage", {}).get("status"),
                "truncated": sg.get("coverage", {}).get("truncated"),
                "unknowns": len(sg.get("unknowns", [])),
            }
            if sg
            else None
        ),
        "partial_files": partial,
        "limitations": nr.get("limitations", []),
        "top_limitations": nr.get("limitations", [])[:4],
    }


def main() -> None:
    pattern = os.path.join(HERE, "*.json")
    results = []
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)
        if base in ("ui-components-digest.json", "ui-components-details.json"):
            continue
        try:
            results.append(summarize(path))
        except Exception as exc:  # noqa: BLE001
            results.append({"component": base, "error": repr(exc)})
    digest_path = os.path.join(HERE, "ui-components-digest.json")
    with open(digest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("wrote", digest_path)
    for r in results:
        if "error" in r:
            print(f"- {r['component']}: ERROR {r['error']}")
            continue
        st = r["statistics"]
        print(
            f"- {r['component']}: files={st['relevant_files']} js={st['parsed_javascript_files']} "
            f"modules={st['modules']} nodes={r['graph']['nodes']} "
            f"trunc={r['graph']['truncated']} partial={r['partial_files']}"
        )

    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
