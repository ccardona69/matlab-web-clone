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

## Pruebas

```bash
pytest
```
