# WO-05 | WS-7 | Bus `mw-mvm` y servicios MATLAB-compatibles (spec + implementación)

- **Asignada a:** OpenCode + Codex
- **Evidencia:** análisis REA de `ui/jsconsole` (local: `rea/reconstructed/`, 469 módulos; mensajes del bus y endpoints) + `rea/ui-analysis/` digests + `backend/rea_ledger.py` (11 P/Invoke de libMatlabEngine)
- **Objetivo:** especificar e implementar el mínimo de servicios que el frontend original (E1) espera:
  1. `docs/specs/mw-mvm-bus.md`: inventario de mensajes/topics observados en la evidencia (p. ej. `user-mvm`, `commandRequest`, `commandResponse`, `output`, `status`), con campos y semántica documentada por REA.
  2. Endpoints REST/WS mínimos en `backend/` equivalentes a `mw-mvm/impl/Connection`.
  3. Stub de cometd (handshake + canal de notificaciones) para que la UI original no se bloquee al arrancar.
- **Entregable:** spec + endpoints + `tests/test_bus.py` que valide el flujo comando→salida sin UI.
- **Aceptación:** `pytest tests/test_bus.py -q` verde; el flujo documentado en la spec permite, con la UI real local, enviar `sum(1:100)` y recibir `ans = 5050` (verificación manual guiada por la spec).
- **Límites:** la spec describe protocolo (nombres de mensajes/campos), que es información estructural; no pegar código ni bundles originales en el repo.
- **Rama sugerida:** `ws/7-bus-spec`
