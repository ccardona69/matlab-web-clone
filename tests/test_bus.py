"""Contract tests for the minimal mw-mvm/CometD adapter."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import _bus_clients, app, mvm


@pytest.fixture
def client():
    mvm.reset()
    _bus_clients.clear()
    with TestClient(app) as test_client:
        yield test_client
    mvm.reset()
    _bus_clients.clear()


def test_rest_attach_command_returns_correlated_output(client: TestClient) -> None:
    attach = client.post("/api/mvm/attach", json={"mvmID": "user-mvm", "supportedApiVersions": ["v7_0"]})
    assert attach.status_code == 200
    assert attach.json() == {"apiVersion": "v7_0", "channelPrefix": "/mvm/user-mvm"}

    request_id = str(uuid4())
    response = client.post(
        "/api/mvm/command",
        json={"command": "sum(1:100)", "isUserEval": True, "requestID": request_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requestID"] == request_id
    assert "ans =" in body["result"]["output"]
    assert "5050" in body["result"]["output"]


def test_cometd_handshake_subscribe_attach_eval_and_notification(client: TestClient) -> None:
    handshake = client.post(
        "/matlab/messageservice/async",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    assert handshake["successful"] is True
    cid = handshake["clientId"]

    channels = ["/matlab/mvm/attach/response", "/matlab/mvm/user-mvm/text/output", "/matlab/mvm/user-mvm/eval/response"]
    for idx, channel in enumerate(channels, start=2):
        ack = client.post(
            "/cometd",
            json={"channel": "/meta/subscribe", "clientId": cid, "subscription": channel, "id": str(idx)},
        ).json()[0]
        assert ack["successful"] is True

    attach_id = str(uuid4())
    ack = client.post(
        "/cometd",
        json={
            "channel": "/matlab/mvm/attach/request",
            "clientId": cid,
            "data": {"mvmID": "user-mvm", "supportedApiVersions": ["v7_0"], "requestID": attach_id},
            "id": "5",
        },
    ).json()[0]
    assert ack["successful"] is True
    attach_events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "6"}).json()
    attached = next(item for item in attach_events if item.get("channel") == "/matlab/mvm/attach/response")
    assert attached["data"]["requestID"] == attach_id
    assert attached["data"]["channelPrefix"] == "/mvm/user-mvm"

    request_id = str(uuid4())
    ack = client.post(
        "/cometd",
        json={
            "channel": "/matlab/mvm/user-mvm/eval/request",
            "clientId": cid,
            "data": {"command": "sum(1:100)", "isUserEval": True, "requestID": request_id},
            "id": "7",
        },
    ).json()[0]
    assert ack["successful"] is True
    events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "8"}).json()
    output = next(item for item in events if item.get("channel") == "/matlab/mvm/user-mvm/text/output")
    response = next(item for item in events if item.get("channel") == "/matlab/mvm/user-mvm/eval/response")
    assert output["data"]["requestID"] == request_id
    assert "ans =" in output["data"]["text"]
    assert "5050" in output["data"]["text"]
    assert response["data"]["requestID"] == request_id
    assert "5050" in response["data"]["result"]["output"]


def test_websocket_emits_status_output_and_command_response(client: TestClient) -> None:
    request_id = str(uuid4())
    with client.websocket_connect("/ws/mvm") as websocket:
        status = websocket.receive_json()
        assert status["channel"] == "status"
        websocket.send_json({"type": "command", "command": "sum(1:100)", "requestID": request_id})
        output = websocket.receive_json()
        response = websocket.receive_json()
    assert output["channel"] == "/mvm/user-mvm/text/output"
    assert output["data"]["requestID"] == request_id
    assert "5050" in output["data"]["text"]
    assert response["channel"] == "commandResponse"
    assert response["data"]["requestID"] == request_id

