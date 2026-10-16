"""Assemble a canonical REA Evidence bundle from genuine record JSON files.

Replicates createEvidenceBundle() ordering/dedup exactly so the result passes
parseEvidenceBundle's canonicality check (JSON.stringify(parsed) ===
JSON.stringify(canonical)).
"""
import json
import sys


def jstr(v):
    return json.dumps(v, separators=(",", ":"), ensure_ascii=False)


def unique_sorted(values):
    seen = {}
    for v in values:
        seen[jstr(v)] = v
    return [seen[k] for k in sorted(seen.keys())]


def main(paths, out_path):
    records = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            records.append(json.load(f))
    records.sort(key=lambda r: r["evidence_id"])

    artifacts = unique_sorted(
        [
            {
                "digest": {"sha256": s["digest"]["sha256"]},
                "format": s["format"],
                "architecture": s["architecture"],
            }
            for r in records
            if (s := r.get("subject")) is not None
        ]
    )
    providers = unique_sorted(
        [
            {
                "id": r["provider"]["id"],
                "name": r["provider"]["name"],
                "version": r["provider"]["version"],
            }
            for r in records
        ]
    )
    environments = unique_sorted(
        [
            {
                "id": e["id"],
                "platform": e["platform"],
                "architecture": e["architecture"],
                "isolation": e["isolation"],
            }
            for r in records
            if (e := r.get("environment")) is not None
        ]
    )
    scenarios = [
        {
            "evidence_id": r["evidence_id"],
            "operation": r["operation"],
            "authority": r["authority"],
        }
        for r in records
        if r["authority"] == "controlled-replay"
    ]
    captures = [
        {"evidence_id": r["evidence_id"], "predicate_type": r["predicate_type"]}
        for r in records
        if r["predicate_type"] == "rea.process-capture"
    ]

    bundle = {
        "artifacts": artifacts,
        "providers": providers,
        "environments": environments,
        "scenarios": scenarios,
        "captures": captures,
        "unknowns": [],
        "records": records,
    }
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        json.dump(bundle, f, separators=(",", ":"), ensure_ascii=False)
    print(
        json.dumps(
            {
                "out": out_path,
                "records": len(records),
                "artifacts": len(artifacts),
                "providers": len(providers),
                "environments": len(environments),
                "scenarios": len(scenarios),
                "captures": len(captures),
            }
        )
    )


if __name__ == "__main__":
    main(sys.argv[1:-1], sys.argv[-1])
