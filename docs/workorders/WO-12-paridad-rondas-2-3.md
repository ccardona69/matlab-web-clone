# WO-12 — Paridad rondas 2 y 3 del curriculum (examen de ciego)

## Objetivo

Subir el score de `scripts/diff_wire.py` en las rondas 2 y 3 del curriculum
de comandos (171 comandos que WO-08 no cubrió).

## Baselines medidos (2026-10-16)

| Ronda | Texto | Errores | Captura profesor | Captura alumno |
|---|---|---|---|---|
| 2 | 52/81 | 73/81 | `_ronda2/wire-20261016-221912.jsonl` | `_alumno/wire-20261016-231318.jsonl` |
| 3 | 60/90 | 75/90 | `_ronda3/wire-20261016-224546.jsonl` | `_alumno3/wire-20261016-231508.jsonl` |

## Worklist pre-masticada (LEER PRIMERO)

`ml-mirror/_captures/wo12-diffs.md` — cada diff ya extraído: comando, texto
profesor vs alumno, error profesor vs alumno. ~59 items.

## Familias de diffs (lo que falta en el motor)

1. **Builtins ausentes**: `union`, `intersect`, `setdiff`, `perms`, `fopen`,
   `fclose`, `fgetl`, `license`, `help`/`lookfor`/`which`/`doc` (texto de ayuda),
   `date`/`datetime`/`duration`, `ver`, `what`, `tic`/`toc`.
2. **Formato**: `logical`, `gcd`, `lcm`, `factor`, `syms` (debe dar error de
   toolbox ausente), `nchoosek(-1,2)`, `fminbnd`, `ode45` (sin salida visible),
   `format compact`, `ver`, `what`.
3. **Errores**: ids y mensajes nuevos (`MATLAB:lang:InvalidEqualsInParens`,
   `MATLAB:type:fileNotFound`...). El mecanismo `error_data` de WO-08 ya existe
   en `mvm_engine.py` — extender el mapeo.
4. **Structs**: salida de asignación anidada y `rmfield`.

## Dónde tocar

- `backend/mvm_engine.py` — builtins + error_data + formato.
- `backend/matlab/` — librería de funciones si aplica (revisar primero qué
  builtins ya existen ahí).
- `backend/e1_bus_services.py` / `app.py` — solo si el shape lo requiere.

## Verificación

```bash
python -m uvicorn backend.app:app --port 8002    # en otra terminal
# ronda 2 alumno:
python scripts\harvest_wire.py --url http://127.0.0.1:8002 --out ml-mirror\_captures\_alumno --only help,error2,logic,complex,linalg,poly,stats,str2,struct2,files,fig2
python scripts\diff_wire.py ml-mirror\_captures\_ronda2\wire-20261016-221912.jsonl ml-mirror\_captures\_alumno\<nuevo>.jsonl --verbose
# ronda 3 alumno:
python scripts\harvest_wire.py --url http://127.0.0.1:8002 --out ml-mirror\_captures\_alumno3 --only datetime,rng,round,trig,explog,matops,types,setops,fnhandle,format2,fileio,err3,misc
python scripts\diff_wire.py ml-mirror\_captures\_ronda3\wire-20261016-224546.jsonl ml-mirror\_captures\_alumno3\<nuevo>.jsonl --verbose

python -m pytest -q   # 192 tests deben seguir verdes
```

## Reglas

- No commitear. No tocar `ml-mirror/` salvo capturas nuevas del alumno.
- Comportamientos no-deterministas (`date`, `now`, `tic/toc`, `randperm`
  sin semilla): el score de texto puede no ser alcanzable; priorizar shape
  correcto y documentar.
- `ode45`/`fzero`/`fminbnd`: si la implementación numérica exacta es costosa,
  aproximar el formato de salida; lo importante es la paridad visible.
