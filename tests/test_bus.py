"""Contract tests for the minimal mw-mvm/CometD adapter."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
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


def test_wo10_filesystem_listfolder_and_operations_protocol(client: TestClient) -> None:
    """WO-10: filesystem/listfolder/* y operations/* responden en */response con uuid correlado."""
    handshake = client.post(
        "/cometd",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]

    for idx, ch in enumerate(["/matlab/filesystem/listfolder/response", "/matlab/filesystem/operations/response"], start=2):
        client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": ch, "id": str(idx)})

    # 1. get-path-separator
    uid_sep = "ListFolderService-TEST:1-/get-path-separator"
    client.post("/cometd", json={"channel": "/matlab/filesystem/listfolder/get-path-separator", "clientId": cid, "id": "10", "data": {"uuid": uid_sep}})
    events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "11"}).json()
    resp = next(e for e in events if e.get("channel") == "/matlab/filesystem/listfolder/response" and e.get("data", {}).get("uuid") == uid_sep)
    assert resp["data"]["separator"] == 92

    # 2. operations/exists
    uid_exists = "FileOperations-TEST:2-/exists"
    client.post("/cometd", json={"channel": "/matlab/filesystem/operations/exists", "clientId": cid, "id": "12", "data": {"path": os.getcwd(), "uuid": uid_exists}})
    events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "13"}).json()
    resp = next(e for e in events if e.get("channel") == "/matlab/filesystem/operations/response" and e.get("data", {}).get("uuid") == uid_exists)
    assert resp["data"]["exists"] is True
    assert resp["data"]["isDirectory"] is True


def test_wo10_fileinfo_shape_and_getchildren_in_tempdir(client: TestClient) -> None:
    """WO-10: fileInfo shape verbatim y getchildren con archivos reales (.m, carpetas)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        m_file = Path(tmpdir) / "test_func.m"
        m_file.write_text("function y = test_func(x)\ny = x * 2;\nend\n", encoding="utf-8")
        sub_dir = Path(tmpdir) / "subpkg"
        sub_dir.mkdir()

        handshake = client.post(
            "/cometd",
            json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
        ).json()[0]
        cid = handshake["clientId"]
        client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": "/matlab/filesystem/listfolder/response", "id": "2"})

        uid = "ListFolderService-TEST:3-/getchildren"
        client.post("/cometd", json={
            "channel": "/matlab/filesystem/listfolder/getchildren",
            "clientId": cid,
            "id": "3",
            "data": {"path": tmpdir, "computeHasChildren": False, "uuid": uid},
        })
        events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "4"}).json()
        resp = next(e for e in events if e.get("channel") == "/matlab/filesystem/listfolder/response" and e.get("data", {}).get("uuid") == uid)
        data = resp["data"]
        assert data["uuid"] == uid
        folder = data["folder"]
        assert folder["isDirectory"] is True
        assert folder["separator"] == "\\"
        assert folder["iri"].startswith("file:///")

        contents = data["folderContents"]
        m_entry = next(c for c in contents if c["name"] == "test_func.m")
        assert m_entry["type"] == "m"
        assert m_entry["isDirectory"] is False
        assert m_entry["separator"] == "\\"
        assert m_entry["filePermissions"]["canWrite"] is True
        assert "file:///" in m_entry["iri"]

        sub_entry = next(c for c in contents if c["name"] == "subpkg")
        assert sub_entry["type"] == "Folder"
        assert sub_entry["isDirectory"] is True


