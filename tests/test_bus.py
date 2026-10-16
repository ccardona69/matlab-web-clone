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
    assert attached["data"]["channelPrefix"] == f"/mvm/{attach_id}"

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


def test_real_shell_wire_sequence_feval_sinks_and_services(client: TestClient) -> None:
    """Secuencia wire real del escritorio (capturada en e1-request-map):

    handshake → subscribe response channels → attach → mvmSinks →
    subscribeEvent → feval(function=eval) → /meta/connect drena todas las
    respuestas correlacionadas por requestID.
    """
    handshake = client.post(
        "/messageservice/async",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]

    subscriptions = [
        "/matlab/mvm/attach/response",
        "/matlab/mvm/user-mvm/feval/response",
        "/matlab/mvm/user-mvm/mvmSinks/response",
        "/matlab/mvm/user-mvm/subscribeEvent/response",
        "/matlab/mvm/user-mvm/text/output",
        "/matlab/mvm/user-mvm/text/error",
        "/matlab/mvm/user-mvm/event/fireEvent",
        "/matlab/matlab/settingsChannel/Response/UUID1",
        "/matlab/shortcuts/model/services/response/add",
    ]
    for idx, channel in enumerate(subscriptions, start=2):
        ack = client.post(
            "/messageservice/async",
            json={"channel": "/meta/subscribe", "clientId": cid, "subscription": channel, "id": str(idx)},
        ).json()[0]
        assert ack["successful"] is True

    def publish(channel: str, data: dict, mid: str) -> None:
        ack = client.post(
            "/messageservice/async",
            json={"channel": channel, "clientId": cid, "data": data, "id": mid},
        ).json()[0]
        assert ack["successful"] is True

    publish("/matlab/mvm/attach/request", {"mvmID": "user-mvm", "supportedApiVersions": ["v7_0"], "requestID": "AT1"}, "10")
    publish("/matlab/mvm/user-mvm/mvmSinks/request", {"outSinkTraits": {}, "errSinkTraits": {}, "requestID": "SK1"}, "11")
    publish("/matlab/mvm/user-mvm/subscribeEvent/request", {"eventName": "mlutil::io::UncaughtInterruptEvent", "requestID": "SE1"}, "12")
    publish("/matlab/mvm/user-mvm/subscribeEvent/request", {"eventName": "mlutil::prompt::PromptEvent", "requestID": "SE2"}, "12b")
    publish("/matlab/mvm/user-mvm/feval/request", {"function": "eval", "rhsArgs": ["1+1"], "numOutputsExpected": 0, "requestID": "FE1"}, "13")
    publish("/matlab/matlab/settingsChannel/Request", {"type": "GetSettingMessage", "SettingName": "matlab.fonts.size", "channel": "/matlab/settingsChannel/Response/UUID1", "uuid": "ST1"}, "14")
    publish("/matlab/shortcuts/model/services/request/add/global", {"uid": "U1", "clientId": "C1", "requestId": 27, "payload": {"actions": ["sysobj.newBasic"]}}, "15")

    events = client.post(
        "/messageservice/async",
        json={"channel": "/meta/connect", "clientId": cid, "id": "16"},
    ).json()

    by_channel = {}
    for item in events:
        by_channel.setdefault(item.get("channel"), []).append(item)

    attach = by_channel["/matlab/mvm/attach/response"][0]
    assert attach["data"]["requestID"] == "AT1"
    assert attach["data"]["channelPrefix"] == "/mvm/AT1"

    assert by_channel["/matlab/mvm/user-mvm/mvmSinks/response"][0]["data"]["requestID"] == "SK1"
    assert by_channel["/matlab/mvm/user-mvm/subscribeEvent/response"][0]["data"]["requestID"] == "SE1"

    # fireEvent: el motor real dispara PromptEvent/IdleEvent al suscribirse
    # (isIdle=true → `>>` Ready) y en cada feval (Busy → Ready).
    fires = by_channel["/matlab/mvm/user-mvm/event/fireEvent"]
    prompt_fires = [
        f for f in fires
        if "mlutil::prompt::PromptEvent" in f["data"]["eventData"]["filterTags"]
    ]
    assert any(f["data"]["eventData"]["isIdle"] is True for f in prompt_fires)
    assert any(f["data"]["eventData"]["isIdle"] is False for f in prompt_fires)

    output = by_channel["/matlab/mvm/user-mvm/text/output"][0]
    assert output["data"]["requestID"] == "FE1"
    assert "ans" in output["data"]["text"] and "2" in output["data"]["text"]
    feval = by_channel["/matlab/mvm/user-mvm/feval/response"][0]
    assert feval["data"]["requestID"] == "FE1"
    assert isinstance(feval["data"]["result"], list)

    settings = by_channel["/matlab/matlab/settingsChannel/Response/UUID1"][0]
    assert settings["data"]["uuid"] == "ST1"
    assert settings["data"]["type"] == "GetSettingMessageResponse"

    shortcut_replies = by_channel.get("/matlab/shortcuts/model/services/response/add") or by_channel[
        "/matlab/shortcuts/model/services/response/add/global"
    ]
    assert shortcut_replies[0]["data"]["uid"] == "U1"
    assert shortcut_replies[0]["data"]["requestId"] == 27


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

