# WO-09 — Workspace browser con variables reales

## Objetivo

El panel Workspace del desktop real muestra las variables del `mvm_engine`
(nombre, valor, clase, tamaño) y se actualiza tras cada comando — como hace el
MATLAB real.

## Estado actual (DEVIN — implementado, falta verificación en vivo)

- **Wire real cosechado**: `ml-mirror/_captures_paneles/wire-workspace-real.jsonl`
  (363 eventos; el panel aparece poblado en el oráculo). Dump completo de la
  sesión: `wire-desktop-full.jsonl`.
- **Implementado** en `backend/e1_bus_services.py` (sección "WO-09"):
  - `/DesktopWSB` — `WSBStartup`/`EnableWorkspaceListeners` activan el flag
    `_WSB_ENABLED`; `PauseWorkspaceListeners`/`HideWorkspaceBrowser` lo quitan.
  - `/WorkspaceBrowser_who` — protocolo de eventTypes (ver tabla abajo).
  - `/WorkspaceBrowser` — ack silencioso (propertySet, remoteManagerServerReady).
  - `publish_workspace_variables` — tras cada eval empuja eventType 3 + 2.
  - `set_workspace_provider` — inyecta `mvm.get_workspace_summary` sin ciclo.
- **Tests**: `tests/test_bus.py::test_workspace_browser_who_protocol` (verde).
- **Pendiente de verificar en vivo**: la última prueba mostró el panel sin
  variables (o layout sin el panel). Posibles causas por revisar:
  - El JSD puede esperar el push `servicesStarted` o un mensaje en
    `clientDelivery/client_*` antes de consumir `_who` (WSBReadyService
    reintentaba la suscripción a `/matlab/WSBService/ready` ×22).
  - El `partialData` puede necesitar un campo extra (p.ej. `requestId` o el
    `eventType` correcto en init — ver orden real abajo).
  - Orden de variables: MATLAB ordena case-insensitive (`a,A,c,ch,flag,s`).

## Protocolo REAL descifrado (wire-workspace-real.jsonl + bundle.361.js)

### Cliente → servidor en `/matlab/DesktopWSB`
`{"type":"WSBStartup"}` → `EnableWorkspaceListeners` → … →
`PauseWorkspaceListeners`/`ShowWorkspaceBrowser`/`HideWorkspaceBrowser`.
El servidor no responde nada; solo activa/pausa su empuje de datos.

### `/matlab/WorkspaceBrowser` (documento)
- Cliente: `{"type":"propertySet","propertyName":…,"propertyValue":…}` y
  `/matlab/WorkspaceBrowser/remoteManagerServerReady {}`.
- Servidor empuja `{"Variables":[…],"type":"SelectedVariablesChanged"}`.

### `/matlab/WorkspaceBrowser_who` — eventTypes

Cliente pide (requests `{"eventType":N,…}`):

| eventType | Significado (del bundle) | Respuesta del server (push en el MISMO canal) |
|---|---|---|
| 19 | setClientReady | eventType 1 `{columnCount,rowCount,source:"server"}` |
| 13 | getSize | eventType 1 |
| 20 | getTableMetaData | eventType 3 `{metaDataType:"TableModelProperties",properties:[{class:"char"}]}` |
| 21 | getColumnMetaData | eventType 4 (4 columnas: Name/Value/Size/Class — shape verbatim en `e1_bus_services._WSB_COLUMN_PROPS`) |
| 22 | getRowMetaData | eventType 5 `properties:[{RowNumber:1…N}]` |
| 23 | getCellMetaData | eventType 6 `properties:[[{ColumnNumber,RowNumber}×cols]×rows]` |
| 10 | setViewportRange | eventType 2 (datos del viewport) |
| 11 | getData | eventType 2 `partialData` |
| 12 | setData (editar celda) | (no implementado — editar desde el panel) |
| 14 | getData extendido? | (visto en bundle, no en wire) |
| 24 | setSortColumn | (no implementado) |

`eventType:2` — `partialData` es un STRING JSON doblemente escapado: matriz
rows×cols donde cada celda es a su vez un JSON string:
- col0 (Name): `{"class":"double","editorValue":"a","value":"a"}`
- col1 (Value): `{"editable":true,"editorValue":"a","isMetaData":false,"value":"5"}`
  — o `isMetaData:true` + `value:"4×4 double"` para matrices grandes/cell/struct
  (umbral observado: 3×3 literal, 4×4 metadato → `numel>9`)
- col2 (Size): `{"editable":false,…,"value":"4×4"}`
- col3 (Class): `{"editable":false,…,"value":"double"}`
- `endRow:-1` en request = "todas las filas".

### Tras cada eval
El servidor empuja `eventType 3` + `eventType 2` (partialData completo) en
`/matlab/WorkspaceBrowser_who` — implementado en `publish_workspace_variables`.

### Canales suscritos por el cliente (censo real)
`/matlab/DesktopWSB`, `/matlab/WorkspaceBrowser`, `/matlab/WorkspaceBrowser_who`,
`/matlab/WorkspaceBrowser/MF0ViewModelManagerClient`,
`/matlab/WorkspaceBrowserManager/MF0ViewModelManagerClient`,
`/matlab/viewmodelmulticlient/WorkspaceBrowser{,Manager}`,
`/matlab/WSBService/ready`, `/matlab/clientDelivery/client_*`,
`/matlab/VariableEditorMOTW/variableEditorServerInitialized`,
`/matlab/InspectorPropertyManager`, `/matlab/PropertyInspector`,
`/matlab/variableviewer/open`, `/matlab/datatools/VariableSnapshotManager`.

## Verificación

Panel Workspace del desktop muestra `A`, `a`, `ans` tras los comandos del
curriculum; `pytest -q` sigue verde.
