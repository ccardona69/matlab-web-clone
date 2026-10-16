# PLAN MAESTRO — Gemelo de MATLAB R2026b con frontend indistinguible

Versión: 1.1 (2026-10-16) · Coordinación: OpenCode · Repo: https://github.com/ccardona69/matlab-web-clone
IA participantes: OpenCode (coordinación/verificación) + Codex + Devin + Gemini 3.8 Flash
Target único de evidencia: `C:\Program Files\MATLAB\R2026b` — Release 26.2.0.3386108, 4.46 GB (< 6 GB), 127 840 archivos.
Licencia MATLAB: ACTIVA en la máquina del usuario → capturas diferenciales real vs gemelo habilitadas.
Estado: APROBADO por el usuario el 2026-10-16 (v1.1).

---

## 1. Objetivo

Construir un gemelo funcional de MATLAB R2026b cuyo **frontend sea indistinguible** del original para el usuario: al probarlo no debe poder saber si usa MATLAB real o el gemelo.

**Criterio de aceptación final (prueba de ciego):** el usuario pasa 30 minutos ejecutando tareas típicas (comandos en consola, variables, scripts, gráficas, navegación de paneles) y no logra distinguir el gemelo del MATLAB real.

## 2. Definiciones y límites (no negociables)

1. **No existe copia byte a byte.** REA es análisis estático; no regenera binarios ni C++ compilable. El objetivo es paridad funcional/visual verificada por evidencia.
2. **Target único:** toda evidencia REA proviene de `C:\Program Files\MATLAB\R2026b`. No se mezclan releases.
3. **Higiene legal del repo público:** el repo `matlab-web-clone` es público → jamás se commitea contenido derivado de MathWorks (bundles decompilados, módulos reconstruidos, assets gráficos, fuentes). El `.gitignore` actual ya lo protege; se mantiene así.
4. **Assets locales en runtime:** para la fidelidad visual en la máquina del usuario, el backend del clon puede servir iconos/fuentes/CSS **directamente desde la instalación local** (opt-in, configurable, `MATLAB_ROOT`), sin copiarlos al repo.
5. **Evidencia es la fuente de verdad:** ninguna tarea se acepta sin citar `evidence_id` + SHA-256 y pasar su prueba. El ledger de obligaciones REA es el checklist.
6. **Capturas diferenciales autorizadas:** la licencia de MATLAB está activa; se ejecutará MATLAB real SOLO para capturas controladas de comparación (entradas/salidas de comandos). Nunca se modifica la instalación ni se captura contenido protegido; los outputs capturados son datos de prueba.

## 3. Inventario de partida (verificado)

**Gemelo actual (repo):** ~8 300 líneas Python — intérprete `.m` (lexer/parser/interpreter + bibliotecas), `hg_graphics`, 73 tests pasando, SPA frontend (~1 900 líneas), FastAPI. 41 archivos rastreados, commit `f6b11a0`.

