# WO-07 | WS-3 | E2: eval E2E en el desktop real + modo oráculo (proxy connector)

- **Asignada a:** Devin
- **Precede a:** WO-06 (frontend real servido + bootstrap WORKER_READY), WO-05 (bus mw-mvm)
- **Evidencia:** `docs/acceptance/ui/e1-request-map.md` (iteración 3), `backend/e1_bus_services.py`, `backend/e1_connector.py`, `tests/test_bus.py::test_real_shell_wire_sequence_feval_sinks_and_services`, `tests/test_e1_oracle.py`

## Objetivo

Que el Command Window del frontend REAL de MATLAB (servido en runtime desde
`MATLAB_ROOT` bajo `/mw/`) evalúe contra la MVM propia (`backend/mvm_engine.py`),
y mantener un "modo oráculo" opt-in que proxeé el bus al connector real de MATLAB
para capturar respuestas auténticas.

## Implementado

### Servicios del bus (`backend/e1_bus_services.py`)

Despachados desde `_bayeux_handle` en `app.py` tras el strip del prefijo
`/matlab`. Cada servicio request/response correlaciona por `requestID` (mvm) o
`uid`+`requestId` (shortcuts), publicando en el canal `*/response` al que el
shell se suscribe:

| Canal (sin prefijo /matlab) | Respuesta |
|---|---|
| `{prefix}/feval/request` | `feval/response` + `text/output`/`text/error` + `mvmSinks/output` con el mismo `requestID`; `function=eval/evalin` evalúa el arg de cadena, namespaces internos responden no-op |
| `{prefix}/mvmSinks/request` | `mvmSinks/response` (instala los sinks de texto) |
| `{prefix}/subscribeEvent/request` | `subscribeEvent/response` + `{prefix}/event/fireEvent` inicial (`mlutil::prompt::PromptEvent` con `isIdle:true`, `requester:"BASE_PROMPT"`) |
| `{prefix}/disconnectEvent/request` | `disconnectEvent/response` |
| `/editor/event-notification-request` | responde en `data.messageChannel` (`/executionstateservice/hasinitialized`) con `{dataMap:{isInitialized}, requesterId}`, desbloqueando `ExecutionStateService` para mostrar `>>` y `Ready` |
| `/matlab/settingsChannel/Request` | `data.channel` (`/matlab/settingsChannel/Response/<uuid>`); store en memoria + defaults reales de fuentes RTC (`Monospaced`, `10pt`), tema (`Light`) y colores |
| `/shortcuts/model/services/request/*` | `/shortcuts/model/services/ack` + `response/{op}/...` con `responseId` secuencial (`0, 1, 2...`) y `status:true` |
| `/regfwk/apis/getResourceList` | `/regfwk/apis/resourceList/<clientId>` con `{resourcesFilesData:[], uuid}` |
| `/fctrl/addcb` | `/fctrl/response/addcb` con el estado del feature flag |
| `/filesystem/listfolder/*` | `listfolder/started` y `listfolder/response` con datos del disco local |
| `*` (`mf.zero.io.ModelSynchronizer.*`) | respuesta en el canal espejo (`Client`/`out`/`toClient`) con modelo mínimo |

Observabilidad: cada `/meta/subscribe` registra `subscribe→<canal>` en
`/api/e1/channels`, de modo que el mapa muestra qué canales de respuesta espera
el shell en cada arranque.

### Modo oráculo (`backend/e1_connector.py`)

- `MATLAB_CONNECTOR_URL` (vacío = off): middleware que corre antes del routing y
  proxeé los paths de servicio (`/messageservice/*`, `/matlab/*`, `/msh/*`,
  `/rtc/*`, `/mw-*`, `/cometd`…) al connector real (`httpx`, `verify=False` por
  el certificado autofirmado, `timeout=300s` para long-poll, strip de
  `Origin`/`Referer` que el connector rechaza con 403).
- `/ui/*`, `/toolbox/*`, `/sys/*`: disco primero (MATLAB_ROOT); proxy solo si el
  archivo falta — los assets locales siempre ganan.
- `E1_SHELL=nologin|jsd` (default `nologin`): entry del shell en `/mw/`.
  `jsd` carga `index-jsd.html`, el desktop clásico de MATLABWindow.

### Uso del oráculo

```bash
# 1) MATLAB vivo con el connector:
matlab -batch "connector.ensureServiceOn"   # o sesión persistente
# 2) backend en modo oráculo:
MATLAB_ROOT="C:\Program Files\MATLAB\R2026b" \
MATLAB_CONNECTOR_URL="https://127.0.0.1:31515" \
E1_SHELL=jsd \
python -m uvicorn backend.app:app --port 8002
# 3) El wire auténtico queda en /api/e1/request-log y /api/e1/channels.
```

## Verificación completada

1. Boot del shell en navegador contra el emulador (`:8002`, sin MATLAB connector) → `<div data-state="ready">Ready prompt</div>`, `<span class="promptNode active">&gt;&gt; </span>` y status `Ready` visibles en ~12 s.
2. Evaluación interactiva en el Command Window real (`2+2`) → `/matlab/mvm/<id>/eval/request` (`isUserEval: true`) ejecutado por `mvm.execute` con salida publicada por `text/output` y `mvmSinks/output`.
3. Captura comparativa oráculo (`:8004`) vs emulador (`:8002`) documentada en `docs/acceptance/ui/e1-request-map.md` (iteración 3).

## Límites

- Nada de MathWorks al repo; los assets se sirven en runtime o via mirror local
  (`MATLAB_MIRROR` / `ml-mirror/`).
- El oráculo es herramienta de desarrollo/paridad, no el producto: el default
  sigue siendo el emulador sin MATLAB.
