# Catálogo de Formatos Numéricos (WO-04 | WS-9)

> Salidas reales capturadas de MATLAB R2026b (PCWIN64) desde `docs/acceptance/golden-catalogs.txt`.
> Este documento sirve como especificación contractual de formato y espaciado de salida para el motor MVM.

## Tabla de Cobertura de Formatos (WO-04)

| Variante solicitada (WO-04) | Caso de captura | Comando MATLAB | Estado de captura |
|---|---|---|---|
| `short` | FM-01 | `format short` | Capturado |
| `long` | FM-02 | `format long` | Capturado |
| `shortE` | FM-03 | `format shortE` | Capturado |
| `longE` | FM-04 | `format longE` | Capturado |
| `shortG` | FM-05 | `format shortG` | Capturado |
| `longG` | FM-06 | `format longG` | Capturado |
| `eng` | FM-07 / FM-08 | `format shortEng` / `format longEng` | Capturado (como variantes `shortEng` y `longEng`) |
| `bank` | FM-09 | `format bank` | Capturado |
| `hex` | FM-10 | `format hex` | Capturado |
| `rat` | FM-11 | `format rat` | Capturado |
| `+` | FM-12 | `format +` | Capturado |
| `compact` | FM-13 | `format compact` | Capturado |
| `loose` | *(Sin caso FM)* | `format loose` | **No presente como caso FM** en `golden-catalogs.txt` (es el espaciado predeterminado con líneas en blanco entre líneas/cabeceras observado en FM-01 a FM-12, pero no existe un caso `FM-xx` con el comando explícito `format loose`) |

---

## Detalle de Casos FM-01 a FM-13

### FM-01: `format short`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format short; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
   1.0e+10 *

    0.0000
    0.0000
    0.0000
    0.0000
    1.0000
   -0.0000

```

### FM-02: `format long`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format long; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
   1.0e+10 *

   0.000000000314159
   0.000000123456780
   0.000000000033333
   0.000000000000001
   1.000000000000000
  -0.000000000100000

```

### FM-03: `format shortE`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format shortE; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
   3.1416e+00
   1.2346e+03
   3.3333e-01
   1.2346e-05
   1.0000e+10
  -1.0000e+00

```

### FM-04: `format longE`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format longE; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
     3.141592653589793e+00
     1.234567800000000e+03
     3.333333333333333e-01
     1.234560000000000e-05
     1.000000000000000e+10
    -1.000000000000000e+00

```

### FM-05: `format shortG`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format shortG; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
       3.1416
       1234.6
      0.33333
   1.2346e-05
        1e+10
           -1

```

### FM-06: `format longG`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format longG; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
          3.14159265358979
                 1234.5678
         0.333333333333333
               1.23456e-05
               10000000000
                        -1

```

### FM-07: `format shortEng`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format shortEng; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
     3.1416e+000
     1.2346e+003
   333.3333e-003
    12.3456e-006
    10.0000e+009
    -1.0000e+000

```

### FM-08: `format longEng`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format longEng; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
    3.14159265358979e+000
    1.23456780000000e+003
    333.333333333333e-003
    12.3456000000000e-006
    10.0000000000000e+009
   -1.00000000000000e+000

```

### FM-09: `format bank`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format bank; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
          3.14
       1234.57
          0.33
          0.00
 10000000000.00
         -1.00

```

### FM-10: `format hex`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format hex; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
   400921fb54442d18
   40934a456d5cfaad
   3fd5555555555555
   3ee9e3fe580f5494
   4202a05f20000000
   bff0000000000000

```

### FM-11: `format rat`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format rat; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
     355/113   
   45679/37    
       1/3     
       2/162001
10000000000       
      -1       

```

### FM-12: `format +`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format +; disp(V)
```

**Salida exacta de MATLAB R2026b:**
```text
+
+
+
+
+
-

```

### FM-13: `format compact`

**Código ejecutado:**
```matlab
V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format compact; disp(V); disp(V')
```

**Salida exacta de MATLAB R2026b:**
```text
   1.0e+10 *
    0.0000
    0.0000
    0.0000
    0.0000
    1.0000
   -0.0000
   1.0e+10 *
    0.0000    0.0000    0.0000    0.0000    1.0000   -0.0000
```
