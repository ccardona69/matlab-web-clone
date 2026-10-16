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

## Pruebas

```bash
pytest
```
