# WO-11 — Figuras embebidas (plot/figure/surf)

## Objetivo

`plot`, `figure`, `bar`, `scatter`, etc. producen una figura web real dentro
del desktop — la pieza más compleja del clon.

## Estado actual

- `figure`/`plot`/`close all` ya responden OK (eval pasa).
- El profesor, al hacer `plot`, abre un **segundo attach MVM** y eventos de
  grupo `UserGroup` (capturado en ronda 1 y 2).

## Apuntes disponibles

- `ml-mirror/_captures_paneles/apuntes-wo11-figures.md` — 67 eventos del
  flujo figure/uicontainer (incluye `figureCreated` verbatim).
- `ml-mirror/_captures_paneles/wire-desktop-full.jsonl` — handshake del
  contenedor undocked (clientSubscribed, setUndockInWindowFigureContainer…).
- `ml-mirror/_captures/_ronda2/wire-20261016-221912.jsonl` — comandos fig2:
  plot con datos, title/xlabel/ylabel, hold on, legend, figure(2), bar,
  subplot, scatter.

## Protocolo REAL descifrado (wire de paneles)

### Creación de figura (server → client, tras `plot()`)
Push en `/matlab/gbtweb/divfigure/figureCreated`:
```json
{"Uuid":"<uuid4>","channel":"/uifigure/<uuid>",
 "ClientToServer":"/embeddedfigure/ClientToServer",
 "ServerToClient":"/embeddedfigure/ServerToClient",
 "Title":"Figure 1","Position":[423,230,1074,647]}
```

### Flujo del contenedor (undocked window)
1. Cliente suscribe `/matlab/gbtweb/divfigure/*`, `/matlab/embedded/figure/*`,
   `/matlab/motw/uicontainer`, `/matlab/updateUndockInWindowFigureContainer`.
2. Ventana undocked abre `undocked-container.html?id=<id>&websocket=on`
   con SU PROPIO handshake Bayeux y envía:
   - `/matlab/motw/uicontainer {"type":"started"}` (al abrir) /
     `{"type":"terminated"}` (al cerrar)
   - `/matlab/gbtweb/divfigure/clientSubscribed {}`
   - `/matlab/gbtweb/divfigure/setUndockInWindowFigureContainer {}`
   - `/matlab/gbtweb/divfigure/figureRefresh {}`
   - `/matlab/mg2web/eventChannel {"type":"command","message":"register",
     "id":"main","clientType":"Normal"}` y eventos
     `{"type":"event","data":{"type":"focused",…}}`
   - `/matlab/mlapp/figure {"eventType":"moRefreshed"}`
3. Todos esos requests reciben ack silencioso (data null).
4. Los PÍXELES del plot viajan por **websocket** (`&websocket=on` en la URL
   del contenedor) — el clon renderiza la figura con canvas/SVG propio en una
   página servida por nosotros (frontend/ es nuestro, no MathWorks).

### Canales por figura (suscripciones del JSD)
`/uifigure/<uuid>`, `/embeddedfigure/ClientToServer`,
`/embeddedfigure/ServerToClient`, `/embedded/figure/toolstrip/*`,
`/matlab/figureContainerDefault`.

## Tareas

1. Cosecha profunda del canal de figuras (attach secundario + suscripciones).
2. Decidir renderer propio: el panel de figura JSD espera datos/render
   — evaluar enviar imagen/SVG generada (matplotlib) vs datos MDA.
3. Implementar el segundo attach + publicación de figura.

## Verificación

`plot(1:10)` en el Command Window produce una figura visible en el desktop;
`pytest -q` verde.

## Nota de alcance

Es la WO más grande: puede dividirse (WO-11a solo figura estática renderizada,
WO-11b interactividad/zoom). No bloquea el uso básico del clon para estudios.
