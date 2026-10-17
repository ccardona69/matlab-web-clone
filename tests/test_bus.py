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
        "/matlab/mvm/user-mvm/eval/response",
        "/matlab/mvm/user-mvm/mvmSinks/output",
        "/matlab/matlab/settingsChannel/Response/UUID1",
        "/matlab/shortcuts/model/services/response/add",
        "/matlab/executionstateservice/hasinitialized",
        "/matlab/regfwk/apis/resourceList/C1",
        "/matlab/fctrl/response/addcb",
    ]
    for idx, channel in enumerate(subscriptions, start=2):
        ack = client.post(
            "/messageservice/async",
            json={"channel": "/meta/subscribe", "clientId": cid, "subscription": channel, "id": str(idx)},
        ).json()[0]
        assert ack["successful"] is True

    def publish(channel: str, data: object, mid: str) -> None:
        ack = client.post(
            "/messageservice/async",
            json={"channel": channel, "clientId": cid, "data": data, "id": mid},
        ).json()[0]
        assert ack["successful"] is True

    publish("/matlab/mvm/attach/request", {"mvmID": "user-mvm", "supportedApiVersions": ["v7_0"], "requestID": "AT1"}, "10")
    publish("/matlab/mvm/user-mvm/mvmSinks/request", {"outSinkTraits": {}, "errSinkTraits": {}, "requestID": "SK1"}, "11")
    publish("/matlab/mvm/user-mvm/subscribeEvent/request", {"eventName": "mlutil::io::UncaughtInterruptEvent", "requestID": "SE1"}, "12")
    publish("/matlab/mvm/user-mvm/subscribeEvent/request", {"eventName": "mlutil::prompt::PromptEvent", "requestID": "SE2"}, "12b")
    publish("/matlab/editor/event-notification-request", {"messageChannel": "/executionstateservice/hasinitialized", "requesterId": "REQ_INIT_1"}, "12c")
    publish("/matlab/regfwk/apis/getResourceList", {"uuid": "RG1", "clientId": "C1", "resourceSpecifications": [{"resourceName": "desktopPlugins"}]}, "12d")
    publish("/matlab/fctrl/addcb", {"id": "FC1", "name": "RichCmdWin", "mvm": "user-mvm"}, "12e")
    publish("/matlab/matlab/js_log/diagnosticSpecDataRequest", "queryLoggingStatus", "12f")
    publish("/matlab/mvm/user-mvm/eval/request", {"command": "builtin('_installSink', true);", "requestID": "EV_SINK"}, "12g")
    publish("/matlab/mvm/user-mvm/feval/request", {"function": "eval", "rhsArgs": ["1+1"], "numOutputsExpected": 0, "requestID": "FE1"}, "13")
    publish("/matlab/matlab/settingsChannel/Request", {"type": "GetSettingMessage", "SettingGroup": "matlab.fonts.codefont", "SettingName": "Name", "channel": "/matlab/settingsChannel/Response/UUID1", "uuid": "ST1"}, "14")
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
    assert settings["data"]["settingData"]["SettingValue"] == "Monospaced"

    has_init = by_channel["/matlab/executionstateservice/hasinitialized"][0]
    assert has_init["data"]["requesterId"] == "REQ_INIT_1"
    assert "isInitialized" in has_init["data"]["dataMap"]

    regfwk = by_channel["/matlab/regfwk/apis/resourceList/C1"][0]
    assert regfwk["data"]["uuid"] == "RG1"
    assert regfwk["data"]["resourcesFilesData"] == []

    fctrl = by_channel["/matlab/fctrl/response/addcb"][0]
    assert fctrl["data"]["id"] == "FC1"
    assert fctrl["data"]["value"] == 1

    sink_eval = by_channel["/matlab/mvm/user-mvm/eval/response"][0]
    assert sink_eval["data"]["requestID"] == "EV_SINK"

    sink_out = by_channel["/matlab/mvm/user-mvm/mvmSinks/output"][0]
    assert sink_out["data"]["stream"] == 0
    assert "ans" in sink_out["data"]["text"]

    shortcut_replies = by_channel.get("/matlab/shortcuts/model/services/response/add") or by_channel[
        "/matlab/shortcuts/model/services/response/add/global"
    ]
    assert shortcut_replies[0]["data"]["uid"] == "U1"
    assert shortcut_replies[0]["data"]["requestId"] == 27


