# WO-03 | WS-3 | Shell web: layout estiloMATLAB R2026b

- **Asignada a:** Devin + Codex
- **Evidencia:** `rea/ui-analysis/` (webgui, desktop-default-plugins, mw-taskbar; digests en repo: `ui-components-digest.json`, `ui-components-details.json`) + capturas controladas del MATLAB real
- **Objetivo:** layout del escritorio web equivalente a R2026b:
  1. Barra superior con tabs y ribbon simplificado (HOME: New Script, Open, Save, Run; botones a la derecha del layout real).
  2. Panel **Current Folder** (izquierda superior): tabla NOMBRE / ÚLTIMA MODIFICACIÓN con navegación y breadcrumb.
  3. Panel **Workspace** (izquierda inferior): NOMBRE / VALOR con refresco tras cada comando.
  4. **Statusbar** inferior + placeholder para barra de comandos de figuras.
  5. Tema claro/oscuro conmutables (por defecto como R2026b).
  6. Paneles redimensionables (dividers arrastrables) y colapsables.
- **Entregable:** `frontend/` (HTML/CSS/JS) + `docs/acceptance/ui/shell-checklist.md` con la lista de comprobación visual contra capturas del webgui real.
- **Aceptación:** checklist al 100% "sin diferencias visibles" para: proporciones de paneles, colores, tipografía, iconografía (assets locales opt-in) y comportamiento de resize.
- **Límites:** no copiar CSS/HTML/bundles de MathWorks al repo; iconos y fuentes solo en runtime desde la instalación local.
- **Rama sugerida:** `ws/3-shell-layout`
