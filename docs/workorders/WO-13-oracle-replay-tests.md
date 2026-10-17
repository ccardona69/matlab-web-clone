# WO-13 — Examen permanente: replay de apuntes como tests

## Objetivo

Convertir las capturas JSONL del profesor en tests ejecutables que repliegan
cada comando contra `mvm_engine` y verifican paridad — el "examen" deja de ser
manual (diff_wire) y pasa a ser parte de pytest para siempre.

## Por qué

- Las capturas (`ml-mirror/_captures/*.jsonl`) son locales/gitignored — cuando
  expire la licencia son la única verdad disponible.
- Un test runner que las consuma convierte cada apunte en una aserción:
  si alguien rompe el motor, pytest lo grita.

## Diseño propuesto

`tests/test_oracle_replay.py`:

1. Localiza capturas del profesor en `ml-mirror/_captures/` (glob `wire-*.jsonl`
   en raíz y subdirs `_ronda*/`). Si no existen → `pytest.skip` (CI sin capturas
   no debe fallar).
2. Por cada registro `note: command` → ejecuta `MatlabVirtualMachine.execute(cmd)`
   (o el path equivalente) en una VM fresca persistente por sesión (el workspace
   importa: `a = 5` antes de `a`).
3. Compara lo que el usuario vería:
   - Texto: la concatenación de segmentos de salida vs `mvmSinks/output` del
     apunte (normalización igual que `diff_wire.normalize`; los segmentos con
     `sink_text`/`rich` usan ese campo).
   - Errores: `result["error_data"]["id"]` y `["msg"]` vs `data.error` del
     apunte.
4. XFAIL documentado:
   - stderr asíncrono del profesor (texto de error que llega en la ventana
     del siguiente comando — lista en WO-08).
   - no-deterministas: `date`, `datetime('now')`, `now`, `tic; toc`,
     `randperm(5)` (sin semilla), `who`/`whos` (contenido depende del estado).
   - Comandos que mutan filesystem real (`save`/`load`/`delete`/fopen) si el
     entorno de test no los soporta.
5. Parametriza por comando (`pytest.mark.parametrize` o generador) para que el
   reporte muestre exactamente qué apunte falla.

## Resultado esperado

- ~250 tests parametrizados, mayoría passing hoy (paridad ~98%).
- Cada ronda futura de cosecha = más tests gratis (regenerar es solo copiar
  el JSONL).

## Restricciones

- Solo añadir `tests/test_oracle_replay.py` (+ fixture pequeña en
  `tests/conftest.py` si hace falta). NO tocar producción.
- No commitear. `python -m pytest -q` debe quedar verde (xfail permitido).

## Verificación

```bash
python -m pytest tests/test_oracle_replay.py -v
python -m pytest -q
```