def test_wo10_sandbox_restriction(client: TestClient) -> None:
    """WO-10: Seguridad — pedir fuera del root configurado no debe devolver datos."""
    from backend.e1_bus_services import _SAFE_ROOTS, set_filesystem_safe_roots

    with tempfile.TemporaryDirectory() as safe_root, tempfile.TemporaryDirectory() as secret_root:
        secret_file = Path(secret_root) / "secret.m"
        secret_file.write_text("classified = true;", encoding="utf-8")

        # Restringir safe roots solo al directorio seguro
        set_filesystem_safe_roots([safe_root])
        try:
            # 1. messageservice/json OpenFile de archivo fuera de sandbox
            resp = client.post("/messageservice/json", json={
                "messages": {
                    "OpenFile": [{"path": str(secret_file), "uuid": "TEST_SANDBOX_OPEN"}]
                }
            })
            assert resp.status_code == 200
            body = resp.json()
            open_resp = body["messages"]["OpenFileResponse"][0]
            assert "file" not in open_resp
            assert open_resp["messageFaults"][0]["faultCode"] == "FileService.IOError"

            # 2. filesystem getchildren fuera de sandbox
            handshake = client.post(
                "/cometd",
                json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
            ).json()[0]
            cid = handshake["clientId"]
            client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": "/matlab/filesystem/listfolder/response", "id": "2"})
            uid = "ListFolderService-TEST:SANDBOX-/getchildren"
            client.post("/cometd", json={
                "channel": "/matlab/filesystem/listfolder/getchildren",
                "clientId": cid,
                "id": "3",
                "data": {"path": secret_root, "uuid": uid},
            })
            events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "4"}).json()
            resp = next(e for e in events if e.get("channel") == "/matlab/filesystem/listfolder/response" and e.get("data", {}).get("uuid") == uid)
            assert resp["data"]["folderContents"] == []
        finally:
            set_filesystem_safe_roots(None)


def test_wo10_editor_systeminfo_service(client: TestClient) -> None:
    """WO-10: /editor/systeminfoservice/request responde isWindows: True con uid correlado."""
    handshake = client.post(
        "/cometd",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]
    client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": "/matlab/editor/systeminfoservice/response", "id": "2"})

    # isWindows
    client.post("/cometd", json={
        "channel": "/matlab/editor/systeminfoservice/request",
        "clientId": cid,
        "id": "3",
        "data": {"uid": "SYS_WIN_1", "type": "isWindows", "data": ""},
    })
    events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "4"}).json()
    resp = next(e for e in events if e.get("channel") == "/matlab/editor/systeminfoservice/response" and e.get("data", {}).get("uid") == "SYS_WIN_1")
    assert resp["data"]["data"]["isWindows"] is True

    # isRootUser
    client.post("/cometd", json={
        "channel": "/matlab/editor/systeminfoservice/request",
        "clientId": cid,
        "id": "5",
        "data": {"uid": "SYS_ROOT_2", "type": "isRootUser", "data": ""},
    })
    events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "6"}).json()
    resp = next(e for e in events if e.get("channel") == "/matlab/editor/systeminfoservice/response" and e.get("data", {}).get("uid") == "SYS_ROOT_2")
    assert resp["data"]["data"]["isRootUser"] is False


def test_wo10_editor_open_and_mlx_read_write(client: TestClient) -> None:
    """WO-10: OpenFile via messageservice y lectura/escritura via /mlx/service/readRequest_cpp."""
    import hashlib

    with tempfile.TemporaryDirectory() as tmpdir:
        m_file = Path(tmpdir) / "ejemplo1_regresion.m"
        initial_code = "% Regresion lineal\nx = [1 2 3 4 5]';\ny = [2.1 3.9 6.2 8.1 9.9]';\np = polyfit(x, y, 1);\n"
        m_file.write_text(initial_code, encoding="utf-8")

        # 1. messageservice/json OpenFile
        resp = client.post("/messageservice/json", json={
            "messages": {
                "OpenFile": [{"path": str(m_file), "uuid": "OPEN_REGRESION_1"}]
            }
        })
        assert resp.status_code == 200
        open_data = resp.json()["messages"]["OpenFileResponse"][0]
        assert open_data["uuid"] == "OPEN_REGRESION_1"
        assert open_data["file"]["content"] == initial_code
        assert open_data["file"]["fileInfo"]["name"] == "ejemplo1_regresion.m"
        assert open_data["file"]["fileInfo"]["type"] == "m"

        # 2. Bayeux /mlx/service/readRequest_cpp
        handshake = client.post(
            "/cometd",
            json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
        ).json()[0]
        cid = handshake["clientId"]
        rtc_id = "RTC_MLX_READ_1"
        resp_channel = f"/matlab/mlx/service/readResponse/{rtc_id}"
        client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": resp_channel, "id": "2"})

        client.post("/cometd", json={
            "channel": "/matlab/mlx/service/readRequest_cpp",
            "clientId": cid,
            "id": "3",
            "data": {"rtcId": rtc_id, "filePath": str(m_file)},
        })
        events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "4"}).json()
        read_resp = next(e for e in events if e.get("channel") == resp_channel)
        data = read_resp["data"]
        assert data["status"] is True
        assert data["data"] == initial_code
        expected_md5 = hashlib.md5(initial_code.encode("utf-8")).hexdigest()
        assert data["checksum"] == expected_md5
        assert data["encoding"] == "UTF-8"

        # 3. Bayeux /mlx/service/writeRequest_cpp
        new_code = initial_code + "plot(x, y, 'ro');\n"
        write_rtc = "RTC_MLX_WRITE_2"
        write_resp_channel = f"/matlab/mlx/service/writeResponse/{write_rtc}"
        client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": write_resp_channel, "id": "5"})

        client.post("/cometd", json={
            "channel": "/matlab/mlx/service/writeRequest_cpp",
            "clientId": cid,
            "id": "6",
            "data": {"rtcId": write_rtc, "filePath": str(m_file), "content": new_code},
        })
        events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "7"}).json()
        write_resp = next(e for e in events if e.get("channel") == write_resp_channel)
        assert write_resp["data"]["status"] is True
        assert m_file.read_text(encoding="utf-8") == new_code


