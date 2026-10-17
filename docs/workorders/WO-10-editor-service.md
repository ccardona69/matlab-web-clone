# WO-10 — Editor de archivos .m funcional

## Objetivo

El Editor del desktop real abre, muestra, edita y guarda archivos `.m` del
disco del usuario — como el MATLAB real (ya abrió `ejemplo1_regresion.m`
durante las pruebas con el connector).

## Estado actual

- `filesystem/listfolder` ya responde con contenido real del disco
  (`backend/e1_bus_services.py`): raíz, cwd, getchildren, exists, watch.
- Falta: servicio de documentos del editor (open/read/save/buffer), y la
  sincronización Editor <-> Current Folder.

## Apuntes disponibles

- **Wire real cosechado**: `ml-mirror/_captures_paneles/wire-desktop-full.jsonl`
  (363 eventos, contiene todo el flujo filesystem+editor) y
  `apuntes-wo10-editor.md` (84 eventos extraídos del primer volcado).
- Capturas filesystem en `ml-mirror/_captures/` y el mapa de canales en
  `docs/acceptance/ui/e1-request-map.md` (iteración 3).

## Protocolo REAL descifrado (wire-desktop-full.jsonl)

### Secuencia de arranque de servicios (cliente → servidor, todos solo ack)
- `/matlab/filesystem/listfolder/start {}` → server empuja
  `/matlab/filesystem/listfolder/started {"separator":92}` (92 = `\`)
- `/matlab/filesystem/operations/start {}` → `operations/started {}`
- `/matlab/filesystem/sourcecontrol/start {}` → `sourcecontrol/started {}`
- `/matlab/matlab/FileDataServiceChannel {"type":"startServerSide","filepaths":[]}`

### Patrón uuid (todas las llamadas filesystem)
Request lleva `"uuid":"<Service>-<ID>:<RND>-/<op>"`; la respuesta llega ASYNC
en `<canal>/response` con el MISMO `uuid` en el payload (no en el ack Bayeux).

### `/matlab/filesystem/listfolder/<op>` → push `/matlab/filesystem/listfolder/response`
- `get-path-separator {uuid}` → `{"separator":92,"uuid":…}`
- `getprocesscwd {uuid}` → `{"iri":"file:///C:","path":"C:\\","uuid":…}`
- `getfilesystemroots {uuid}` → `{"fileSystemRoots":[<fileInfo>],"uuid":…}`
- `get-iri {"path":"C:\\…"}` → `{"iri":"file:///C:/…","uuid":…}`
- `getchildren {"path":"C:\\…\\","computeHasChildren":false,"uuid":…}` →
  `{"folder":<fileInfo>,"folderContents":[<fileInfo>…],"location":"<dir>","uuid":…}`
- `watch {"iri":"file:///…","reason":"CWD::files","flags":1,"uuid":…}` → `{"uuid":…}`
- `unwatch` similar (reason `filechooser::<id>`).

### Shape `fileInfo` (verbatim)
```json
{"iri":"file:///C:/Users/dav/Documents/MATLAB",
 "isDirectory":true,"isHidden":false,
 "location":"C:\\Users\\dav\\Documents\\","name":"MATLAB",
 "parent":"C:\\Users\\dav\\Documents","path":"C:\\Users\\dav\\Documents\\MATLAB",
 "resolvedTargetPath":"","resolvedTargetType":"","separator":"\\",
 "type":"Folder"}                      // files: type = extensión ("m","pdf"…)
```
`iri` lleva URL-encoding (`%20` por espacios); `location`/`parent` con `\` final.
Raíces: `{"iri":"file:///C:","location":"\\","name":"C:","parent":"\\",…}`.

### `/matlab/filesystem/operations/<op>` → push `/matlab/filesystem/operations/response`
- `exists {"path":"…","uuid":…}` → `{"exists":true,"isDirectory":false,"uuid":…}`

### Editor
- `/matlab/editor/systeminfoservice/request {"uid":"…","type":"isWindows"|"isRootUser","data":""}`
  → push `/matlab/editor/systeminfoservice/response {"data":{"isWindows":true},"uid":"…"}`
- `/matlab/editor/event-notification-request {"messageChannel":"/executionstateservice/hasinitialized","requesterId":"…"}`
- `/matlab/editor/reflector` — publica `{"channel":"/userexecutionservice/onUserExecution","data":"{\"uuid\":\"…\"}"}` tras exec
- `matlab.desktop.Documents` (settingsChannel): sync de docs abiertos con
  `fileInfo {location,name,filePermissions.canWrite,isDirectory,parent}`.

## Tareas

1. ~~Cosechar wire del Editor~~ — hecho (ver arriba).
2. Implementar servicio de documentos (leer archivo real del disco vía
   filesystem backend ya existente) + FileDataServiceChannel.
3. Guardar: escritura al disco (cuidado: rutas del usuario; sandbox bajo
   root configurable).

## Tareas

1. Cosechar wire del Editor (abrir/guardar `.m` en sesión JSD real).
2. Implementar servicio de documentos (leer archivo real del disco vía
   filesystem backend ya existente).
3. Guardar: escritura al disco (cuidado: rutas del usuario).

## Verificación

Editor abre `ejemplo1_regresion.m` con contenido correcto; `pytest -q` verde.
