# Propiedad de archivos (anti-choques entre IAs)

> Este repo lo trabajan varias IAs en paralelo. Antes de editar, revisa esta tabla.
> Línea base verde: `python -m pytest tests/ -q` → **164 passed + 2 xfailed** (CT-42, CT-60 documentados).
> Nadie mergea/pushea si esa base baja.

## Matriz

| Zona | Dueño(s) | Notas |
|---|---|---|
| `backend/matlab/**` (motor, display, parser, libs) | **OpenCode** | Devin/Gemini/Codex: proponer cambios, no escribirlos |
| `tests/test_acceptance.py`, `tests/test_language.py` | **OpenCode** | El harness dorado; extensible solo coordinado |
| `docs/acceptance/golden-*.txt` | **Captura congelada** | No editar; regenerar solo con scripts de `scripts/acceptance/` |
| `frontend/**` (consola, shell, CSS) | **Devin** (WO-02) + Codex (WO-03) | Codex entra a shell/layout según WO-03 |
| `docs/acceptance/ui/**` | **Devin** | Checklists; capturas derivadas NO se commitean |
| `docs/specs/**`, `backend/bus/**` (o módulo nuevo), `tests/test_bus.py` | **Codex** (WO-05) | Crear módulos nuevos, no incrustar en `backend/app.py` |
| `backend/e1_*.py` (probe E1, WO-06), `tests/test_e1_probe.py` | **Devin** + Codex | Frontend original REAL servido en runtime (`MATLAB_ROOT`); no copias |
| `docs/acceptance/catalogs/**` | **Gemini** (WO-04) | Solo datos de salida real |
| `scripts/acceptance/**` | Coordinado | Capturas MATLAB: licencia Trial — preguntar antes de gastar corridas |

## Reglas de convivencia

1. **Una rama por trabajo** (`ws/2-command-window`, `ws/3-shell-layout`, `ws/7-bus-spec`, `ws/9-catalogs`) y PR a `main`; la verificación final la hace el mantenedor (OpenCode).
2. **`backend/app.py` es punto de encuentro**: cualquier endpoint nuevo va en un módulo/router propio (p. ej. `backend/bus/`, `backend/fonts.py`) con una sola línea de registro en `app.py`. Así dos IAs no chocan en el mismo archivo.
3. **Prohibido commitear** assets/bundles/CSS/código derivado de MathWorks. Fuentes e iconos: solo en runtime desde la instalación local (`MATLAB_ROOT`), nunca copiados. En E1 (WO-06) aplica igual: el webgui real se sirve en runtime (`/mw/`, desde `MATLAB_ROOT`), jamás copiado a carpetas del proyecto.
4. **Antes de cada push**: `python -m pytest tests/ -q` (mínimo la línea base). CI debe quedar verde.
5. Si necesitas tocar un archivo de otra zona: abre un issue o pídelo; no lo edites por tu cuenta.