**Instalación objetivo (MATLAB base, SIN toolboxes reales):**
- `toolbox\matlab`: 14 087 archivos `.m` (668 MB) — lenguaje y funciones base.
- `toolbox\shared`: 2 648 `.m` (128 MB) — helpers compartidos.
- `bin\win64`: 2.65 GB nativos, 5 179 archivos (`libcef`, `mkl.dll`, `m_lxe.dll`, `handle_graphics.dll`, CGIR…).
- `ui\`: frontends web (jsconsole, webgui, editor…) — evidencia REA ya generada.
- Toolboxes: solo agregados ligeros (comparisons 64 MB, coder 21, deployment 20, classdiagram 13, livecode 12, experiments 11, mdom 9); **simulink es STUB de 5 MB** (no funcional); compiler/stateflow/physmod ~0.

**Conclusión de alcance:** "clonar la instalación" = clonar **MATLAB base** (lenguaje + motor + gráficas + UI web). No hay toolboxes de ingeniería que clonar.

**Evidencia REA disponible (local, no en repo):**
| Fuente | Contenido | Estado |
|---|---|---|
| `rea/reconstructed/` | 469 módulos del Command Window web (jsconsole) con fingerprints | Completo |
| `rea/ui-analysis/` | 6 componentes UI analizados + digests (digest/details en repo) | Completo |
| `backend/rea_ledger.py` | 9 artefactos autenticados, 11 P/Invoke de `libMatlabEngine` | Integrado |
| `rea/reconstruction-obligation-ledger.md` | Obligaciones por SHA por módulo jsconsole | Completo |

**Superficie a cubrir:** de los 14 087 `.m` base, la meta es la superficie observable de uso típico (~1 000–1 500 funciones). Hoy: **265 builtins registrados**.

## 4. Estrategia de paridad (dos vías simultáneas)

**E1 — "Frontend original asistido" (fidelidad máxima, uso local del usuario).**
Cargar los bundles originales desde la instalación local (`ui/jsconsole` primero) apuntados a un backend propio que implemente el protocolo documentado por REA (`mw-mvm/impl/Connection`, endpoints de `mw-messageservice`). Sustituciones funcionales de nativos: `libcef` → navegador del usuario; `mkl` → numpy/BLAS; `m_lxe` → motor `.m` propio.

**E2 — "SPA propia de paridad" (entregable público del repo).**
Evolucionar la SPA del repo hasta la paridad usando las reconstrucciones como referencia de comportamiento (no copia de código MathWorks al repo). Assets visuales servidos desde la instalación local en runtime.

**Oráculo de capturas:** con la licencia activa, por cada comando del set de aceptación se captura el par entrada→salida del MATLAB real y se usa como prueba dorada del gemelo (`docs/acceptance/`).

## 5. Workstreams y asignación

| WS | Alcance | Evidencia base | Asignación |
|---|---|---|---|
| W1 | **Motor `.m`/MVM**: semántica, formato de salida, errores, workspace | jsconsole `mw-mvm/*`; capturas doradas | OpenCode + Codex |
| W2 | **Command Window web**: paridad visual/funcional del prompt y outputs | `rea/reconstructed/` (469 módulos) | Devin (soporte: Gemini) |
| W3 | **Shell web**: toolbar, paneles (Current Folder, Workspace), statusbar, temas | `ui-analysis` | Devin + Codex |
| W4 | **Figuras/gráficas**: ventana de figura, ejes, colormaps, toolbar | `hg_graphics` + capturas | OpenCode |
| W5 | **Protocolo SPA↔motor**: bus equivalente a `mw-mvm/Connection` | jsconsole + `ui-analysis` endpoints | OpenCode |
| W6 | **Verificación continua**: ledger, CI, prueba de ciego, comparaciones lado a lado | Todo lo anterior | OpenCode |
| W7 | **Servicios MATLAB-compatibles**: bus `mw-messageservice`, stub cometd, servicios Current Folder/Workspace/Editor | Evidencia jsconsole + webgui | OpenCode + Codex |
| W8 | **Ejecución asíncrona**: streaming de output, Ctrl+C, cola de comandos | jsconsole `mw-mvm/*` | OpenCode |
| W9 | **Catálogos de paridad**: errores/warnings exactos, formatos numéricos, capturas diferenciales | Capturas doradas | Gemini 3.8 Flash |

Regla de ramas: `ws/<n>-<slug>` por workstream; PR con checklist de evidencia; merge solo con tests verdes.

## 6. Fases, entregables y criterios de salida

- **F0 — Higiene del repo** *(completado en commit F0)*: `LICENSE` (MIT), CI de pytest, excepciones `.gitignore` para digests, `docs/PARITY-PROGRAM.md`, plantillas y work orders, set de aceptación + capturas doradas.
- **F1 — Command Window indistinguible:** prompt, formatos, errores/warnings, colores y tipografía; assets locales; capturas diferenciales vs MATLAB real. *Salida:* capturas lado a lado sin diferencias visibles; set de 20 comandos con salida dorada idéntica.
- **F2 — Shell web básico:** barra superior (tabs), paneles Current Folder y Workspace, statusbar, tema claro/oscuro. *Salida:* checklist de layout contra capturas del webgui real.
- **F3 — Editor y scripts:** resaltado MATLAB, ejecutar selección/archivo, guardar `.m`. *Salida:* los 4 scripts de `scripts/` corren desde el editor con salida idéntica a consola.
- **F4 — Figuras y gráficas:** ventana de figura estilo MATLAB (toolbar, ejes, grid, colormaps), `plot/surf/mesh/fft`. *Salida:* `surface_peaks_3d.m` y `spectral_fft.m` equivalentes a capturas.
- **F5 — Prueba de ciego y pulido:** protocolo de 30 min; registro de diferencias; correcciones. *Salida:* acta "no distingo / distingo en X".

## 7. Contratos de evidencia (para Codex, Devin y Gemini)

```
WO-xx | WS-n | objetivo
Evidencia: ev_<id> (sha256 del artefacto), rutas locales
Entregable: archivos + test
Aceptación: comando de test o captura lado a lado
Límites: (p. ej. "no ejecutar MATLAB; solo capturas controladas")
```

Los JSON de evidencia grandes quedan locales; las IAs consumen: digests pequeños (en repo), ledger de obligaciones (en repo) y capturas doradas (datos, no contenido protegido).

## 8. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Copiar assets/código MathWorks al repo público | Regla 3 + revisión en PR + `.gitignore` |
| `bundle.361.js` no expandido por REA | Recuperación de fuentes dedicada (Wakaru) en W3 |
| Dependencias de servicios del webgui (cometd/login) | E1 incremental: jsconsole y `mw-mvm` primero |
| Uso del MATLAB real | Solo capturas controladas; nunca modificar la instalación |
| Divergencia entre IAs | Un solo repo, ramas por WS, PR revisado, CI obligatoria |

## 9. Próximos pasos inmediatos

1. ~~Copiar plan a `docs/PARITY-PROGRAM.md`~~ *(F0, hecho)*
2. ~~LICENSE + CI + excepciones + plantillas~~ *(F0, hecho)*
3. Emitir WO-01…WO-05 → **hecho en `docs/workorders/`**
4. Ejecutar WO-01 (motor: paridad contra `docs/acceptance/golden-output.txt`).

## 10. Éxito medible (KPIs) y expectativas

**Meta oficial:** "indistinguible en la prueba de ciego sobre el flujo acordado" (no "copia exacta de todo MATLAB").

| KPI | Meta |
|---|---|
| K1: set de aceptación con salida idéntica al MATLAB real | 100% antes de F5 |
| K2: catálogo de errores/warnings comunes con texto exacto | 95% de los 100 más frecuentes |
| K3: capturas lado a lado de UI sin diferencias visibles | 0 diferencias listadas por el usuario |
| K4: suite del repo en CI verde | 100% de PRs |

**Expectativas honestas por fase** (estimaciones): F1 ~85-90% · F2 ~60-70% · F3 ~70% · F4 ~70% · F5 flujo definido probable; flujo libre no garantizable.

**No alcanzable:** paridad con el catálogo completo de MathWorks, regeneración de binarios, "nunca distinguirlo" en cualquier tarea arbitraria.
