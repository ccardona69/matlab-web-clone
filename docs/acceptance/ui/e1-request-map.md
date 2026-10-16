# E1 — Primer mapa de arranque del webgui real (WO-06)

> Capturado el 2026-10-16 con el probe `backend/e1_probe.py` (fusionado en PR #4),
> `MATLAB_ROOT = C:\Program Files\MATLAB\R2026b`, navegador headless Edge (Chromium 155).
> Los cuerpos crudos viven solo en el server local (`/api/e1/request-log`); este
> documento es el mapa saneado que consume el equipo. Nada de bundles/CSS de
> MathWorks se commitea: todo se sirve en runtime desde la instalación.
## Secuencia de arranque observada

| # | Petición | Respuesta | Notas |
|---|---|---|---|
| 1 | `GET /mw/` | 200 | `index-nologin.html` (1.1 KB) |
| 2 | `GET /mw/release/<rev>/index-css.css` | 200 | CSS real del webgui (1.35 MB) |
| 3 | `GET /mw/release/<rev>/bundle.index-nologin.js` | 200 | loader del shell |
| 4 | `GET /mw/release/<rev>/MOTW/dojoConfig-release-global.js` | 200 | config Dojo |
| 5 | `GET /mw/release/<rev>/bundle.361.js` | 200 | bundle principal |
| 6 | `GET /mw/defaults.json?<ts>` | 200 | flags/valores por defecto de la UI |
| 7 | `GET /mw/release/<rev>/derived/3p/ui/dojo/resources/blank.gif` | 200 | asset del tema Dojo |
| 8 | `GET /favicon.ico` | 404 | trivial (no afecta) |
| 9 | `POST /messageservice/json` (en otra corrida: `POST /matlab/messageservice/async`) | 200 | primer mensaje del protocolo (abajo) |

**Resultado:** DOM final de 7.9 KB con el shell MOTW real renderizado (Dojo con tema
`tundra`, overlay «MATLAB is loading» con spinner real, contenedor `#motw` oculto a la
espera de sesión). Consola JS **sin errores**: `uiLifecycle state: PAGE_LOAD`
(emitido por el propio `bundle.361.js`).

## Primer mensaje del protocolo (capturado del shell real)

```json
{
  "uuid": "<msg>",
  "messages": {
    "CurrentUser": [{ "apiVersion": "1.2", "uuid": "<sub>" }],
    "ClientType": [{
      "properties": {
        "LOCALE": "es",
        "OS": "Win32",
        "PLATFORM": "Win32",
        "TYPE": "motw",
        "VERSION": "24.0",
        "SERVICE_ENDPOINT": ""
      },
      "uuid": "<sub>"
    }]
  }
}
```

Observaciones:

- El shell usa el sobre `{uuid, messages: {TipoDeMensaje: [ ... ]}}` y espera respuestas
  correlacionadas por `uuid`.
- `TYPE=motw`, `VERSION=24.0`: se identifica como cliente MATLAB Online — es la base del
  protocolo `mw-messageservice` que W7/WO-05 empezaron a cubrir.
- Punto de parada actual: **falta responder `CurrentUser` / `ClientType`** (y los mensajes
  siguientes) para que `#motw` deje de estar oculto y arranque el desktop. El probe
  responde hoy un eco mínimo y el shell lo tolera sin error.

## Reproducir

```bash
MATLAB_ROOT="C:\Program Files\MATLAB\R2026b" python -m uvicorn backend.app:app --port 8002
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new \
  --virtual-time-budget=25000 --dump-dom "http://127.0.0.1:8002/mw/"
# bitácora: curl http://127.0.0.1:8002/api/e1/request-log
# mapa:     curl http://127.0.0.1:8002/api/e1/channels
```

## Siguientes pasos (WO-06, Devin + Codex)

1. Implementar respuestas reales para `CurrentUser` y `ClientType` en un módulo propio
   (registrado antes del probe; el probe queda último).
2. Re-capturar y encadenar el siguiente mensaje del shell; documentar cada salto de estado.
3. Iterar hasta el render del desktop; el checklist de progreso vive en este directorio.

---

## Iteración 2 — protocolo implementado: el desktop arranca (2026-10-16)

Con `backend/e1_messageservice.py` (motor de message-containers) + ampliaciones del probe,
el shell real llega a `uiLifecycle: WORKER_READY` y monta el escritorio completo
(Command Window, Workspace, toolstrip con iconos reales; DOM ~156 KB).

### Contenedores respondidos (orden de arranque)

| # | Ruta | Mensajes | Respuesta E1 |
|---|---|---|---|
| 1 | `POST /messageservice/json` | `CurrentUser` + `ClientType` | `userInfo` local + acuse |
| 2 | `POST /messageservice/json/secure` | `GetCurrentComputeResource` | **fault de transacción** `ComputeService.NoWorkersAvailable` → la máquina de estados pasa a `acquireMatlab` |
| 3 | `POST /messageservice/json` | `AcquireMatlab` + `ClientType` | `userInfo` + `sessionInfo` + **`computeInfo`** (`routingHost` = origen del shell) |
| 4 | `POST /messageservice/json/secure` | `CurrentUser` (worker) | sesión del worker ✓ |
| 5 | `POST /messageservice/json/secure` | `ClientModulesStarted` | acuse sano |
| 6 | `POST /messageservice/json/secure` | `Ping` | heartbeat del worker ✓ |

Claves verificadas:

- El **fault de transacción** (no un entry de mensaje) es lo que transiciona la máquina de
  estados: `{"uuid": <nuevo>, "fault": {"faultCode": ...}, "messages": {}}`.
- Sin `computeInfo` el cliente deja `WORKER_ENDPOINT.routingHost=""` y todo envío al worker
  falla (`SendMessageUtil - no handler for endPoint: WORKER_ENDPOINT`;
  `getRemoteUrlForEndPoint` devuelve `""`). Con `computeInfo.routingHost` = origen del
  shell, `SecurityUtils.isAllowed` lo acepta (`new URL(s)` + comparación same-origin; la
  lista local admite `localhost`/`127.0.0.1`) y el worker usa
  `/messageservice/json/secure`.

### Assets de runtime añadidos (se sirven desde MATLAB_ROOT; nada se copia al repo)

| Prefijo | Contenido | Efecto |
|---|---|---|
| `/ui/*` | `ui/icons/**` + `registry.json` | toolstrip con iconos reales (decenas de `GET /ui/icons/...svg` → 200) |
| `/toolbox/matlab/rich_text_component/*` | `bundle.mwBundle.rtc_R2026b.js` (6.5 MB) | sin «Loading chunk rtc failed» |
| `/toolbox/matlab/rtc_addons/*` | `copilot_{shared,actions,inlinecodegen}.js` | sin errores de chunk copilot |

### Bayeux del escritorio

- El shell usa el endpoint **relativo** `/messageservice/async` (sin `/matlab`); ahora entra
  al manejador de WO-05 (attach/eval MVM) en vez del fallback del probe.
- `advice.interval` del handshake: `0` → `3000`; el diluvio de long-polls (≈5.300 POSTs
  por arranque) bajó a ≈30.
- El **attach MVM ocurrió** (`/matlab/mvm/attach/request`, respuesta encolada) y se
  observaron `feval/request`, `mvmSinks/request`, `subscribeEvent/request`,
  `disconnectEvent/request` (protocolo mw-mvm junior, aún sin implementar).

### Pendientes observados

- `/msh/matlab/content/bundle.mwBundle.agent-spf-ui-matlab.js`: no existe en esta
  instalación (chunk del agente de MATLAB Online) → 404 tolerado.
- Feature flags (`CombinedEditor`, `LiveEditorPagination`): timeout → default `false`.
- `shortcuts` (`request/add/global` ×82) y `settingsChannel/Request` ×143: protocolos
  petición–respuesta por Bayeux sin respuesta (reintentan); candidatos a stub.
