"""Contrato del motor E1 de message-containers (WO-06): respuestas del shell real.

Reglas verificadas contra evidencia local (rea/reconstructed/modules/mw-remote/
impl/ResponseManager.js + capturas reales en docs/acceptance/ui/e1-request-map.md):

1. Cada entry de respuesta REUSA el uuid del entry de la petición (correlación:
   el cliente arma "<Tipo>Response:<uuid-clasificador>" y compara C.uuid === e.uuid).
2. El tipo de respuesta es "<Tipo>Response" y todo entry sano lleva
   "messageFaults": [] (el shell olfatea messageFaults[0].faultCode).
3. ServiceRegistry (petición sin uuid) responde sin uuid: va al handler plano
   "ServiceRegistryResponse".
4. Cuerpos no-container en los paths de messageservice conservan el camino
   Bayeux del probe (compatibilidad con la red de seguridad).
5. El sobre de respuesta es {"uuid": <nuevo>, "messages": {...}} (JsonTransaction).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app import app


def _post_container(client: TestClient, body: dict) -> dict:
    response = client.post("/messageservice/json", json=body)
    assert response.status_code == 200
    return response.json()


def test_current_user_echoes_uuid_and_carries_user_info() -> None:
    with TestClient(app) as client:
        client.delete("/api/e1/request-log")
        body = _post_container(
            client,
            {
                "uuid": "520BB31A",
                "messages": {
                    "CurrentUser": [{"apiVersion": "1.2", "uuid": "57743DBA"}],
                    "ClientType": [
                        {
                            "properties": {"TYPE": "motw", "VERSION": "24.0"},
                            "uuid": "96509EB3",
                        }
                    ],
                },
            },
        )
        log = client.get("/api/e1/request-log").json()

    assert body["uuid"]  # transacción nueva para la respuesta
    current = body["messages"]["CurrentUserResponse"][0]
    assert current["uuid"] == "57743DBA"
    assert current["messageFaults"] == []
    # _isAuthorized exige truthy userInfo.userToken (en JS, {} es truthy).
    assert isinstance(current["userInfo"], dict)
    assert "userToken" in current["userInfo"]

    client_type = body["messages"]["ClientTypeResponse"][0]
    assert client_type["uuid"] == "96509EB3"
    assert client_type["messageFaults"] == []

    assert any(entry["kind"] == "container" for entry in log["requests"])
    channels = client.get("/api/e1/channels").json()
    assert "container←CurrentUser" in channels["channels"]


def test_acquire_matlab_is_authorized_and_sets_session_timeouts() -> None:
    with TestClient(app) as client:
        body = _post_container(
            client,
            {
                "uuid": "AA11BB22",
                "messages": {
                    "AcquireMatlab": [
                        {"uuid": "C0FFEE01", "apiVersion": "1.9", "clientType": "matlab"}
                    ]
                },
            },
        )
    reply = body["messages"]["AcquireMatlabResponse"][0]
    assert reply["uuid"] == "C0FFEE01"
    assert reply["messageFaults"] == []
    # _handleAcquireMatlabResponse: _isAuthorized(entry) → setUserInfo(entry).
    assert "userToken" in reply["userInfo"]
    # _setSessionTimeouts lee sessionInfo.sessionTimeoutSeconds.
    assert reply["sessionInfo"]["sessionTimeoutSeconds"] == 3600
    # computeInfo configura el WORKER_ENDPOINT del shell: routingHost = origen
    # del shell (SecurityUtils.isAllowed hace new URL() y compara same-origin).
    assert reply["computeInfo"]["routingHost"] == "http://testserver"
    assert reply["computeInfo"]["computeToken"]["computeSessionId"]


def test_get_current_compute_resource_faults_to_acquire_matlab() -> None:
    with TestClient(app) as client:
        body = _post_container(
            client,
            {
                "uuid": "E1E1E1E1",
                "messages": {"GetCurrentComputeResource": [{"uuid": "CR01"}]},
            },
        )
    # Fault de transacción (no entry): la máquina de estados transiciona
    # "fault GetCurrentComputeResource" → acquireMatlab (envía AcquireMatlab).
    assert body["messages"] == {}
    assert body["fault"]["faultCode"] == "ComputeService.NoWorkersAvailable"
    assert body["uuid"]


def test_get_matlab_status_idle() -> None:
    with TestClient(app) as client:
        body = _post_container(
            client,
            {"uuid": "575A5A57", "messages": {"GetMatlabStatus": [{"uuid": ""}]}},
        )
    reply = body["messages"]["GetMatlabStatusResponse"][0]
    assert reply["GetMatlabStatus"]["status"] == "IDLE"
    assert reply["messageFaults"] == []
    # uuid vacío del request no se propaga (la correlación del cliente lo omite).
    assert "uuid" not in reply


def test_service_registry_plain_handler_without_uuid() -> None:
    with TestClient(app) as client:
        body = _post_container(client, {"uuid": "55AA55AA", "messages": {"ServiceRegistry": [{}]}})
    reply = body["messages"]["ServiceRegistryResponse"][0]
    assert "uuid" not in reply
    assert reply["messageFaults"] == []


def test_unknown_message_type_gets_safe_ack() -> None:
    with TestClient(app) as client:
        body = _post_container(
            client, {"uuid": "12345678", "messages": {"Whatever": [{"uuid": "Q1", "x": 1}]}}
        )
    reply = body["messages"]["WhateverResponse"][0]
    assert reply["uuid"] == "Q1"
    assert reply["messageFaults"] == []


def test_non_container_body_keeps_bayeux_probe_fallback() -> None:
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


def test_cometd_stub_delegates_containers_to_e1_engine() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/matlab/messageservice/async",
            json={"uuid": "DEADBEEF", "messages": {"CurrentUser": [{"uuid": "V1"}]}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["messages"]["CurrentUserResponse"][0]["uuid"] == "V1"


def test_get_without_body_returns_empty_bayeux_list() -> None:
    with TestClient(app) as client:
        response = client.get("/messageservice/json")
    assert response.status_code == 200
    assert response.json() == []


def test_desktop_bayeux_async_routes_to_mvm_attach_flow() -> None:
    # El escritorio real (servido en /mw/) usa /messageservice/async como su
    # endpoint Bayeux: handshake → subscribe → attach de la MVM → connect
    # (el attach responde en el siguiente poll, vía cola de notificaciones).
    with TestClient(app) as client:
        handshake = client.post(
            "/messageservice/async",
            json=[{"channel": "/meta/handshake", "version": "1.0"}],
        ).json()[0]
        assert handshake["successful"] is True
        cid = handshake["clientId"]

        client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/meta/subscribe",
                    "clientId": cid,
                    "subscription": "/matlab/mvm/attach/response",
                }
            ],
        )
        attach = client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/matlab/mvm/attach/request",
                    "clientId": cid,
                    "data": {
                        "mvmID": "user-mvm",
                        "supportedApiVersions": ["v7_0"],
                        "requestID": "A1",
                    },
                }
            ],
        ).json()[0]
        assert attach["successful"] is True

        connect = client.post(
            "/messageservice/async", json=[{"channel": "/meta/connect", "clientId": cid}]
        ).json()
    events = [m for m in connect if m.get("channel") == "/matlab/mvm/attach/response"]
    assert events and events[0]["data"]["requestID"] == "A1"


def test_desktop_bayeux_handshake_advertises_slow_reconnect() -> None:
    # interval>0 evita el bombardeo de long-polls del shell real.
    with TestClient(app) as client:
        handshake = client.post(
            "/matlab/messageservice/async",
            json={"channel": "/meta/handshake", "version": "1.0"},
        ).json()[0]
    assert handshake["advice"]["interval"] == 3000


def test_unknown_bayeux_channel_publish_is_accepted_silently() -> None:
    with TestClient(app) as client:
        handshake = client.post(
            "/messageservice/async",
            json=[{"channel": "/meta/handshake", "version": "1.0"}],
        ).json()[0]
        reply = client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/matlab/services/ErrorLoggingService/JSErrors",
                    "clientId": handshake["clientId"],
                    "data": {"errorMessage": "x"},
                }
            ],
        ).json()[0]
    assert reply["successful"] is True
    assert "error" not in reply


def _bayeux_handshake(client: TestClient) -> str:
    reply = client.post(
        "/messageservice/async", json=[{"channel": "/meta/handshake", "version": "1.0"}]
    ).json()[0]
    assert reply["successful"] is True
    return reply["clientId"]


def _bayeux_subscribe(client: TestClient, client_id: str, *channels: str) -> None:
    for subscription in channels:
        client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/meta/subscribe",
                    "clientId": client_id,
                    "subscription": subscription,
                }
            ],
        )


def _bayeux_connect(client: TestClient, client_id: str) -> list[dict]:
    return client.post(
        "/messageservice/async", json=[{"channel": "/meta/connect", "clientId": client_id}]
    ).json()


def test_prompt_event_subscription_fires_idle_event() -> None:
    """subscribeEvent/request → response + PromptEvent idle en el siguiente poll.

    Cadena copiada de la captura real del connector (real-boot-jsd): sin este
    evento el escritorio se queda en "Initializing..." para siempre, porque el
    ExecutionStateServiceSingleton solo pasa a "ready" con un PromptEvent
    idle (requester BASE_PROMPT).
    """
    with TestClient(app) as client:
        cid = _bayeux_handshake(client)
        _bayeux_subscribe(
            client,
            cid,
            "/matlab/mvm/user-mvm/subscribeEvent/response",
            "/matlab/mvm/user-mvm/event/fireEvent",
        )
        ack = client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/matlab/mvm/user-mvm/subscribeEvent/request",
                    "clientId": cid,
                    "data": {"eventName": "mlutil::prompt::PromptEvent", "requestID": "P1"},
                }
            ],
        ).json()[0]
        assert ack["successful"] is True

        events = _bayeux_connect(client, cid)
    channels = [m.get("channel") for m in events]
    assert "/matlab/mvm/user-mvm/subscribeEvent/response" in channels
    assert "/matlab/mvm/user-mvm/event/fireEvent" in channels
    subscribe_reply = next(
        m for m in events if m["channel"].endswith("/subscribeEvent/response")
    )
    assert subscribe_reply["data"]["requestID"] == "P1"
    fire = next(m for m in events if m["channel"].endswith("/event/fireEvent"))
    assert fire["data"]["requestID"] == "P1"
    assert fire["data"]["eventData"]["isIdle"] is True
    assert fire["data"]["eventData"]["requester"] == "BASE_PROMPT"
    assert fire["data"]["eventData"]["groupName"] == "mlutil::prompt::PromptEvent"


def test_grouped_prompt_subscription_gets_user_group_event() -> None:
    # El shell también se suscribe con la forma manglada "Evento||Grupo";
    # la entrega lleva ese grupo en groupName y en el último filterTag.
    with TestClient(app) as client:
        cid = _bayeux_handshake(client)
        _bayeux_subscribe(
            client,
            cid,
            "/matlab/mvm/user-mvm/subscribeEvent/response",
            "/matlab/mvm/user-mvm/event/fireEvent",
        )
        client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/matlab/mvm/user-mvm/subscribeEvent/request",
                    "clientId": cid,
                    "data": {
                        "eventName": "mlutil::prompt::PromptEvent||UserGroup",
                        "requestID": "P2",
                    },
                }
            ],
        )
        events = _bayeux_connect(client, cid)
    fire = next(m for m in events if m["channel"].endswith("/event/fireEvent"))
    assert fire["data"]["requestID"] == "P2"
    assert fire["data"]["eventData"]["groupName"] == "UserGroup"
    assert (
        "mlutil::prompt::PromptEvent||UserGroup"
        in fire["data"]["eventData"]["filterTags"]
    )


def test_hasinitialized_notification_pushes_confirmation() -> None:
    # event-notification-request (messageChannel hasinitialized) → push con
    # dataMap.isInitialized=true y el requesterId del peticionario.
    with TestClient(app) as client:
        cid = _bayeux_handshake(client)
        _bayeux_subscribe(client, cid, "/matlab/executionstateservice/hasinitialized")
        ack = client.post(
            "/messageservice/async",
            json=[
                {
                    "channel": "/matlab/editor/event-notification-request",
                    "clientId": cid,
                    "data": {
                        "messageChannel": "/executionstateservice/hasinitialized",
                        "requesterId": "ExecutionStateServiceInitializerTEST",
                    },
                }
            ],
        ).json()[0]
        assert ack["successful"] is True
        events = _bayeux_connect(client, cid)
    init = next(
        m for m in events if m.get("channel") == "/matlab/executionstateservice/hasinitialized"
    )
    assert init["data"]["dataMap"] == {"isInitialized": True}
    assert init["data"]["requesterId"] == "ExecutionStateServiceInitializerTEST"
