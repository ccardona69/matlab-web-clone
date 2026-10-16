# Checklist lado a lado — Command Window (WO-02)

Comparación visual gemelo vs MATLAB R2026b real para AC-01…AC-20.
Las capturas lado a lado viven solo en local (no se commitean); este checklist sí.

**Evidencia visual extraída del webgui real** (`C:\Program Files\MATLAB\R2026b\ui\webgui\src\release\3365190-20260824045858`):

| Propiedad | Valor real | Fuente |
|---|---|---|
| Fuente consola | `Menlo,Monaco,Consolas,Courier New,monospace` @14px | `index-css.css` `.commandWindow` |
| Line-height | 1.286 | `index-css.css` `.paragraphNode` |
| Color salida/texto | `#212121` (gray900, `--mw-color-code`) | `index-css.css` tokens |
| Prompt `>> ` | `#0E00FF` (cobalt600, ansiColor-blue-bright) | `index-css.css` tokens |
| Error | `#E11B14` (red550, `--mw-color-matlabErrors` → `--rtc-error-output-color`) | `index-css.css` + `bundle.361.js` (replace literal `#E11B14`) |
| Warning | `#B36205` (honey550, `--mw-color-matlabWarning` → `--rtc-warning-output-color`) | `index-css.css` + `bundle.361.js` (replace literal `#B36205`) |
| Hyperlinks (`> In f (line n)`) | azul subrayado | `index-css.css` `.scrollPane a` |
| Wrap | `pre-wrap; word-wrap:break-word; overflow-wrap:anywhere` (modo `.wrappable`) | `index-css.css` `.scrollPane.wrappable` |
| Prompt inline | `>> ` dentro del área scrollable; sin caja de entrada separada | comportamiento CW real |
| Busy | prompt oculto durante evaluación, status "Busy" | comportamiento CW real |
| Assets (fuentes/iconos) | servidos en runtime desde `MATLAB_ROOT` (`/api/assets/matlab/`, `/api/assets/fonts.css`), opt-in | WO-02 entregable 2 |

## Casos de aceptación

| Caso | Comando | Texto ✓ (dorado) | Colores ✓ | Notas |
|---|---|---|---|---|
| AC-01 | `pi` | ☐ | ☐ | `ans =` + valor, negro sobre blanco |
| AC-02 | `format long; pi` | ☐ | ☐ | 15 dígitos |
| AC-03 | `A = [...]; disp(A)` | ☐ | ☐ | matriz sin `ans =` (disp) |
| AC-04 | `disp([...]')` | ☐ | ☐ | transpuesta |
| AC-05 | `magic(4)` | ☐ | ☐ | matriz 4×4 con `ans =` |
| AC-06 | `sum(1:100)` | ☐ | ☐ | `5050` con sangría ancha |
| AC-07 | `x = linspace(...); disp(x)` | ☐ | ☐ | vector fila |
| AC-08 | `sqrt(-4)` | ☐ | ☐ | complejo `0.0000 + 2.0000i` |
| AC-09 | `1/0` | ☐ | ☐ | `Inf` |
| AC-10 | `0/0` | ☐ | ☐ | `NaN` |
| AC-11 | `sprintf('%.3f', pi)` | ☐ | ☐ | `'3.142'` con comillas |
| AC-12 | `num2str(pi, '%.5e')` | ☐ | ☐ | `'3.14159e+00'` |
| AC-13 | `strcat('ma', 'tlab')` | ☐ | ☐ | `'matlab'` |
| AC-14 | `sin(1, 2, 3)` | ☐ | ☐ | error en **#E11B14**: `Too many input arguments.` |
| AC-15 | `undefined_fn_xyz(1)` | ☐ | ☐ | error en **#E11B14** |
| AC-16 | `inv([1 2; 2 4])` | ☐ | ☐ | `Warning:` en **#B36205** + `> In ... (line n)` como link azul |
| AC-17 | `eig([2 0; 0 3])` | ☐ | ☐ | columna 2, 3 |
| AC-18 | `format rat; pi` | ☐ | ☐ | `355/113` + espacios finales |
| AC-19 | `struct('a', 1)` | ☐ | ☐ | `struct with fields:` |
| AC-20 | `q = 42; whos q` | ☐ | ☐ | tabla `whos` monoespaciada |

## Interacción

| Acción | Esperado (paridad MATLAB) | ✓ |
|---|---|---|
| Enter en `>> ` | eco `>> cmd` (>> azul, cmd negro) + salida + nuevo `>> ` | ☐ |
| `clc` | ventana vacía por completo (incluido el eco de `clc`), prompt limpio | ☐ |
| `clear` | sin salida; panel Workspace vacío | ☐ |
| ↑ / ↓ | recorre historial inline en el prompt | ☐ |
| Tab | autocompleta builtins/vars; prefijo común o popup de candidatos | ☐ |
| Clic en salida | enfoca el prompt (salvo selección de texto) | ☐ |
| Durante evaluación | prompt oculto, status "Busy", sin entrada | ☐ |

## Cómo capturar

1. `set MATLAB_ROOT=C:\Program Files\MATLAB\R2026b` (activa assets locales) y `uvicorn backend.app:app`
2. Abrir `http://localhost:8000`, ejecutar cada comando del set en el gemelo y en MATLAB real
3. Comparar colores (cuentagotas), fuente, márgenes y texto byte a byte
