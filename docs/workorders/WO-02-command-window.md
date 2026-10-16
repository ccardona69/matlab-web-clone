# WO-02 | WS-2 | Command Window: paridad visual y funcional

- **Asignada a:** Devin (soporte: Gemini 3.8 Flash)
- **Evidencia:** `rea/reconstructed/` (469 módulos del Command Window web de jsconsole, local) + `rea/reconstruction-obligation-ledger.md` + `docs/acceptance/golden-output.txt` (salidas reales)
- **Objetivo:** que la consola de la SPA (`frontend/`) sea indistinguible del Command Window de MATLAB R2026b: prompt `>> `, eco de comandos, colores (errores en rojo, warnings en naranja), tipografía monoespaciada y espaciado reales, scrollback, autocompletado básico y `clc`/`clear` correctos. Los textos de salida deben coincidir con las capturas doradas (coordinado con WO-01 para los textos; aquí es el render).
- **Entregable:**
  1. Mejoras en `frontend/` (consola) + CSS.
  2. Fuentes/iconos: **servidos en runtime desde la instalación local** vía backend (opt-in, variable `MATLAB_ROOT`), nunca copiados al repo.
  3. `docs/acceptance/ui/command-window-checklist.md` con capturas lado a lado (local, las imágenes no se commitean si derivan de MATLAB; el checklist sí).
- **Aceptación:** para los 20 casos AC-01…AC-20, captura de la consola del gemelo vs captura del MATLAB real sin diferencias visibles en colores, fuente, márgenes ni textos.
- **Límites:** no commitear assets de MathWorks. No tocar el protocolo del bus (eso es WS-5/WS-7).
- **Rama sugerida:** `ws/2-command-window`
