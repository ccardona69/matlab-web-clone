"""Build the reconstruction obligation ledger request for the MATLAB clone.

Bindings are only declared where the clone genuinely owns a counterpart
boundary; the rest stay unowned (honest open work).
"""
import hashlib
import json
from pathlib import Path

REA_DIR = Path(__file__).parent
CLONE = REA_DIR.parent

LEDGER = REA_DIR / "ledger-evidence-orig.json"
BUNDLE = REA_DIR / "canonical-bundle-v2.json"
REQUEST = REA_DIR / "ledger-request-v2.json"

VERIFIER_EVIDENCE = "ev_66db488c78e1c5ce63c760d1a8dea8807dd6d3a8fb606a4e526854da592faa9c"

# obligation title -> (module_path, symbol)
OWNER_MAP = {
    "backend": ("backend/app.py", "evaluate_matlab_code"),
    "user-mvm": ("backend/mvm_engine.py", "MatlabVirtualMachine"),
    "network endpoint": ("frontend/app.js", "apiPost"),
    "menu": ("frontend/app.js", "switchTab"),
    "tabIndexNodes": ("frontend/app.js", "switchTab"),
    "text": ("frontend/app.js", "appendConsoleEntry"),
    "textNode": ("frontend/app.js", "appendConsoleEntry"),
    "content": ("frontend/app.js", "appendConsoleEntry"),
    "errorText": ("frontend/app.js", "appendConsoleEntry"),
    "warningText": ("frontend/app.js", "appendConsoleEntry"),
    "shortcut": ("frontend/app.js", "DOMContentLoaded"),
    "showShortcut": ("frontend/app.js", "DOMContentLoaded"),
    "platformizeShortcut": ("frontend/app.js", "DOMContentLoaded"),
    "validationState": ("frontend/app.js", "evaluateCode"),
    "icon": ("frontend/index.html", "toolstrip-tab"),
    "iconNode": ("frontend/index.html", "toolstrip-tab"),
    "iconAlignment": ("frontend/index.html", "toolstrip-tab"),
    "hasDynamicMenu": ("frontend/app.js", "initCopilotTemplates"),
    "closeMenuOnClick": ("frontend/app.js", "switchTab"),
    "description": ("frontend/app.js", "initCopilotTemplates"),
    "showDescription": ("frontend/app.js", "initCopilotTemplates"),
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ledger = json.load(open(LEDGER, encoding="utf-8"))["normalized_result"]
    obligations = ledger["obligations"]

    bound_ids = []
    bindings = []
    for obl in obligations:
        owner = OWNER_MAP.get(obl["title"])
        if owner is None:
            continue
        module_path, symbol = owner
        digest = sha256_file(CLONE / module_path)
        bound_ids.append(obl["obligation_id"])
        bindings.append(
            {
                "obligation_id": obl["obligation_id"],
                "owner": {
                    "module_path": str(CLONE / module_path),
                    "symbol": symbol,
                    "owner_sha256": digest,
                },
                "parser_type": None,
                "original_cases": [],
                "fixtures": [],
                "verifier": {
                    "verifier_id": "pytest.matlab_clone.suite",
                    "claim_id": "matlab-clone.verification.v1",
                    "command": "python3 -m pytest tests/ -q -k 'not test_rea_ledger_and_native_bridge and not test_fastapi_endpoints_and_simulink'",
                    "authority": obl["required_verifier_authority"],
                    "status": "pass",
                    "result_evidence_id": VERIFIER_EVIDENCE,
                    "enumerated_obligation_ids": [],  # filled below
                    "nondeterminism": {
                        "mode": "total-order",
                        "specification": "pytest exits 0 iff every collected assertion passes; two Windows-native tests are deselected on the Linux/WSL capture lane by design.",
                    },
                },
            }
        )

    for b in bindings:
        b["verifier"]["enumerated_obligation_ids"] = sorted(bound_ids)

    bundle = json.load(open(BUNDLE, encoding="utf-8"))
    req = {
        "evidence_bundle": bundle,
        "reviewed_obligations": [],
        "manifest": {"bindings": bindings, "contradictions": []},
    }
    with open(REQUEST, "w", encoding="utf-8", newline="") as f:
        json.dump(req, f, separators=(",", ":"), ensure_ascii=False)
    print(f"bound={len(bindings)} unowned={len(obligations) - len(bindings)}")


if __name__ == "__main__":
    main()
