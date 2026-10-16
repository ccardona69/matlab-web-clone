"""
E2 — Servicios del bus Bayeux del escritorio real.

Tras el attach MVM, el shell habla con los servicios del backend publicando en
canales `<servicio>/request` y esperando la respuesta correlacionada en
`<servicio>/response` (mismo requestID / uid+requestId). Este módulo implementa
los servicios observados en el mapa de arranque (docs/acceptance/ui/
e1-request-map.md) que el Command Window y los paneles necesitan:

- {prefix}/feval/request        → ejecuta via MVM propio → feval/response +
                                 text/output|text/error (mismo requestID)
- {prefix}/mvmSinks/request     → mvmSinks/response (instala sinks de texto;
                                 sin esto el shell ignora los eventos text/*)
- {prefix}/subscribeEvent/request    → subscribeEvent/response
- {prefix}/disconnectEvent/request   → disconnectEvent/response
- /matlab/matlab/settingsChannel/Request → settingsChannel/Response con un
                                 store en memoria (Get/Set/AddListener)
- /matlab/shortcuts/model/services/request/* → responses con acuse sano;
                                 corta la tormenta de reintentos (×4000+)
- /matlab/filesystem/listfolder|operations/start → acuse (service start)

`handle_service` recibe `publish` y `execute` por inyección para no importar
app.py (evita el ciclo app → e1_probe → app).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

Publish = Callable[[dict[str, Any]], None]
Execute = Callable[[str], dict[str, Any]]

# Defaults observados en el wire del connector real (fuentes RTC, tema, colores,
# Command Window y sugerencias). Evitan que _convertValueToOld devuelva
# undefined y rompa FontCssUtilities al inicializar el prompt del Command Window.
_DEFAULT_SETTINGS: dict[str, Any] = {
    "matlab.appearance.CurrentTheme": "Light",
    "matlab.appearance.MATLABTheme": "Light",
    "matlab.appearance.figure.GraphicsTheme": "auto",
    "matlab.desktop.TextFontSize": 12,
    "matlab.desktop.RestoreDesktopConfig": True,
    "matlab.desktop.MOFavoriteCommandsEnabled": True,
    "matlab.desktop.panels.HeaderStyle": "always",
    "matlab.desktop.enableForeverRetryForNativeDebuggingWorkflows": [],
    "matlab.fonts.codefont.Name": "Monospaced",
    "matlab.fonts.codefont.Size": {"mwdata": [10], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.fonts.codefont.Style": {"mwdata": [0], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.fonts.custom.editor.FontToUse": "CodeFont",
    "matlab.fonts.custom.editor.Name": "Courier",
    "matlab.fonts.custom.editor.Size": {"mwdata": [9], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.fonts.custom.editor.Style": {"mwdata": [0], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.fonts.editor.code.Color": [[33, 33, 33, 1]],
    "matlab.fonts.editor.code.Name": "Monospaced",
    "matlab.fonts.editor.code.Size": "14px",
    "matlab.fonts.editor.code.Style": {"mwdata": ["plain"], "mwsize": [1, 1], "mwtype": "cell"},
    "matlab.fonts.editor.heading1.Color": [[33, 33, 33, 1]],
    "matlab.fonts.editor.heading1.Name": "SansSerif",
    "matlab.fonts.editor.heading1.Size": "20px",
    "matlab.fonts.editor.heading1.Style": {"mwdata": ["bold"], "mwsize": [1, 1], "mwtype": "cell"},
    "matlab.fonts.editor.heading2.Color": [[33, 33, 33, 1]],
    "matlab.fonts.editor.heading2.Name": "SansSerif",
    "matlab.fonts.editor.heading2.Size": "17px",
    "matlab.fonts.editor.heading2.Style": {"mwdata": ["bold"], "mwsize": [1, 1], "mwtype": "cell"},
    "matlab.fonts.editor.heading3.Color": [[33, 33, 33, 1]],
    "matlab.fonts.editor.heading3.Name": "SansSerif",
    "matlab.fonts.editor.heading3.Size": "15px",
    "matlab.fonts.editor.heading3.Style": {"mwdata": ["bold"], "mwsize": [1, 1], "mwtype": "cell"},
    "matlab.fonts.editor.normal.Color": [[33, 33, 33, 1]],
    "matlab.fonts.editor.normal.Name": "SansSerif",
    "matlab.fonts.editor.normal.Size": "14px",
    "matlab.fonts.editor.normal.Style": {"mwdata": ["plain"], "mwsize": [1, 1], "mwtype": "cell"},
    "matlab.fonts.editor.title.Color": [[192, 76, 11, 1]],
    "matlab.fonts.editor.title.Name": "SansSerif",
    "matlab.fonts.editor.title.Size": "24px",
    "matlab.fonts.editor.title.Style": {"mwdata": ["plain"], "mwsize": [1, 1], "mwtype": "cell"},
    "matlab.fonts.textfont.Name": "Helvetica",
    "matlab.fonts.textfont.Size": {"mwdata": [9], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.fonts.textfont.Style": {"mwdata": [0], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.fonts.textfont.UseSystemFont": True,
    "matlab.colors.BackgroundColor": {"mwdata": [255, 255, 255], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.ForegroundColor": {"mwdata": [33, 33, 33], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.CommentColor": {"mwdata": [0, 128, 19], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.KeywordColor": {"mwdata": [14, 0, 255], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.StringColor": {"mwdata": [167, 9, 245], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.SyntaxErrorColor": {"mwdata": [183, 49, 44], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.SystemCommandColor": {"mwdata": [139, 102, 6], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.UnterminatedStringColor": {"mwdata": [144, 38, 34], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.ValidationSectionColor": {"mwdata": [160, 82, 45], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.DesktopColors": "",
    "matlab.colors.SyntaxHighlightingColors": "",
    "matlab.colors.UseSystemColor": True,
    "matlab.colors.commandwindow.ErrorColor": {"mwdata": [183, 49, 44], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.commandwindow.HyperlinkColor": {"mwdata": [22, 86, 167], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.colors.commandwindow.WarningColor": {"mwdata": [179, 98, 5], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.commandwindow.EnableRichOutputInteractiveView": False,
    "matlab.commandwindow.GettingStarted": True,
    "matlab.commandwindow.NumberOfLinesInScrollBuffer": {"mwdata": [5000], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.commandwindow.ScrollBeyondLastLine": True,
    "matlab.commandwindow.ShowEnhancedOutput": True,
    "matlab.commandwindow.ShowTypoSuggestions": True,
    "matlab.commandwindow.WarnIfRoot": True,
    "matlab.commandwindow.WrapLines": False,
    "matlab.suggestions.AcceptOnRightArrow": True,
    "matlab.suggestions.HorizontalWidth": -1,
    "matlab.suggestions.MaximumNumberOfSuggestions": 200,
    "matlab.suggestions.ShowFooterDemoPopout": True,
    "matlab.suggestions.ShowInlineText": True,
    "matlab.suggestions.ShowTips": True,
    "matlab.suggestions.VerticalHeight": -1,
    "matlab.suggestions.commandwindow.ShowAutomatically": True,
    "matlab.suggestions.commandwindow.ShowOnTab": True,
    "matlab.suggestions.commandwindow.TabAcceptsOnOneSuggestion": False,
    "matlab.editor.DisplayFullPath": True,
    "matlab.editor.language.matlab.EnableSyntaxHighlighting": True,
    "matlab.editor.displaysettings.CurrentZoomFactor": 1,
    "matlab.editor.displaysettings.ShowCodeFoldingMargin": True,
    "matlab.editor.displaysettings.ShowLineNumbers": True,
    "matlab.editor.displaysettings.ShowRunSectionMargin": True,
    "matlab.editor.displaysettings.ShowRunToHereMargin": True,
    "matlab.editor.displaysettings.WrapCodeLines": False,
    "matlab.editor.displaysettings.linelimit.LineColor": {"mwdata": [191, 191, 191], "mwsize": [1, 3], "mwtype": "int32"},
    "matlab.editor.displaysettings.linelimit.LineColumn": {"mwdata": [75], "mwsize": [1, 1], "mwtype": "int32"},
    "matlab.editor.displaysettings.linelimit.ShowLine": True,
    "matlab.keyboard.shortcuts.ActiveKeyset": "default",
    "matlab.keyboard.shortcuts.ActivePlatform": "windows",
    "matlab.keyboard.shortcuts.CustomFilePaths": {"mwdata": [], "mwsize": [1, 0], "mwtype": "cell"},
    "matlab.desktop.currentfolder.History": {"mwdata": [], "mwsize": [1, 0], "mwtype": "cell"},
    "matlab.desktop.currentfolder.ShowHiddenFiles": False,
    "matlab.desktop.currentfolder.layout.ColumnOrder": {"mwdata": ["name", "size", "modifiedUtc", "type", "cmStatus"], "mwsize": [1, 5], "mwtype": "cell"},
    "matlab.desktop.currentfolder.layout.VisibleColumns": {"mwdata": ["name", "cmStatus"], "mwsize": [1, 2], "mwtype": "cell"},
    "matlab.desktop.workspace.columns.ColumnOrder": {"mwdata": ["Name", "Value", "Size", "Class", "Min", "Max", "Range", "Mean", "Median", "Mode", "Var", "Std", "Bytes"], "mwsize": [1, 13], "mwtype": "cell"},
    "matlab.desktop.workspace.columns.ColumnsShown": {"mwdata": ["Name", "Value", "Size", "Class"], "mwsize": [1, 4], "mwtype": "cell"},
    "matlab.desktop.workspace.columns.ColumnWidths": [[75, 75, 75, 75, 75, 75, 75, 75, 75, 75, 75, 75, 75]],
    "matlab.editor.RecentFileList": {"mwdata": [], "mwsize": [1, 0], "mwtype": "cell"},
    "matlab.editor.RecentClosedFileList": {"mwdata": [], "mwsize": [1, 0], "mwtype": "cell"},
    "matlab.online.cdAnywhereDisabled": False,
    "matlab.ui.internal.figure.webwindow.LifecycleLogs": "none",
}

# Store de settings en memoria: settingsChannel mezcla listeners y valores.
_SETTINGS: dict[str, Any] = {}

# Suscripciones a eventos del motor (subscribeEvent): eventName → requestID.
# El servidor real etiqueta cada fireEvent con el requestID de la suscripción.
_EVENT_SUBS: dict[str, str] = {}

# Eventos que el MATLAB real dispara inmediatamente tras la suscripción
# (estado inicial del motor), observados en el wire del connector.
_FIRE_TAGS = [
    "mlutil::prompt::PromptEvent",
    "mlutil::prompt::IdleEvent",
    "foundation::msg_svc::eventmgr::BaseEvent",
]


def _fire_event(
    publish: Publish,
    prefix: str,
    request_id: str | None,
    event_data: dict[str, Any],
) -> None:
    publish({
        "channel": f"{prefix}/event/fireEvent",
        "data": {"eventData": event_data, "requestID": request_id},
    })


def fire_prompt(
    publish: Publish,
    prefix: str,
    idle: bool,
    only_request_id: str | None = None,
) -> None:
    """Dispara mlutil::prompt::PromptEvent/IdleEvent como el motor real.

    isIdle=true + requester=BASE_PROMPT hace aparecer el `>>` (estado Ready);
    isIdle=false + NO_PROMPT marca Busy durante la ejecución.
    """
    for name in ("mlutil::prompt::PromptEvent", "mlutil::prompt::PromptEvent||UserGroup"):
        rid = _EVENT_SUBS.get(name)
        if rid is None or (only_request_id is not None and rid != only_request_id):
            continue
        _fire_event(
            publish,
            prefix,
            rid,
            {
                "filterTags": _FIRE_TAGS + [f"mlutil::prompt::PromptEvent||{name.split('||')[-1]}"],
                "groupName": "UserGroup",
                "isIdle": idle,
                "requester": "BASE_PROMPT" if idle else "NO_PROMPT",
                "wasCreatedInProcess": False,
            },
        )


def _initial_event_data(name: str) -> dict[str, Any] | None:
    """EventData inicial que el motor real publica tras subscribeEvent."""
    if name in ("mlutil::prompt::PromptEvent", "mlutil::prompt::PromptEvent||UserGroup"):
        return {
            "filterTags": _FIRE_TAGS + [name],
            "groupName": "UserGroup",
            "isIdle": True,
            "requester": "BASE_PROMPT",
            "wasCreatedInProcess": False,
        }
    if name == "mvm_events::ClientCapabilityEvent":
        return {
            "clientCapabilities": [
                "InteractiveCommandLine", "Swing", "ComplexSwing",
                "LocalClient", "WebWindow", "ModalDialogs", "Debugging",
            ],
            "filterTags": ["mvm_events::ClientCapabilityEvent"],
        }
    if name == "mvm_events::CurrentWorkFolderChangedEvent":
        import os

        return {
            "currentWorkFolder": os.getcwd().replace("\\", "/"),
            "filterTags": ["mvm_events::CurrentWorkFolderChangedEvent"],
        }
    if name == "mvm_events::MATLABPathChangedEvent":
        return {"editScript": [], "filterTags": ["mvm_events::MATLABPathChangedEvent"]}
    return None


def _handle_subscribe_event(
    channel: str,
    data: dict[str, Any],
    publish: Publish,
) -> bool:
    prefix = channel[: -len("/subscribeEvent/request")]
    request_id = _request_id(data)
    name = data.get("eventName")
    if isinstance(name, str):
        _EVENT_SUBS[name] = request_id or ""
        from backend.e1_probe import _record_channel as _rc

        _rc(f"subevt→{name}", {"requestID": request_id})
    publish({
        "channel": f"{prefix}/subscribeEvent/response",
        "data": {"requestID": request_id},
    })
    initial = _initial_event_data(name) if isinstance(name, str) else None
    if initial is not None:
        _fire_event(publish, prefix, request_id, initial)
    return True


def replay_initial_events(publish: Publish, prefix: str) -> None:
    """Re-publica los eventos iniciales ya suscritos por el cliente.

    El motor real dispara PromptEvent/ClientCapability/etc. de forma asíncrona;
    en local la respuesta es síncrona y puede adelantarse al /meta/subscribe
    del canal fireEvent. Se re-dispara al suscribirse a `.../event/fireEvent`
    para garantizar la entrega (el shell tolera PromptEvents repetidos).
    """
    for name, request_id in list(_EVENT_SUBS.items()):
        initial = _initial_event_data(name)
        if initial is not None:
            _fire_event(publish, prefix, request_id, initial)


def _request_id(data: dict[str, Any]) -> str | None:
    rid = data.get("requestID")
    return rid if isinstance(rid, str) else None


def publish_eval_output(
    publish: Publish,
    prefix: str,
    request_id: str | None,
    result: dict[str, Any],
) -> None:
    """Emite el output de una ejecución por ambos caminos del protocolo.

    - `{prefix}/text/output|error` con `{requestID, text}`: sinks por petición
      (EvalFevalCancel enruta al callback del runOptions por requestID).
    - `{prefix}/mvmSinks/output` con `{stream, text}`: sink GLOBAL instalado con
      mvmSinks/request (stream 0=stdout, 1=stderr; MVMSink._handleOutput solo
      lee stream+text). Es el camino por el que el Command Window pinta el
      output persistente.
    """
    for segment in result.get("segments") or []:
        kind = segment.get("kind")
        if kind in ("out", "warn", "err") and segment.get("text"):
            stream = "error" if kind == "err" else "output"
            publish({
                "channel": f"{prefix}/text/{stream}",
                "data": {"requestID": request_id, "text": segment["text"]},
            })
            publish({
                "channel": f"{prefix}/mvmSinks/output",
                "data": {"stream": 1 if kind == "err" else 0, "text": segment["text"]},
            })


def _feval_code(data: dict[str, Any]) -> str | None:
    """Traduce un feval wire a código ejecutable por la MVM.

    function="eval"/"evalin" evalúan su argumento de cadena (evalin añade el
    workspace como primer arg). Para el resto se construye la llamada
    `function(arg1, arg2, ...)` con los rhsArgs como literales MATLAB.
    """
    function = data.get("function")
    rhs = data.get("rhsArgs")
    if not isinstance(function, str) or not function:
        return None
    if not isinstance(rhs, list):
        rhs = []
    if function == "eval":
        return rhs[0] if rhs and isinstance(rhs[0], str) else None
    if function == "evalin":
        code = rhs[1] if len(rhs) > 1 else (rhs[0] if rhs else None)
        return code if isinstance(code, str) else None
    args = ", ".join(json.dumps(a) if isinstance(a, str) else str(a) for a in rhs)
    return f"{function}({args})"


def _handle_feval(
    channel: str,
    data: dict[str, Any],
    publish: Publish,
    execute: Execute,
) -> bool:
    prefix = channel[: -len("/feval/request")]
    request_id = _request_id(data)
    function = data.get("function")
    # Funciones internas del escritorio (connector.internal.*, simulink.*,
    # matlab.internal.*…) existen en el MATLAB real pero no en la MVM propia:
    # ejecutarlas generaría "Undefined function" y rompería la cadena de init
    # del shell. Se responde éxito vacío, igual que un no-op del backend.
    _INTERNAL_FEVAL_ROOTS = (
        "connector.", "simulink.", "matlab.", "stateflow.", "slonline.",
        "mvm.", "cmlink.", "glee.", "webwindow.",
    )
    if isinstance(function, str) and function.startswith(_INTERNAL_FEVAL_ROOTS):
        publish({
            "channel": f"{prefix}/feval/response",
            "data": {
                "requestID": request_id,
                "result": [{"screenSize": {"width": 1920, "height": 1080}, "diagnosticViewerNames": {}}],
            },
        })
        return True
    code = _feval_code(data)
    if code is None:
        publish({
            "channel": f"{prefix}/feval/response",
            "data": {"requestID": request_id, "error": "feval request sin función evaluable"},
        })
        return True
    fire_prompt(publish, prefix, idle=False)
    result = execute(code)
    publish_eval_output(publish, prefix, request_id, result)
    # feval/response real: result es un array MDA de salidas ([{}] sin outputs).
    publish({
        "channel": f"{prefix}/feval/response",
        "data": {"requestID": request_id, "result": [result]},
    })
    fire_prompt(publish, prefix, idle=True)
    return True


def _split_setting_key(group: Any, name: Any) -> tuple[str, str, str]:
    if isinstance(group, list):
        group_str = ".".join(str(x) for x in group)
    elif isinstance(group, str):
        group_str = group
    else:
        group_str = ""
    name_str = str(name) if isinstance(name, str) else ""
    full = f"{group_str}.{name_str}" if (group_str and name_str) else (group_str or name_str)
    if "." in full:
        parent, _, node = full.rpartition(".")
        return parent, node, full
    return group_str, name_str, full


def _get_setting_value(full_key: str, node_name: str) -> Any:
    if full_key in _SETTINGS:
        return _SETTINGS[full_key]
    if full_key in _DEFAULT_SETTINGS:
        return _DEFAULT_SETTINGS[full_key]
    low = full_key.lower()
    if "font" in low and node_name == "Name":
        return "Monospaced"
    if "font" in low and node_name == "Size":
        return {"mwdata": [10], "mwsize": [1, 1], "mwtype": "int32"}
    if "font" in low and node_name == "Style":
        return {"mwdata": [0], "mwsize": [1, 1], "mwtype": "int32"}
    if "theme" in node_name.lower():
        return "Light"
    if any(k in node_name for k in ("Size", "Width", "Height", "Limit", "Count", "Interval")):
        return 10
    if node_name.startswith(("Show", "Enable", "Use", "Is", "Has", "Auto", "Wrap", "Save", "Warn", "Accept", "Filter", "Match", "Borrow")):
        return False
    return ""


def _handle_settings_request(data: dict[str, Any], publish: Publish) -> bool:
    """settingsChannel: el cliente lleva en `data.channel` el canal de respuesta
    único (`/matlab/settingsChannel/Response/<uuid>`) y en `data.uuid` el
    correlador del deferred (settingsService._handleServerMessages resuelve con
    `data.settingData`; `type:"ERROR_RESPONSE"` rechaza). Sin respuesta en ese
    canal el cliente reintenta la petición indefinidamente.
    """
    msg_type = data.get("type")
    from backend.e1_probe import _record_channel as _rc
    _rc(f"settings←{msg_type}", {"uuid": data.get("uuid"), "channel": bool(data.get("channel")), "name": data.get("SettingName")})
    response_channel = data.get("channel")
    parent_group, node_name, full_key = _split_setting_key(data.get("SettingGroup"), data.get("SettingName"))
    prev_val = _get_setting_value(full_key, node_name) if full_key else ""
    if msg_type == "SetSettingMessage" and full_key:
        _SETTINGS[full_key] = data.get("SettingValue")
        publish({
            "channel": "/matlab/settingsChannel/ValueChanged",
            "data": {"name": full_key, "newValue": _SETTINGS[full_key], "oldValue": prev_val},
        })
    elif msg_type == "ClearSettingMessage" and full_key:
        _SETTINGS.pop(full_key, None)
    if not isinstance(response_channel, str) or not response_channel:
        return True
    reply: dict[str, Any] = {
        "type": f"{msg_type}Response" if isinstance(msg_type, str) else "Response",
        "uuid": data.get("uuid"),
        "makeCompatible": bool(data.get("makeCompatible")),
        "settingData": {
            "SettingNodeName": node_name,
            "SettingParentGroup": parent_group,
            "SettingValue": _get_setting_value(full_key, node_name),
        },
    }
    if msg_type == "SetSettingMessage":
        reply["settingData"]["PreviousValue"] = prev_val
    elif msg_type == "ClearSettingMessage":
        reply["settingData"] = {"SettingNodeName": node_name, "SettingParentGroup": parent_group}
    elif msg_type == "GetMessage":
        reply["settingData"] = {
            "SettingObject": {
                "ChildrenGroups": [],
                "ChildrenSettings": [],
                "SettingNodeName": node_name,
                "SettingParentGroup": parent_group,
            }
        }
    elif msg_type == "GetSettingsMessage":
        req_settings = data.get("Settings") if isinstance(data.get("Settings"), list) else []
        groups_out: list[str] = []
        names_out: list[str] = []
        vals_out: list[Any] = []
        for s_path in req_settings:
            pg, nn, fk = _split_setting_key(None, s_path)
            groups_out.append(pg)
            names_out.append(nn)
            vals_out.append(_get_setting_value(fk, nn))
        reply.update({"groups": groups_out, "settings": names_out, "values": vals_out})
    elif msg_type == "GetAllSettingsMessage":
        merged = {**_DEFAULT_SETTINGS, **_SETTINGS}
        prefix = f"{full_key}." if full_key else ""
        groups_all: list[list[str]] = []
        names_all: list[str] = []
        vals_all: list[Any] = []
        for k, v in merged.items():
            if prefix and k.startswith(prefix):
                pg, nn, _ = _split_setting_key(None, k)
                groups_all.append(pg.split(".") if pg else [])
                names_all.append(nn)
                vals_all.append(v)
        reply.update({"groups": groups_all, "settings": names_all, "values": vals_all})
    # data.channel es el canal LÓGICO de respuesta del cliente
    # (/matlab/settingsChannel/Response/<uuid>); publish() antepone /matlab y
    # queda el wire /matlab/matlab/settingsChannel/Response/<uuid> que el
    # cliente realmente suscribió.
    publish({"channel": response_channel, "data": reply})
    return True


# Contador global de respuestas del servicio de shortcuts: el cliente solo
# procesa respuestas con responseId consecutivo empezando en 0
# (_lastHandledResponseId === -1 → exige responseId - last === 1); si se
# desordena, la respuesta queda en _pendingResponses y la promesa no resuelve.
_shortcuts_response_seq = 0


def _shortcuts_response_channels(channel: str) -> list[str]:
    """request/{op}/... → response/{op}/... y response/{op} (ambas vistas
    suscritas por el cliente en distintas versiones del shell)."""
    marker = "/request/"
    idx = channel.find(marker)
    if idx < 0:
        return []
    tail = channel[idx + len(marker):]
    base = channel[:idx]
    first = tail.split("/", 1)[0]
    channels = [f"{base}/response/{tail}"]
    if f"{base}/response/{first}" not in channels:
        channels.append(f"{base}/response/{first}")
    return channels


def _handle_shortcuts(channel: str, data: dict[str, Any], publish: Publish) -> bool:
    """Servicio de shortcuts (wire observado + bundle.361.js):

    - Cada request {uid, clientId, requestId, payload} necesita un ACK en
      `/shortcuts/model/services/ack` con {requestId}: sin él el cliente
      reintenta la petición a los ~10s (la tormenta de ×4000 del mapa).
    - La respuesta va a `response/{op}/...` correlacionada por uid y con un
      `responseId` estrictamente secuencial empezando en 0.
    """
    global _shortcuts_response_seq
    request_id_num = data.get("requestId")
    publish({
        "channel": "/shortcuts/model/services/ack",
        "data": {"requestId": request_id_num, "uid": data.get("uid"), "clientId": data.get("clientId")},
    })
    reply = {
        "uid": data.get("uid"),
        "clientId": data.get("clientId"),
        "requestId": request_id_num,
        "responseId": _shortcuts_response_seq,
        "status": True,
        "payload": {"shortcuts": [], "actions": [], "aliases": {}},
    }
    _shortcuts_response_seq += 1
    for response_channel in _shortcuts_response_channels(channel):
        publish({"channel": response_channel, "data": reply})
    return True


def _handle_request_response(
    channel: str,
    data: dict[str, Any],
    publish: Publish,
) -> bool:
    """Patrón genérico {prefix}/{servicio}/request → {prefix}/{servicio}/response
    con el requestID correlacionado (mvmSinks, subscribeEvent, disconnectEvent...).
    """
    response_channel = channel[: -len("/request")] + "/response"
    publish({
        "channel": response_channel,
        "data": {"requestID": _request_id(data)},
    })
    return True


def _fs_iri(path: str) -> str:
    return "file:///" + path.replace("\\", "/")


def _fs_entry(path: str) -> dict[str, Any]:
    """Entrada de archivo con el shape del ListFolderService real."""
    import os

    p = os.path.abspath(path)
    name = os.path.basename(p) or p
    parent = os.path.dirname(p)
    is_dir = os.path.isdir(p)
    has_children = False
    if is_dir:
        try:
            has_children = bool(os.listdir(p))
        except OSError:
            pass
    return {
        "hasChildren": has_children,
        "hasNonHiddenChildren": has_children,
        "iri": _fs_iri(p),
        "isDirectory": is_dir,
        "isHidden": os.path.basename(p).startswith("."),
        "location": parent + "\\" if parent else "\\",
        "name": name,
        "parent": parent,
        "path": p,
        "resolvedTargetPath": "",
        "resolvedTargetType": "",
        "separator": "\\",
        "type": "Folder" if is_dir else "File",
    }


def _fs_roots() -> list[dict[str, Any]]:
    import os
    import string

    roots = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if not os.path.exists(drive):
            continue
        entry = _fs_entry(drive)
        entry.update({
            "iri": f"file:///{letter}:",
            "location": "\\",
            "name": f"{letter}:",
            "parent": "\\",
            "path": drive,
        })
        roots.append(entry)
    return roots


def _handle_filesystem(
    channel: str,
    data: dict[str, Any],
    publish: Publish,
) -> bool:
    """ListFolderService/FileOperations del escritorio (wire capturado del
    connector real): cada petición responde en .../response con el uuid
    correlacionado y los datos del disco local, igual que el MATLAB real.
    """
    import os

    if channel.endswith("/start"):
        started = channel[: -len("/start")] + "/started"
        started_payload: dict[str, Any] = {}
        if channel == "/filesystem/listfolder/start":
            started_payload["separator"] = 92
        publish({"channel": started, "data": started_payload})
        return True
    uid = data.get("uuid")
    response = "filesystem/listfolder/response"
    if channel == "/filesystem/listfolder/get-path-separator":
        payload: dict[str, Any] = {"separator": 92}
    elif channel == "/filesystem/listfolder/getprocesscwd":
        cwd = os.getcwd()
        payload = {"iri": _fs_iri(cwd), "path": cwd}
    elif channel == "/filesystem/listfolder/getfilesystemroots":
        payload = {"fileSystemRoots": _fs_roots()}
    elif channel == "/filesystem/listfolder/get-iri":
        payload = {"iri": _fs_iri(str(data.get("path") or ""))}
    elif channel == "/filesystem/listfolder/watch":
        payload = {}
    elif channel == "/filesystem/listfolder/getchildren":
        path = str(data.get("path") or os.getcwd())
        children: list[dict[str, Any]] = []
        try:
            for child in sorted(os.listdir(path)):
                children.append(_fs_entry(os.path.join(path, child)))
        except OSError:
            pass
        payload = {
            "folder": _fs_entry(path),
            "folderContents": children,
            "location": os.path.abspath(path) + "\\" if os.path.isdir(path) else "",
        }
    elif channel == "/filesystem/operations/exists":
        response = "filesystem/operations/response"
        payload = {"exists": os.path.exists(str(data.get("path") or ""))}
    else:
        payload = {}
        if channel.startswith("/filesystem/operations/"):
            response = "filesystem/operations/response"
    publish({"channel": f"/{response}", "data": {**payload, "uuid": uid}})
    return True


# Valores fctrl observados en el wire real (feature flags del escritorio):
# la mayoría Off, un subconjunto On/Beta/Preview. addcb → response/addcb.
_FCTRL_VALUES = {
    "homeSessionManagerImpl": 1,
    "FigureContainerDefault": 1,
    "figurePositionFixG3655174": 1,
    "RebuildViewBugFixG3610012": 1,
    "RichCmdWin": 1,
    "webui": 1,
}
_FCTRL_STATES = {"CombinedEditor": "Beta", "EngagementNotification": "Preview"}


def _handle_fctrl(data: dict[str, Any], publish: Publish) -> bool:
    name = data.get("name")
    value = _FCTRL_VALUES.get(name, 0)
    publish({
        "channel": "/fctrl/response/addcb",
        "data": {
            "FCtrlState": _FCTRL_STATES.get(name, "On" if value else "Off"),
            "defaultValue": value,
            "id": data.get("id"),
            "name": name,
            "scope": "Scope::PROCESS",
            "value": value,
        },
    })
    return True


# mf.zero model sync: el servidor responde en el canal "espejo" del request
# (…/server→…/client, …/in→…/out, toServer→toClient, *Server→*Client) con
# {client: uuid, content: {definitions: [...], …}}. El clon devuelve el
# modelo mínimo (definiciones vacías): resuelve el fetch y deja los paneles
# vacíos sin depender de la instalación.
_MFZ_SUFFIX_MAP = {
    "MF0ViewModelManagerServer": "MF0ViewModelManagerClient",
    "toServer": "toClient",
    "in": "out",
    "server": "client",
    "update": "update",
}


def _mfz_response_channel(channel: str) -> str:
    head, _, last = channel.rpartition("/")
    return f"{head}/{_MFZ_SUFFIX_MAP.get(last, last)}"


def _handle_mfz_fetch(channel: str, data: dict[str, Any], publish: Publish) -> bool:
    publish({
        "channel": _mfz_response_channel(channel),
        "data": {
            "client": str(uuid.uuid4()),
            "content": {
                "definitions": [],
                "added": [],
                "addedElementURIs": [],
                "destroyed": [],
                "modified": [],
            },
        },
    })
    return True


def _handle_cmlink(channel: str, data: dict[str, Any], publish: Publish) -> bool:
    """cmlink (Current Folder): getRootView → canales de vista del modelo."""
    if isinstance(data.get("type"), str) and "ModelSynchronizer" in data["type"]:
        return _handle_mfz_fetch(channel, data, publish)
    if channel == "/cmlink/getRootView":
        publish({
            "channel": "/cmlink/getRootView/r",
            "data": {
                "ClientChannel": "/cmlink/viewclient",
                "CommandChannel": "/cmlink/viewcommand",
                "ServerChannel": "/cmlink/viewserver",
                "UUID": str(uuid.uuid4()),
            },
        })
        return True
    return True  # resto de cmlink/*: acuse silencioso (vistas sin modelo)


# Cache de notificaciones /editor/event-notification (ej. ExecutionStateServiceInitializer
# consulta /executionstateservice/hasinitialized antes de permitir que PromptEvent
# cambie el Command Window de "Initializing prompt" a "Ready prompt" `>>`).
_EVENT_NOTIFICATIONS: dict[str, dict[str, Any]] = {}


def _handle_event_notification(channel: str, data: dict[str, Any], publish: Publish) -> bool:
    msg_channel = data.get("messageChannel")
    if channel == "/editor/event-notification":
        if isinstance(msg_channel, str) and isinstance(data.get("messageData"), dict):
            _EVENT_NOTIFICATIONS[msg_channel] = dict(data["messageData"])
        return True
    if channel == "/editor/event-notification-request" and isinstance(msg_channel, str) and msg_channel:
        cached = _EVENT_NOTIFICATIONS.get(msg_channel, {"dataMap": {"isInitialized": False}})
        publish({
            "channel": msg_channel,
            "data": {**cached, "requesterId": data.get("requesterId")},
        })
        return True
    return True


def _handle_usagesetup(data: dict[str, Any], publish: Publish) -> bool:
    """UsageSetup type=start → responde en data.responseChannel (usage metrics)."""
    response_channel = data.get("responseChannel")
    if isinstance(response_channel, str) and response_channel:
        publish({"channel": response_channel, "data": {"type": "started"}})
    return True


# Canal de respuesta por operación regfwk (visto en las suscripciones del
# shell real: suscribe todos los canales <op>/<clientId> por adelantado).
_REGFWK_RESPONSE_NAMES = {
    "getResourceList": "resourceList",
    "getFolderState": "folderState",
    "getAllRequestedResourceNames": "allRequestedResourceNames",
    "getExtensionsMetadataFromFile": "getExtensionsMetadataFromFileResponse",
    "setExtensionsMetadataToFile": "setExtensionsMetadataToFileResponse",
}


def handle_service(
    channel: str,
    data: dict[str, Any],
    publish: Publish,
    execute: Execute,
) -> bool:
    """Despacha un mensaje Bayeux de servicio; True si quedó respondido.

    `channel` llega sin el prefijo /matlab (app.py lo despoja antes). Devuelve
    False para que el llamante aplique el acuse silencioso por defecto.
    """
    if not isinstance(data, dict):
        data = {}
    if channel == "/services/ErrorLoggingService/JSErrors":
        from backend.e1_probe import _record_channel as _rc

        msg = str(data.get("errorMessage") or "")[:300]
        tag = msg.splitlines()[1] if len(msg.splitlines()) > 1 else msg[:80]
        _rc(f"jserr→{tag[:80]}", {"errorMessage": msg})
        return True
    if channel.endswith("/feval/request"):
        return _handle_feval(channel, data, publish, execute)
    if channel.endswith("/mvmSinks/request"):
        return _handle_request_response(channel, data, publish)
    if channel.endswith("/subscribeEvent/request"):
        return _handle_subscribe_event(channel, data, publish)
    if channel.endswith("/disconnectEvent/request"):
        return _handle_request_response(channel, data, publish)
    if channel == "/matlab/settingsChannel/Request":
        return _handle_settings_request(data, publish)
    if "/shortcuts/model/services/request/" in channel:
        return _handle_shortcuts(channel, data, publish)
    # Resource framework (regfwk): request regfwk/apis/<op> → respuesta en
    # regfwk/apis/<resp>/<clientId> correlacionada por uuid. Sin respuesta el
    # cargador de plugins queda esperando y el desktop no termina de montar.
    # El real devuelve el registro de extensiones.json de la instalación; el
    # clon responde el caso vacío {"resourcesFilesData": [], "uuid": ...},
    # válido en el wire y suficiente para que el boot continúe.
    if channel.startswith("/regfwk/apis/") and channel != "/regfwk/apis/start":
        op = channel[len("/regfwk/apis/"):]
        resp_name = _REGFWK_RESPONSE_NAMES.get(op, op)
        client_id = data.get("clientId") or ""
        payload: dict[str, Any] = {"uuid": data.get("uuid")}
        if op == "getResourceList":
            payload["resourcesFilesData"] = []
        publish({
            "channel": f"/regfwk/apis/{resp_name}/{client_id}",
            "data": payload,
        })
        return True
    # Filesystem (ListFolderService) y panel Current Folder.
    if channel.startswith("/filesystem/"):
        return _handle_filesystem(channel, data, publish)
    if channel == "/fctrl/addcb":
        return _handle_fctrl(data, publish)
    if channel.startswith("/cmlink/"):
        return _handle_cmlink(channel, data, publish)
    # mf.zero model sync (datamodels de filesystem, history, workspace…)
    if isinstance(data.get("type"), str) and "ModelSynchronizer" in data["type"]:
        return _handle_mfz_fetch(channel, data, publish)
    if channel in ("/editor/event-notification-request", "/editor/event-notification"):
        return _handle_event_notification(channel, data, publish)
    if channel == "/UsageSetup":
        return _handle_usagesetup(data, publish)
    # Clipboard service: requestAvailableDataFlavors → sendAvailableDataFlavors/<uid>
    if channel == "/v2/clipboardservice/requestAvailableDataFlavors":
        publish({
            "channel": f"/v2/clipboardservice/sendAvailableDataFlavors/{data.get('uid') or ''}",
            "data": {"flavors": []},
        })
        return True
    # Servicios con patrón */start → evento */started (wire real: connector
    # publica filesystem/listfolder/started {separator}, operations/started {},
    # regfwk/apis/started {}, packagedataservice/apis/started {}…).
    if channel.endswith("/start"):
        started = channel[: -len("/start")] + "/started"
        payload: dict[str, Any] = {}
        if channel == "/filesystem/listfolder/start":
            payload["separator"] = 92  # '\' en Windows, igual que el real
        publish({"channel": started, "data": payload})
        return True
    return False
