"""
Suite de pruebas automatizadas para el clon de MATLAB R2026b impulsado por REA.
Cubre casos normales, casos límite y errores esperados.
"""

from __future__ import annotations

import numpy as np
from fastapi.testclient import TestClient

from backend.app import app
from backend.mvm_engine import MatlabVirtualMachine
from backend.rea_ledger import get_rea_ledger_payload

client = TestClient(app)


def test_rea_ledger_and_native_bridge() -> None:
    payload = get_rea_ledger_payload()
    assert payload["release"] == "R2026b"
    assert payload["evidence_count"] == 9
    bridge = payload["native_bridge_status"]
    assert bridge["matlab_root_exists"] is True
    assert bridge["libMatlabEngine"]["matches_evidence"] is True
    assert bridge["native_dll_loaded"] is True
    resolved = [b for b in bridge["pinvoke_bindings"] if b["symbol_resolved"]]
    assert len(resolved) == 11


def test_mvm_matrix_and_linear_algebra() -> None:
    vm = MatlabVirtualMachine()
    res = vm.execute("M = magic(4);\ns = sum(M(:));\nd = det([4 -1 1; -1 4.25 2.75; 1 2.75 3.5]);")
    assert res["ok"] is True
    assert vm.workspace["M"].shape == (4, 4)
    assert float(vm.workspace["s"].item()) == 136.0
    assert abs(float(vm.workspace["d"].item()) - 16.0) < 1e-6


def test_mvm_backslash_and_1based_indexing() -> None:
    vm = MatlabVirtualMachine()
    res = vm.execute(
        "A = [4 -1 1; -1 4.25 2.75; 1 2.75 3.5];\n"
        "b = [4; 6; 7.25];\n"
        "x = A \\ b;\n"
        "elem = A(2, 3);\n"
        "A(1, 1) = 10;"
    )
    assert res["ok"] is True
    assert abs(float(vm.workspace["elem"].item()) - 2.75) < 1e-9
    assert abs(float(vm.workspace["A"][0, 0]) - 10.0) < 1e-9
    assert np.allclose(vm.workspace["x"].ravel(), [1.0, 1.0, 1.0], atol=1e-6)


def test_mvm_control_flow_and_user_function() -> None:
    vm = MatlabVirtualMachine()
    code = """
function [y] = sq_plus_one(x)
    y = x.^2 + 1;
end
acc = 0;
for k = 1:4
    if k > 2
        acc = acc + sq_plus_one(k);
    else
        acc = acc + k;
    end
end
"""
    res = vm.execute(code)
    assert res["ok"] is True
    # k=1 -> +1 (1), k=2 -> +2 (3), k=3 -> +(9+1)=13, k=4 -> +(16+1)=30
    assert float(vm.workspace["acc"].item()) == 30.0


def test_mvm_ode45_and_graphics() -> None:
    vm = MatlabVirtualMachine()
    code = """
f = @(t, y) [-0.5 * y(1)];
[t, Y] = ode45(f, [0, 2], [1.0]);
figure(1);
clf;
plot(t, Y, 'b-');
title('Decaimiento Exponencial');
"""
    res = vm.execute(code)
    assert res["ok"] is True
    assert len(res["figures"]) == 1
    assert res["figures"][0]["image_data_url"].startswith("data:image/png;base64,")
    assert abs(float(vm.workspace["Y"][-1, 0]) - np.exp(-1.0)) < 1e-3


def test_mvm_syntax_error_reported_cleanly() -> None:
    vm = MatlabVirtualMachine()
    res = vm.execute("A = [1 2; 3 4;\n???invalid_token$$$")
    assert res["ok"] is False
    assert res["error"] is not None


def test_fastapi_endpoints_and_simulink() -> None:
    status_res = client.get("/api/mvm/status")
    assert status_res.status_code == 200
    assert status_res.json()["transport"] == "mw-mvm/impl/Connection"

    eval_res = client.post("/api/mvm/eval", json={"code": "Q = magic(3)"})
    assert eval_res.status_code == 200
    assert eval_res.json()["ok"] is True

    var_res = client.get("/api/mvm/variable/Q")
    assert var_res.status_code == 200
    assert len(var_res.json()["matrix_data"]) == 3

    sim_res = client.post("/api/simulink/simulate", json={"gain_kp": 3.0, "gain_ki": 1.2, "gain_kd": 0.4})
    assert sim_res.status_code == 200
    assert sim_res.json()["ok"] is True
    assert "overshoot_pct" in sim_res.json()["metrics"]

    probe_res = client.post("/api/rea/inspect-file", json={"relative_path": "bin/win64/MATLAB.exe"})
    assert probe_res.status_code == 200
    assert probe_res.json()["artifact"]["sha256"] == "5380cc41fc6f075ba911b501216c1b9f20df800866358be5b92bdcdb879b596d"

    bad_probe = client.post("/api/rea/inspect-file", json={"relative_path": "../outside.exe"})
    assert bad_probe.status_code == 400


def test_all_bundled_matlab_scripts_execute_cleanly() -> None:
    scripts_res = client.get("/api/scripts")
    assert scripts_res.status_code == 200
    scripts = scripts_res.json()["scripts"]
    assert len(scripts) >= 4
    for s in scripts:
        vm = MatlabVirtualMachine()
        res = vm.execute(s["content"])
        assert res["ok"] is True, f"Fallo en script {s['filename']}: {res['error']}"