def test_wo10_filesystem_mfz_lf_channel_datamodel(client: TestClient) -> None:
    """WO-10: mf.zero ModelSynchronizer sobre /matlab_filesystem_datamodel/lf-channel."""
    handshake = client.post(
        "/cometd",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]
    lf_channel = "/matlab/matlab_filesystem_datamodel/lf-channel"
    client.post("/cometd", json={"channel": "/meta/subscribe", "clientId": cid, "subscription": lf_channel, "id": "2"})

    req_client = "client-uuid-1234"
    corr_id = "corr-uuid-5678"
    model_id = "model-uuid-9999"
    client.post("/cometd", json={
        "channel": lf_channel,
        "clientId": cid,
        "id": "3",
        "data": {
            "type": "mf.zero.io.ModelSynchronizer.FetchModelWithDataDefinition",
            "client": req_client,
            "correlationId": corr_id,
            "content": {
                "modelId": model_id,
                "endpointsImplemented": [],
                "transaction-factory-ordinals": {},
            },
        },
    })
    events = client.post("/cometd", json={"channel": "/meta/connect", "clientId": cid, "id": "4"}).json()
    resp = next(e for e in events if e.get("channel") == lf_channel)
    data = resp["data"]
    assert data["type"] == "mf.zero.io.ModelSynchronizer.ModelWithDataDefinition"
    assert data["client"] == req_client
    assert data["correlationId"] == corr_id
    content = data["content"]
    assert content["modelId"] == model_id
    definitions = content["definitions"]
    assert len(definitions) == 1
    assert definitions[0]["family"] == "filesystem_datamodel_base"
    assert definitions[0]["modelVersion"] == "R2020b"
    assert "entries" in content["model"]
    assert len(content["model"]["entries"]) > 0


# ---------------------------------------------------------------------------
# WO-11: Figuras Handle Graphics embebidas en el JSD
# ---------------------------------------------------------------------------


