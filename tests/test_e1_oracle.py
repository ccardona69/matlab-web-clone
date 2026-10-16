"""Modo oráculo (E1): MATLAB_CONNECTOR_URL proxea el bus al connector real."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import e1_connector
from backend.app import _bus_clients, app, mvm


@pytest.fixture
def client():
    mvm.reset()
    _bus_clients.clear()
    with TestClient(app) as test_client:
        yield test_client
    mvm.reset()
    _bus_clients.clear()


def test_oracle_disabled_uses_emulator(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MATLAB_CONNECTOR_URL", raising=False)
    response = client.post(
        "/messageservice/json",
        json={"uuid": "T1", "messages": {"CurrentUser": [{"apiVersion": "1.2"}]}},
    )
    assert response.status_code == 200
    body = response.json()
    assert "CurrentUserResponse" in body["messages"]
    assert body["messages"]["CurrentUserResponse"][0]["messageFaults"] == []


def test_oracle_enabled_proxies_service_paths(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MATLAB_CONNECTOR_URL", "https://127.0.0.1:31515")
    calls: list[dict] = []

    async def fake_request(method, url, params=None, content=None, headers=None):
        calls.append({"method": method, "url": url, "headers": headers or {}})
        return httpx.Response(
            200,
            content=b'{"messages":{"PingResponse":[{"messageFaults":[],"uuid":"notset"}]}}',
            headers={"content-type": "application/json"},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(e1_connector._proxy_client, "request", fake_request)

    response = client.post(
        "/messageservice/json",
        json={"messages": {"Ping": [{}]}},
        headers={"Origin": "http://localhost:8002", "Referer": "http://localhost:8002/mw/"},
    )
    assert response.status_code == 200
    assert "PingResponse" in response.json()["messages"]

    assert calls, "el oráculo no proxeó la petición"
    forwarded = calls[0]["headers"]
    assert "origin" not in {k.lower() for k in forwarded}
    assert "referer" not in {k.lower() for k in forwarded}
    assert calls[0]["url"].startswith("https://127.0.0.1:31515/messageservice/json")


def test_oracle_enabled_leaves_local_routes_alone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MATLAB_CONNECTOR_URL", "https://127.0.0.1:31515")

    async def fail_request(*args, **kwargs):  # pragma: no cover - no debe llamarse
        raise AssertionError("no debe proxear rutas propias")

    monkeypatch.setattr(e1_connector._proxy_client, "request", fail_request)

    status = client.get("/api/mvm/status")
    assert status.status_code == 200
    e1 = client.get("/api/e1")
    assert e1.status_code == 200


def test_should_proxy_path_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    assert e1_connector.should_proxy("/messageservice/json")
    assert e1_connector.should_proxy("/matlab/messageservice/async")
    assert e1_connector.should_proxy("/matlab/foo/bar")
    assert e1_connector.should_proxy("/msh/matlab/content/x.js")
    assert e1_connector.should_proxy("/rtc/anything")
    assert not e1_connector.should_proxy("/")
    assert not e1_connector.should_proxy("/mw/")
    assert not e1_connector.should_proxy("/api/e1")
    # Assets: disco primero — solo al connector si el archivo local falta.
    monkeypatch.setattr(e1_connector, "_local_asset", lambda rel: None)
    assert e1_connector.should_proxy("/ui/x/y.js")
    monkeypatch.setattr(e1_connector, "_local_asset", lambda rel: object())
    assert not e1_connector.should_proxy("/ui/x/y.js")
