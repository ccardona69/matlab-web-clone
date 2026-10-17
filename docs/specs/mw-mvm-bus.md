# Contrato mínimo del bus `mw-mvm`

Estado: implementación mínima del clon, derivada de evidencia REA local de MATLAB R2026b. No es una especificación oficial de MathWorks.

## Base de evidencia y grado de certeza

La evidencia primaria es `ev_da7a98bba739ec8565820f30f2b2e2db24add0e9699247d2c0c1365d3933e994`, SHA-256 `d3ad466b5535bf4e86c9d6786db9844634cb80a854c335c3ca029c3fad5b769d`, inventariada en [backend/rea_ledger.py](../../backend/rea_ledger.py). El ledger limita la inferencia a un grafo semántico estático: las llamadas dinámicas pueden quedar sin resolver. Los nombres y campos de abajo son observaciones de `mw-mvm/impl/Connection`, `ConnectionData`, `MVMConnection`, `AttachDetach`, `EvalFevalCancel`, `MVM` y `MWMSink` dentro de `rea/reconstructed/`; no se copia implementación del bundle.

La evidencia secundaria de `rea/ui-analysis/ui-components-details.json` identifica `user-mvm` como endpoint/identidad de MVM. El REA digest también localiza `cometd` y `mw-messageservice`; `MessageServiceAsync` configura el endpoint lógico `/matlab/messageservice/async`. La implementación aquí solo cubre el subconjunto de Bayeux necesario para handshake, connect, subscribe, publish y el flujo attach/eval descrito abajo.

## Modelo de canales

La conexión genera un `requestID` UUID, lo agrega al payload antes de publicar y correlaciona el mensaje recibido por el mismo `requestID`. El prefijo de canal se obtiene en attach. La estructura observada es:

Los nombres de la tabla son canales lógicos vistos por `mw-mvm`. `MessageServiceAsync` antepone `/matlab` al publicar y suscribirse en Bayeux, y elimina ese prefijo al entregar el mensaje a sus consumidores. Por ejemplo, `/mvm/attach/request` viaja en el wire como `/matlab/mvm/attach/request`.

| Canal relativo | Dirección | Función |
|---|---|---|
| `/mvm/attach/request` | cliente → servicio | solicita adjuntar un MVM y negociar API |
| `/mvm/attach/response` | servicio → cliente | devuelve versión y `channelPrefix`, correlacionado por `requestID` |
| `{channelPrefix}/{operation}/request` | cliente → motor | envía operación (`eval`, `feval`, `cancel`, `interrupt`, entre otras) |
| `{channelPrefix}/{operation}/response` | motor → cliente | resuelve o rechaza la promesa asociada con `requestID` |
| `{channelPrefix}/text/output` | motor → cliente | texto stdout vinculado a un request |
| `{channelPrefix}/text/error` | motor → cliente | texto stderr vinculado a un request |
| `{channelPrefix}/mvmSinks/request` | cliente → motor | registra traits/callbacks para sinks de texto |
| `{channelPrefix}/mvmSinks/response` | motor → cliente | confirma la instalación de sinks |

`MVMConnection` añade `{channelPrefix}/{postfix}` y `/request`; su suscripción de respuesta vive en `/response`. En el constructor de `EvalFevalCancel`, los postfix `eval`, `feval`, `cancel`, `cancelGroup`, `interrupt` y `text` son observados. `text` recibe suscripciones `output` y `error`. El canal `mvmSinks` y su evento `output` se observan por separado.

## Mensajes y campos observados

### Attach

Solicitud a `/mvm/attach/request`:

```json
{"mvmID":"user-mvm","supportedApiVersions":["v7_0"],"requestID":"<uuid>"}
```

Respuesta correlacionada en `/mvm/attach/response`:

```json
{"requestID":"<uuid>","apiVersion":"v7_0","channelPrefix":"<prefijo>"}
```

El cliente rechaza/expone errores de comunicación cuando la publicación o suscripción falla. La evidencia indica que `user-mvm` es el único ID aceptado por esa ruta del MVM.

### Eval y respuesta

Solicitud observada en `{prefix}/eval/request`:

```json
{"command":"sum(1:100)","isUserEval":true,"requestID":"<uuid>"}
```

`command` contiene el código MATLAB; `isUserEval` marca evaluación del usuario. La respuesta del transporte se correlaciona mediante `requestID`. En este clon su `data` contiene `{ "requestID": "…", "result": <respuesta REST de ejecución> }`; `result.output`, `result.error`, `result.segments`, estado y resumen del workspace son campos del motor local, no campos wire afirmados por REA.

### Texto y error

Eventos en `{prefix}/text/output` y `{prefix}/text/error` llevan:

```json
{"requestID":"<uuid>","text":"ans =\n\n   5050\n"}
```

El texto llega por separado de la respuesta de `eval`; ambos pueden compartir `requestID`. El sink `mvmSinks` usa el mismo par estructural `{requestID,text}` y además observa `stream` (0 stdout, 1 stderr) en sus eventos `output`.

