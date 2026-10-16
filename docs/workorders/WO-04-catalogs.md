# WO-04 | WS-9 | Catálogos de paridad: errores, warnings y formatos

- **Asignada a:** Gemini 3.8 Flash (soporte a WS-2)
- **Evidencia:** `docs/acceptance/golden-output.txt` (capturado del MATLAB real) + `scripts/acceptance/capture_golden.m` (extensible)
- **Objetivo:** construir los catálogos de paridad textual que W1/W2 usarán como prueba:
  1. **Errores frecuentes** (mínimo 40): función no definida, variable no definida, demasiados/muy pocos argumentos, índices fuera de rango, dimensiones incompatibles en `*`/`\`/`+`, llaves/corchetes desbalanceados, nombres inválidos, división por cero solo warning, etc. Formato: `{ id, code, identifier, text }` con el texto **exacto** del MATLAB real.
  2. **Warnings frecuentes** (mínimo 15): matriz singular, índice no entero ignorado, `implicit expansion` de fila/columna, etc.
  3. **Formatos numéricos** (mínimo 12 variantes): short, long, shortE, longE, shortG, longG, +, bank, hex, rat, compact/loose; documentar en `docs/acceptance/catalogs/formatos-numericos.md` con ejemplos reales.
- **Entregable:**
  1. `docs/acceptance/catalogs/errores-warnings.json`
  2. `docs/acceptance/catalogs/formatos-numericos.md`
  3. Extensión de `scripts/acceptance/capture_golden.m` (o script nuevo `capture_catalogs.m`) con el bloque try/catch reutilizado, y `docs/acceptance/golden-catalogs.txt` capturado.
- **Aceptación:** los JSON/MD contienen solo texto de salida real (datos), sin código de MathWorks; W1 puede consumirlos para implementar los textos exactos.
- **Límites:** la captura del MATLAB real se hace solo con los scripts controlados de este WO; no modificar la instalación. Si un caso no puede capturarse de forma determinista, marcar `deterministic: false` y excluirlo.
- **Rama sugerida:** `ws/9-catalogs`
