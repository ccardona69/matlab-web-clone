# WO-01 | WS-1 | Motor `.m`: paridad contra capturas doradas

- **Asignada a:** OpenCode + Codex
- **Evidencia:** `docs/acceptance/golden-output.txt` (oráculo capturado del MATLAB real, R2026b 26.2.0.3386108) + `docs/acceptance/acceptance-20.json` + `rea/reconstructed/` (local, 469 módulos jsconsole) + `rea/reconstruction-obligation-ledger.md`
- **Objetivo:** que el intérprete del gemelo (`backend/matlab/`) produzca salidas **idénticas** a las doradas para los 20 casos AC-01…AC-20: formato numérico short/long/rat, display de matrices y vectores, complejos, Inf/NaN, struct, `whos`, y textos exactos de errores y warnings.
- **Entregable:**
  1. Ajustes en `backend/matlab/` (interpreter + bibliotecas) para los casos que fallen.
  2. `tests/test_acceptance.py`: parsea `golden-output.txt` (marcadores `<CASE>`, `<CODE>`, `<ERROR id | msg>`, `<WARN id | msg>`, `<END>`), ejecuta cada caso en el motor y compara línea a línea. Los fallos deben listar diff esperado vs obtenido.
  3. En el parser: el texto canónico de errores/warnings son los marcadores `<ERROR ...>`/`<WARN ...>`; ignorar los bloques inline `[Warning: ...]` con stack trace (ruido del modo batch).
- **Aceptación:** `pytest tests/test_acceptance.py -q` verde en CI (ubuntu), y `pytest` completo sin regresiones (73 tests actuales siguen pasando).
- **Límites:** no ejecutar MATLAB (las capturas ya existen); no modificar `golden-output.txt` ni `acceptance-20.json` salvo añadir casos (coordinado). No commitear contenido derivado de MathWorks.
- **Rama sugerida:** `ws/1-motor-golden`

## Estado (2026-10-16, OpenCode)

Completado base (AC-01…AC-20 y catálogo CT/FM):

1. `tests/test_acceptance.py` landea el parser de dorados (creado por OpenCode; Codex no debe reescribirlo, sí ampliarlo).
2. **AC-01…AC-20: 20/20.** Catálogo `golden-catalogs.txt`: **71/73**, con 2 pendientes documentados como xfail no estricto (`PENDING_CATALOG` en el test):
   - CT-42: `ode45` debe reproducir el número exacto de pasos adaptativos de MATLAB (golden 1×11 vs motor 17×1).
   - CT-60: `fzero` sin intervalo con signo debe imprimir el punto exacto de su búsqueda interna (algoritmo de fzero).
3. Reglas de display calibradas contra capturas reales R2026b (comentadas en `backend/matlab/display.py`): floats `max(w+2, 10/20)`, E `max(w+2, 13/26)`, g `max(w+3, 13/26)`, eng `w+3`, enteros `w+3`, escalar doble entero 6/12, rat 15 fijo, bank `max(14, len+1)`, hex `w+3`, struct/Map con `"x = "`, whos 55 columnas.
4. Advertencias estructuradas: `execute()` ahora devuelve `error_id` y `warnings[{id,message}]`; `interp.warn(msg, id)`. Errores de parseo usan identificadores `MATLAB:m_*` y render `Error: <msg>` (sin ubicación, como el texto canónico).
5. `library_containers.py`: `containers.Map()` (presentación) y `dictionary()` (lookup sin configurar → `MATLAB:dictionary:UnconfiguredLookupNotSupported`).

Suite local completa: 164 passed + 2 xfailed. Sin MATLAB requerido.