def test_workspace_browser_who_protocol(client: TestClient) -> None:
    """WO-09: el documento 'who' recibe el modelo mf de variables por
    eventTypes (wire real: 1 tamaño, 3/4/5/6 props, 2 partialData)."""
    import json as _json

    handshake = client.post(
        "/matlab/messageservice/async",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]

    ack = client.post(
        "/cometd",
        json={"channel": "/meta/subscribe", "clientId": cid,
              "subscription": "/matlab/WorkspaceBrowser_who", "id": "2"},
    ).json()[0]
    assert ack["successful"] is True

    def send(channel: str, data: dict, msg_id: str) -> list[dict]:
        client.post("/cometd", json={"channel": channel, "clientId": cid,
                                     "id": msg_id, "data": data})
        connect = client.post(
            "/cometd",
            json={"channel": "/meta/connect", "clientId": cid, "id": msg_id + "c"},
        ).json()
        return [m for m in connect if m.get("channel") == "/matlab/WorkspaceBrowser_who"]

    client.post("/cometd", json={"channel": "/matlab/DesktopWSB", "clientId": cid,
                                 "id": "3", "data": {"type": "WSBStartup"}})
    # Crear variables: escalar (literal) y matriz 4x4 (metadato "4×4 double").
    mvm.workspace["a"] = 5
    mvm.workspace["A"] = __import__("numpy").array([[1, 2, 3, 4]] * 4)

    pushes = send("/matlab/WorkspaceBrowser_who", {"eventType": 19}, "4")
    types = [m["data"]["eventType"] for m in pushes]
    assert 1 in types

    pushes = send("/matlab/WorkspaceBrowser_who", {"eventType": 20}, "4b")
    types = [m["data"]["eventType"] for m in pushes]
    assert 3 in types

    pushes = send("/matlab/WorkspaceBrowser_who",
                  {"eventType": 21, "startColumn": 0, "endColumn": 3}, "5")
    cols = next(m for m in pushes if m["data"]["eventType"] == 4)
    assert [p["HeaderName"] for p in cols["data"]["properties"]] == [
        "Name", "Value", "Size", "Class"]

    pushes = send("/matlab/WorkspaceBrowser_who",
                  {"eventType": 11, "startRow": 0, "endRow": -1,
                   "startColumn": 0, "endColumn": 3}, "6")
    data_msg = next(m for m in pushes if m["data"]["eventType"] == 2)
    grid = _json.loads(data_msg["data"]["partialData"])
    assert data_msg["data"]["columnCount"] == 4
    assert data_msg["data"]["rowCount"] == 2
    names = [_json.loads(cell)["value"] for cell in (row[0] for row in grid)]
    assert set(names) == {"a", "A"}
    row_a = next(r for r in grid if _json.loads(r[0])["value"] == "a")
    assert _json.loads(row_a[1])["value"] == "5"
    row_A = next(r for r in grid if _json.loads(r[0])["value"] == "A")
    assert _json.loads(row_A[1])["isMetaData"] is True
    assert "4×4" in _json.loads(row_A[1])["value"]

    # Tras un eval el servidor re-empuja los datos actualizados.
    client.post(
        "/cometd",
        json={"channel": "/matlab/mvm/user-mvm/eval/request", "clientId": cid,
              "id": "7",
              "data": {"command": "b = 42", "requestID": "EV_WS",
                       "isUserEval": True}},
    )
    connect = client.post(
        "/cometd",
        json={"channel": "/meta/connect", "clientId": cid, "id": "8"},
    ).json()
    data_msgs = [m for m in connect
                 if m.get("channel") == "/matlab/WorkspaceBrowser_who"
                 and (m.get("data") or {}).get("eventType") == 2]
    assert data_msgs, "no llegó partialData tras eval"
    grid = _json.loads(data_msgs[-1]["data"]["partialData"])
    names = {_json.loads(cell)["value"] for cell in (row[0] for row in grid)}
    assert "b" in names


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