### Otras operaciones estructuralmente observadas

`feval` usa `function`, `rhsArgs`, `numOutputsExpected`, `runOptions` (`dequeueMode`, `useNullErrSink`, `eventConnections`) y opcionalmente `mdaOutputFormat`; cancelación usa `requestIDtoCancel`, cancelación agrupada usa `requestGroupNametoCancel` y puede incluir `interrupt`. WO-07 implementa `feval` (`eval`/`evalin` evalúan el arg de cadena; el resto construye la llamada), `mvmSinks`, `subscribeEvent` y `disconnectEvent` (ver `backend/e1_bus_services.py`). Cancelación sigue pendiente.

### Servicios del escritorio respondidos (WO-07)

Además del bus MVM, el shell publica peticiones request→response en otros
canales Bayeux que WO-07 responde correlacionadas:

| Canal (sin prefijo `/matlab`) | Respuesta |
|---|---|
| `/editor/event-notification-request` | publica en `data.messageChannel` (p. ej. `/executionstateservice/hasinitialized`) `{dataMap:{isInitialized}, requesterId}` para desbloquear `ExecutionStateService` (`>>` Ready) |
| `/matlab/settingsChannel/Request` | `data.channel` (`/matlab/settingsChannel/Response/<uuid>`) con `{type:<X>Response, uuid, makeCompatible, settingData}` y defaults de fuentes/tema/colores |
| `/shortcuts/model/services/request/{op}/...` | `/shortcuts/model/services/ack` + `/shortcuts/model/services/response/{op}/...` con `{uid, clientId, requestId, responseId, status:true, payload}` |
| `/regfwk/apis/getResourceList` | `/regfwk/apis/resourceList/<clientId>` con `{resourcesFilesData:[], uuid}` |
| `/fctrl/addcb` | `/fctrl/response/addcb` con `{FCtrlState, defaultValue, id, name, scope, value}` |
| `/filesystem/listfolder/*` | `/filesystem/listfolder/started` y `/filesystem/listfolder/response` correlacionado por `uuid` |

## Tópicos de alto nivel y nombres de UI

REA observa los tópicos wire `request`, `response`, `output` y `error`, no strings wire llamados literalmente `commandRequest` o `commandResponse`. Para clientes genéricos, este proyecto define esos nombres como aliases de eventos sobre REST/WS:

| Alias de integración | Payload de este clon | Correspondencia wire |
|---|---|---|
| `commandRequest` | `{command, requestID?, isUserEval?}` | `{prefix}/eval/request` |
| `commandResponse` | `{requestID, result}` | `{prefix}/eval/response` |
| `output` | `{requestID, text}` | `{prefix}/text/output` |
| `error` | `{requestID, text}` | `{prefix}/text/error` |
| `status` | resumen de estado de `/api/mvm/status` | servicio de conveniencia del clon |

## Endpoints del clon

| Método y ruta | Contrato |
|---|---|
| `GET /api/mvm/status` | estado, release y contadores existentes del motor |
| `POST /api/mvm/attach` | JSON de attach → `{apiVersion, channelPrefix}` |
| `POST /api/mvm/command` | `{command, requestID?, isUserEval?}` → `{requestID, result}` |
| `POST /api/mvm/eval` | ruta preexistente, permanece compatible |
| `WS /ws/mvm` | envía `status` al conectar; acepta `{type:"command",command,requestID?}`; emite `output`/`error` y `commandResponse` |
| `POST /matlab/messageservice/async` y `/cometd` | subset Bayeux: `/meta/handshake`, `/meta/connect`, `/meta/subscribe`, `/meta/unsubscribe`, `/meta/disconnect`, attach y eval publish |

El endpoint Bayeux acepta un objeto o un batch de objetos. Handshake devuelve `clientId`, versión Bayeux y transports `long-polling`/`websocket`; connect drena notificaciones en cola para canales suscritos. No implementa extensiones, transporte long-poll mantenido, reintentos, batching completo, MDA, cancelación ni los servicios de Current Folder/Workspace/Editor.

## Flujo manual de compatibilidad

1. Iniciar `uvicorn backend.app:app --reload` y abrir la UI local apuntando el servicio de mensajes a `/matlab/messageservice/async`.
2. La UI debe poder completar handshake y connect; luego publica attach en `/mvm/attach/request` con `mvmID=user-mvm` y `supportedApiVersions=["v7_0"]`.
3. Tras leer `channelPrefix`, suscribirse a `{prefix}/eval/response`, `{prefix}/text/output` y `{prefix}/text/error`.
4. Publicar `{command:"sum(1:100)",isUserEval:true,requestID:<uuid>}` en `{prefix}/eval/request`.
5. El evento `text/output` debe incluir el mismo `requestID` y el texto `ans = 5050`; `eval/response` debe correlacionar el resultado.

El mismo flujo se puede probar sin navegador mediante `POST /api/mvm/command` y con el test automatizado `tests/test_bus.py`.
