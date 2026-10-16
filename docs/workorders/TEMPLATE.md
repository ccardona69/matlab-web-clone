# Template de Work Order

Copia este archivo como `docs/workorders/WO-XX-<slug>.md` y complétalo.

```markdown
# WO-XX | WS-n | <título>

- **Asignada a:** <OpenCode | Codex | Devin | Gemini>
- **Evidencia:** ev_<id> (sha256 del artefacto) + rutas locales
- **Objetivo:** <qué debe lograrse, medible>
- **Entregable:** <archivos del repo + tests>
- **Aceptación:** <comando de test o captura lado a lado>
- **Límites:** <p. ej. "no ejecutar MATLAB; solo capturas controladas">
- **Rama sugerida:** ws/<n>-<slug>
```

Reglas:
1. Sin evidencia citada no hay tarea.
2. Ningún PR se fusiona sin tests verdes en CI.
3. No commitear contenido derivado de MathWorks (assets, bundles, fuentes decompiladas).
4. Si una tarea depende de otra IA, declararlo en el objetivo.
