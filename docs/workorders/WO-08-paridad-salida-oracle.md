# WO-08 — Paridad de salida contra el oráculo (examen de ciego)

## Objetivo

Subir la nota del examen de ciego `scripts/diff_wire.py` de **54/87** a la máxima
posible sin tocar el protocolo Bayeux (ya verificado 87/87 respuestas).

El "profesor" es el connector real de MATLAB R2026b (`:31515`); el "alumno" es
nuestro backend (`mvm_engine` + `e1_bus_services`). Los apuntes — muestras
verbatim del wire real por comando — están en:

    ml-mirror/_captures/oracle-apuntes.md      (curado, 18 KB, LEER PRIMERO)
    ml-mirror/_captures/wire-20261016-220151.jsonl  (wire completo del profesor)
    ml-mirror/_captures/_alumno/wire-*.jsonl        (wire del alumno)

## Brechas medidas (baseline 54/87)

### B1. `<RICH_OUTPUT>` — 19 comandos

El profesor envía las variables/matrices mostradas como JSON estructurado
envuelto en `<RICH_OUTPUT>...</RICH_OUTPUT>` por `mvmSinks/output` (stream 0):

```
<RICH_OUTPUT>{"outputsData":"{\"type\":\"matrix\",\"outputData\":{\"name\":\"A\",\"value\":\"\",\"header\":\"\",\"type\":\"double\",\"rows\":3,\"columns\":3,\"doc_id\":\"\",\"ve_channel\":\"\",\"subtype\":\"double\",\"prepopulatedData\":[[\"1\",\"2\",\"3\"],...],\"exponent\":\"1\",\"snapshotID\":0,\"displayFormat\":\"short\"},\"lineNumbers\":[],\"format\":\"loose\"}"}</RICH_OUTPUT>
```

Decodificado por tipo en `oracle-apuntes.md` (ver `A = [1 2 3; 4 5 6; 7 8 10]`,
`magic(4)`, `c = {...}`, `s`, `whos`, etc.). El alumno hoy envía texto plano.
Implementar el sobre RICH_OUTPUT donde el apunte lo muestre; el resto queda en
texto plano (escalares `ans = 4` van como texto, ver `2+2`).

### B2. `data.error` estructurado en eval/response — 7 comandos

El profesor incluye en `eval/response.data.error`:

```json
{"id": "MATLAB:badsubscript",
 "msg": "Index exceeds the number of array elements. Index must not exceed 9.",
 "status": "inRUNTIME_ERROR",
 "frames": [{"file": "", "func": "", "line": 1}]}
```

IDs reales capturados: `MATLAB:UndefinedFunction`, `MATLAB:m_unexpected_sep`,
`MATLAB:sizeDimensionsMustMatch`, `MATLAB:badsubscript`,
`MATLAB:cellRefFromNonCell`, `MATLAB:math:mustBeFloat`. El alumno devuelve
`eval/response` sin `error`. Mapear los errores del motor a esos ids/msg.

OJO: el texto del error TAMBIÉN llega por `mvmSinks/output` stream=1, a veces
**en la ventana del comando siguiente** (stderr asíncrono — apunte real, no bug).

### B3. Detalles residuales de formato (~6 comandos)

Espaciado exacto de `whos`, `primes`, `pwd`, etc. — comparar con --verbose.

## Dónde tocar

- `backend/mvm_engine.py` — produce `result["segments"]` (kind out/err/warn).
- `backend/e1_bus_services.py::_publish_command_output` — publica por
  `{prefix}/mvmSinks/output` y `{prefix}/text/*`; aquí va el sobre RICH_OUTPUT.
- `backend/app.py::_command_result` — `eval/response`: añadir `data.error`.
- `scripts/diff_wire.py` — el juez (no hace falta tocarlo).

## Cómo verificar (examen)

```bash
# 1) backend emulado en :8002 (MATLAB_ROOT solo para assets, opcional)
python -m uvicorn backend.app:app --port 8002

# 2) correr el curriculum contra el alumno
python scripts/harvest_wire.py --url http://127.0.0.1:8002 \
    --out ml-mirror/_captures/_alumno

# 3) nota del examen (profesor: wire-20261016-220151.jsonl)
python scripts/diff_wire.py ml-mirror/_captures/wire-20261016-220151.jsonl \
    ml-mirror/_captures/_alumno/<nuevo>.jsonl --verbose
```

También `python -m pytest -q` debe seguir en verde (192 tests).

## Restricciones

- NO commitear nada de `ml-mirror/` ni capturas (gitignored; son apuntes, no
  redistribución).
- NO tocar el protocolo Bayeux/handshake/attach — ya es correcto.
- Mantener `text/output`+`mvmSinks/output` doble publicación (el JSD usa ambos;
  el examen solo juzga `mvmSinks/output`).
