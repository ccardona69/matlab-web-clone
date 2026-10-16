# matlab-web-clone

Reconstrucción funcional de MATLAB (entorno R2026b) como aplicación web: intérprete del lenguaje MATLAB en Python, motor de gráficos Handle Graphics renderizado con Matplotlib, y una interfaz web estilo escritorio MATLAB.

## Estructura

- `backend/` — API FastAPI, intérprete MATLAB (lexer, parser, intérprete, librerías builtin) y motor de gráficos.
- `frontend/` — SPA vanilla (HTML/CSS/JS) con editor, consola, workspace y figuras.
- `scripts/` — Scripts `.m` de ejemplo (FFT, SVD, ODE45, superficies 3D).
- `tests/` — Pruebas con pytest (lenguaje + API).
- `rea/` — Scripts de análisis usados para la reconstrucción por ingeniería inversa (los artefactos de evidencia grandes no están versionados).

## Uso

```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Abrir http://localhost:8000

### Modo E1 standalone (mirror local de assets, opcional)

Para servir el shell real (E1) **sin depender de tener MATLAB instalado en
cada ejecución**, congela una vez los assets HTTP del webgui desde tu
instalación licenciada a una carpeta local ignorada por git (~120 MB):

```bash
python scripts/mirror_matlab_webgui.py            # usa MATLAB_ROOT (o --source)
```

El backend lo detecta automáticamente (`ml-mirror/`) cuando `MATLAB_ROOT` no
está definido: `GET /mw/` y los assets del shell se sirven del mirror. Nada de
MathWorks se copia al repo.

### Variables de entorno (E1/E2)

| Variable | Efecto |
|---|---|
| `MATLAB_ROOT` | Instalación local de MATLAB; sirve `ui/webgui/src` bajo `/mw/` y assets de runtime (`/ui/*`, `/toolbox/*`, `/sys/*`) |
| `MATLAB_MIRROR` | Raíz alternativa de assets (mirror generado por `scripts/mirror_matlab_webgui.py`) |
| `MATLAB_CONNECTOR_URL` | **Modo oráculo** (opt-in): proxea los paths de servicio del shell (`/messageservice/*`, `/matlab/*`, `/msh/*`…) al connector real de MATLAB (p. ej. `https://127.0.0.1:31515`). Vacío = emulador propio |
| `E1_SHELL` | `nologin` (default) o `jsd` para elegir el entry de `/mw/` (`index-nologin.html` vs `index-jsd.html`) |

## Pruebas

```bash
pytest
```
