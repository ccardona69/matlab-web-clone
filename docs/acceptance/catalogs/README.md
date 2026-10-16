# Catálogos de Paridad MATLAB R2026b (WO-04 | WS-9)

Este directorio contiene los catálogos estructurados de salida canónica de MATLAB R2026b (PCWIN64) para consumo del equipo de desarrollo (W1/OpenCode, W2/Codex):

- [`errores-warnings.json`](./errores-warnings.json): Catálogo estructurado de errores y advertencias canónicas.
- [`formatos-numericos.md`](./formatos-numericos.md): Especificación de salida y espaciado de variantes de `format`.

---

## Métricas de Cobertura (WO-04)

| Categoría | Meta WO-04 | Casos capturados | Estado | Notas |
|---|---|---|---|---|
| **Errores** | $\ge 40$ | **43 errores** | ✅ Superada | 42 en catálogo base (`CT-01`..`CT-50`) + 1 en catálogo extra (`CT-66`). |
| **Warnings** | $\ge 15$ | **10 warnings** | ⚠️ Meta no alcanzada | 4 en catálogo base (`CT-49`, `CT-51`, `CT-58`, `CT-59`) + 6 en catálogo extra (`CT-61`..`CT-65`, `CT-71`). |
| **Formatos numéricos** | $\ge 12$ | **13 variantes** | ✅ Superada | Casos `FM-01` a `FM-13` (short, long, shortE, longE, shortG, longG, shortEng, longEng, bank, hex, rat, +, compact). |

---

## Análisis de Warnings y Casos Silenciosos en R2026b

Durante la corrida única controlada de captura extendida ([`capture_catalogs_extra.m`](../../scripts/acceptance/capture_catalogs_extra.m) ejecutada contra MATLAB R2026b real, registrada en `golden-catalogs-extra.txt`), se evaluaron 12 casos candidatos con los siguientes resultados:

### Warnings capturados (6 casos):
1. **`CT-61`**: `polyfit(1:3, [1 2 3], 3)` → `MATLAB:polyfit:PolyNotUnique`
   > *"To fit a unique polynomial, reduce the degree to be less than the number of data points."*
2. **`CT-62`**: `A = [1 2; 2 4]; A \ [1; 2]` → `MATLAB:singularMatrix`
   > *"Matrix is singular to working precision."*
3. **`CT-63`**: `inv(hilb(15))` → `MATLAB:nearlySingularMatrix`
   > *"Matrix is close to singular or badly scaled. Results may be inaccurate. RCOND =  8.269626e-19."*
4. **`CT-64`**: `nchoosek(100, 50)` → `MATLAB:nchoosek:LargeCoefficient`
   > *"Result may not be exact. Coefficient has a maximum relative error of 1.6875e-14, corresponding to absolute error 1702580784238102."*
5. **`CT-65`**: `rmpath('C:\no_such_dir_xyz')` → `MATLAB:rmpath:DirNotFound`
   > *`"C:\no_such_dir_xyz" not found in path.`*
6. **`CT-71`**: `ode45(@(t,y) y.^2, [0 10], 1)` → `MATLAB:ode45:IntegrationTolNotMet`
   > *"Failure at t=9.999858e-01.  Unable to meet integration tolerances without reducing the step size below the smallest value allowed (1.776357e-15) at time t."*

### Error capturado (1 caso):
- **`CT-66`**: `table([1;2], [3;4], 'VariableNames', {'a','a'})` → `MATLAB:table:DuplicateVarNames`
  > *"Duplicate table variable name: 'a'."*

### Candidatos silenciosos (5 casos — excluidos del catálogo de errores/warnings):
En MATLAB R2026b estos 5 patrones no emiten `warning` ni `error`:
- **`CT-67`** (`1:0:5`): produce `1×0 empty double row vector` silenciosamente.
- **`CT-68`** (`[1, 2+3i] < 2`): la comparación compleja produce `1×2 logical array` (`1   0`) sin advertencia.
- **`CT-69`** (`strmatch('a', {'a','b'})`): función heredada que ejecuta y devuelve `1` sin emitir advertencia por consola.
- **`CT-70`** (`strread('1 2', '%d')`): función heredada que ejecuta y devuelve `[1; 2]` sin emitir advertencia por consola.
- **`CT-72`** (`quad(@(x) x.^2, 0, 1)`): función clásica de cuadratura que devuelve `0.3333` sin advertencia por consola.

Por esta razón, la cobertura de advertencias queda en **10 warnings reales y documentados**, reflejando la conducta real y determinista de MATLAB R2026b.

---

## Contrato de `errores-warnings.json`

Cada entrada cumple con:
```json
{
  "id": "CT-xx",
  "type": "error" | "warning",
  "code": "código MATLAB que provoca la condición",
  "identifier": "identificador canónico (o \"\" si no tiene)",
  "text": "mensaje byte-exacto de MATLAB real",
  "deterministic": true
}
```
Todos los casos son deterministas (`deterministic: true`).
