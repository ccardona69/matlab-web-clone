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