def test_wo11_plot_figure_created_and_wildcard_subscription(client: TestClient) -> None:
    """WO-11: Al evaluar plot(1:10), se publica figureContainerDefault y gbtweb/divfigure/figureCreated con wildcard."""
    handshake = client.post(
        "/messageservice/async",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]

    subscriptions = [
        "/matlab/mvm/attach/response",
        "/matlab/mvm/user-mvm/eval/response",
        "/matlab/figureContainerDefault",
        "/matlab/gbtweb/divfigure/*",  # Comprobación de suscripción wildcard
    ]
    for idx, channel in enumerate(subscriptions, start=2):
        ack = client.post(
            "/messageservice/async",
            json={"channel": "/meta/subscribe", "clientId": cid, "subscription": channel, "id": str(idx)},
        ).json()[0]
        assert ack["successful"] is True

    # Evaluar plot(1:10)
    client.post(
        "/messageservice/async",
        json={
            "channel": "/matlab/mvm/user-mvm/eval/request",
            "clientId": cid,
            "data": {"command": "plot(1:10)", "requestID": "PLOT_1"},
            "id": "10",
        },
    )

    events = client.post(
        "/messageservice/async",
        json={"channel": "/meta/connect", "clientId": cid, "id": "11"},
    ).json()

    by_channel = {}
    for item in events:
        by_channel.setdefault(item.get("channel"), []).append(item)

    assert "/matlab/figureContainerDefault" in by_channel
    default_fig = by_channel["/matlab/figureContainerDefault"][0]["data"]
    assert default_fig["launchUndockedWindow"] == 1
    assert default_fig["defaultFigurePosition"] == [423, 230, 1074, 647]

    assert "/matlab/gbtweb/divfigure/figureCreated" in by_channel
    fig_created = by_channel["/matlab/gbtweb/divfigure/figureCreated"][0]["data"]
    assert fig_created["ClientToServer"] == "/embeddedfigure/ClientToServer"
    assert fig_created["ServerToClient"] == "/embeddedfigure/ServerToClient"
    assert fig_created["Title"] == "Figure 1"
    assert fig_created["Visible"] is True
    assert fig_created["WindowStyle"] == "docked"
    assert fig_created["channel"].startswith("/uifigure/")
    assert len(fig_created["Uuid"]) > 0


def test_wo11_figure_lifecycle_channels_acknowledged(client: TestClient) -> None:
    """WO-11: Todos los canales del ciclo de vida y eventos de figuras reciben acuse sin error."""
    handshake = client.post(
        "/messageservice/async",
        json={"channel": "/meta/handshake", "version": "1.0", "supportedConnectionTypes": ["long-polling"], "id": "1"},
    ).json()[0]
    cid = handshake["clientId"]

    channels_to_test = [
        ("/matlab/motw/uicontainer", {"type": "started"}),
        ("/matlab/gbtweb/divfigure/clientSubscribed", {}),
        ("/matlab/gbtweb/divfigure/setUndockInWindowFigureContainer", {}),
        ("/matlab/gbtweb/divfigure/figureRefresh", {}),
        ("/matlab/mg2web/eventChannel", {"type": "command", "message": "register", "id": "main", "clientType": "Normal"}),
        ("/matlab/mlapp/figure", {"eventType": "moRefreshed"}),
        ("/matlab/channel/webwindow/focus", {"channelName": "/channel/webwindow"}),
        ("/matlab/x270E6283/uicontainer", {"type": "started"}),
        ("/matlab/x270E6283/uicontainer", {"type": "terminated"}),
    ]

    for idx, (channel, data) in enumerate(channels_to_test, start=2):
        ack = client.post(
            "/messageservice/async",
            json={"channel": channel, "clientId": cid, "data": data, "id": str(idx)},
        ).json()[0]
        assert ack["successful"] is True


def test_wo11_figure_image_and_meta_endpoints(client: TestClient) -> None:
    """WO-11: Endpoints de renderizado PNG y metadatos de figura."""
    client.post("/api/mvm/eval", json={"code": "figure(1); plot(1:5, [1 4 9 16 25], 'r-o'); title('Parabola');"})

    # 1. /api/figures
    figs = client.get("/api/figures").json()
    assert len(figs) >= 1
    f1 = next(f for f in figs if f["number"] == 1)
    assert f1["number"] == 1
    assert "image_data_url" in f1
    assert f1["image_data_url"].startswith("data:image/png;base64,")

    # 2. /api/figure/1
    meta = client.get("/api/figure/1").json()
    assert meta["number"] == 1
    assert meta["width"] == 560
    assert meta["height"] == 420
    assert len(meta["axes"]) == 1

    # 3. /api/figure/1/image (PNG real con bytes mágicos)
    img_resp = client.get("/api/figure/1/image")
    assert img_resp.status_code == 200
    assert img_resp.headers["content-type"] == "image/png"
    assert img_resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    # 4. /mw/undocked-container.html sirve la página del contenedor
    html_resp = client.get("/mw/undocked-container.html?id=fig1&fig=1")
    assert html_resp.status_code == 200
    assert "Figure 1" in html_resp.text
    assert "/api/figure/1/image" in html_resp.text



