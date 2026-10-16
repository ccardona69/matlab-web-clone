"""Smoke checks del probe E1 (WO-06): sirve el webgui real en runtime desde MATLAB_ROOT.

Contrato mínimo para que la evolución del probe (Devin/Codex) no rompa:
1. /api/e1 describe URLs de lanzamiento y bitácoras.
2. /mw/ exige MATLAB_ROOT (404 si falta: sin instalación no hay shell real).
3. El catch-all prefija 501 y registra en /api/e1/request-log.
4. El handshake Bayeux mínimo responde successful:true con clientId.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app


def test_e1_index_describes_launch_urls() -> None:
    with TestClient(app) as client:
        response = client.get("/api/e1")
    assert response.status_code == 200
    body = response.json()
    assert body["launch"]["desktop_nologin"] == "/mw/"
    assert body["log"] == "/api/e1/request-log"
    assert body["channel_map"] == "/api/e1/channels"


def test_mw_requires_matlab_root(monkeypatch) -> None:
    monkeypatch.delenv("MATLAB_ROOT", raising=False)
    with TestClient(app) as client:
        response = client.get("/mw/")
    assert response.status_code == 404


def test_install_asset_prefixes_require_matlab_root(monkeypatch) -> None:
    # /ui/* y /toolbox/matlab/rich_text_component/* también se sirven en runtime
    # desde MATLAB_ROOT (registry de iconos del toolstrip + chunk del Command
    # Window); sin instalación no hay shell real → 404.
    monkeypatch.delenv("MATLAB_ROOT", raising=False)
    with TestClient(app) as client:
        assert client.get("/ui/icons/registry.json").status_code == 404
        assert (
            client.get(
                "/toolbox/matlab/rich_text_component/src/release/bundle.mwBundle.rtc_R2026b.js"
            ).status_code
            == 404
        )


def test_catch_all_prefixed_and_recorded() -> None:
    with TestClient(app) as client:
        client.delete("/api/e1/request-log")
        response = client.get("/mwactions/bootstrap")
        assert response.status_code == 501
        assert response.json()["e1_probe"] is True

        log = client.get("/api/e1/request-log").json()
        assert any("/mwactions/bootstrap" in entry["path"] for entry in log["requests"])

        cleared = client.delete("/api/e1/request-log").json()
        assert cleared["cleared"] is True
        assert client.get("/api/e1/request-log").json()["count"] == 0


def test_bayeux_probe_handshake() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/messageservice/json",
            json=[{"channel": "/meta/handshake", "version": "1.0"}],
        )
    assert response.status_code == 200
    reply = response.json()[0]
    assert reply["channel"] == "/meta/handshake"
    assert reply["successful"] is True
    assert reply["clientId"].startswith("e1probe-")
