# WO-06 | WS-2/WS-3/WS-7 | E1: frontend original asistido (webgui real en runtime)

- **Asignada a:** Devin (frontend/loader) + Codex (protocolo del bus)
- **Evidencia:** `backend/e1_probe.py` (integrado en `app.py`; endpoints `/api/e1`, `/api/e1/request-log`, `/api/e1/channels`), `docs/PARITY-PROGRAM.md` §4 E1, `rea/reconstructed/` (469 módulos jsconsole), digests en `rea/ui-analysis/`.
- **Objetivo:** cargar el frontend REAL de MATLAB (`ui/webgui/src`, empezando por `index-nologin.html`) **servido en runtime desde `MATLAB_ROOT`**, apuntado a nuestro backend, y avanzar el render tanto como sea posible implementando lo que pida.

## Mecanismo (ya operativo)

- `GET /mw/` sirve `ui/webgui/src/index-nologin.html` + todos sus assets relativos (`release/**`) desde la instalación local. Nada se copia al repo.
- El probe responde un handshake Bayeux mínimo y registra cada petición desconocida (`501`) con su payload en `/api/e1/request-log`; el mapa deduplicado está en `/api/e1/channels`.
- Precedencia: el router del probe se registra ÚLTIMO en `app.py`; cualquier endpoint real (p. ej. WO-05) gana. Los endpoints nuevos de E1 deben registrarse ANTES del probe.

## Pasos

1. Con `MATLAB_ROOT` configurado, abrir `/mw/` en el navegador y volcar `channels` + `request-log`.
2. Saneado: commitear SOLO el mapa (endpoint/canal + método + conteo + content-type) como `docs/acceptance/ui/e1-request-map.md`. Nunca payloads crudos voluminosos ni fragmentos de bundles.
3. Priorizar por impacto en render: headers (CORP/CSP), MIME de fuentes, rutas de login/desktop; después los canales mw-mvm.
4. Codex: implementar en módulos propios los endpoints REST/Bayeux críticos del mapa (registrarlos antes del probe).
5. La SPA propia (E2) sigue siendo el entregable público y el fallback: E1 nunca debe romperla.

## Límites

- PROHIBIDO copiar archivos de la instalación a cualquier carpeta del proyecto (regla 3 de `docs/OWNERSHIP.md`); todo se sirve en runtime desde `MATLAB_ROOT`.
- Cero bundles/CSS/JS/fuentes de MathWorks en el diff del PR.
- `frontend/**` sigue siendo de Devin+Codex; `backend/e1_*.py` lo evoluciona Devin con revisión de OpenCode.

## Aceptación

- Checklist en `docs/acceptance/ui/` con el progreso del render (qué carga, qué falla y por qué).
- Captura lado a lado del shell real (renderizado en la máquina del usuario con su instalación) sin diferencias visibles frente a MATLAB.

**Rama sugerida:** `ws/3-e1-webgui` (desde `main`).
