# Análisis REA de las UIs JavaScript de MATLAB R2026b (resto de `ui\`)

Fecha: 2026-10-16 · REA v6.5.0 (skill v42) · Provider: `rea-javascript-application`
Target: `C:\Program Files\MATLAB\R2026b\ui\` (Release 26.2.0.3386108) · Formato: análisis estático inerte (sin ejecución)

## Método

Comando canónico (REA CLI vía `npx -y rea-agents@6.5.0`, cache npm `ad9a3fdbcad992c6`):

```
rea analyze-javascript-application "<ruta-del-componente>" --format json
```

Variantes por presupuesto de recursos:

- `webgui`: `--max-heap-mb 4096 --analysis-timeout-ms 900000`
- Resto: valores por defecto (heap 1024 MiB, timeout 300 s por fuente)

Artefactos generados en este directorio:

| Archivo | Rol |
|---|---|
| `<componente>.json` | Evidencia REA completa (envelope con `normalized_result`) |
| `<componente>.err` | Bitácora de progreso del CLI (fases, sin errores) |
| `ui-components-digest.json` | Digest compacto por componente (stats, cobertura, límites) |
| `ui-components-details.json` | Detalle: namespaces, endpoints, workers, chunks, módulos notables |
| `evidence-integrity.json` | SHA-256 y tamaño de cada archivo de evidencia |
| `analyze-component.ps1` | Runner reproducible del análisis por componente |
| `summarize_analysis.py`, `extract_details.py` | Generadores de digest/detalle |

## Resumen por componente

| Componente | Archivos | JS | Módulos | Hallazgos | Nodos de grafo | Endpoints | Nodos semánticos | ¿Truncado? |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `webgui` | 50 | 32 | 1558 | 7933 | 318 | 17 | 42505 | Sí (presupuesto) |
| `install` | 23 | 15 | 3691 | 12913 | 1236 | 39 | 85 | Sí (presupuesto) |
| `academyinteractions` | 8 | 4 | 1364 | 4154 | 2804 | 12 | 26 | Sí (presupuesto) |
| `help` | 12 | 7 | 979 | 3526 | 745 | 31 | 20039 | Sí (techo 20k/archivo) |
| `desktop-default-plugins` | 5 | 2 | 3093 | 13012 | 9 | 0 | 13 | Sí (presupuesto) |
| `mw-taskbar` | 3 | 2 | 9 | 11 | 17 | 0 | 4381 | No (completo) |

Referencia previa: `jsconsole` (ya integrado al proyecto vía `ev_da7a98bba739ec8565820f30f2b2e2db24add0e9699247d2c0c1365d3933e994`) — 5 archivos, 2 JS, 469 módulos, 1702 hallazgos, 20012 nodos semánticos (mismo techo de truncamiento).

Nota: los módulos `mw-*` / `dijit` / `dojo` se empaquetan dentro de cada aplicación, por lo que los conteos entre componentes se solapan parcialmente.

## Hallazgos por componente

### `webgui` — contenedor principal del escritorio web

- Bundles: `bundle.index.js`, `bundle.index-jsd.js`, `bundle.index-jsd-cr.js`, `bundle.index-mos.js`, `bundle.index-nologin.js`, `bundle.appshell.js`, `bundle.common.js`, `bundle.undocked.js`, `bundle.window.js` y el chunk `361` (`bundle.361.js`, 18 033 270 bytes).
- Grafo: chunk `361`, bootstrap webpack y `source map reference` retenidos.
- Endpoints observados: `actionId`, `actionService`, `contextMenuManager`, `dataService`, `menu`, `settingsService`, `uiBuilder`, `route endpoint`, `value`, `tag`, `icon`, `showText`, etc.
- Storage: `crConfig`.
- Límites clave (13 limitaciones en la evidencia):
  - `bundle.361.js` excede el presupuesto de checkpoint estático ("complete-fact byte budget"): sus hechos no se expandieron como grafo.
  - `bundle.appshell.js`: el análisis semántico no se inició (capacidad reservada a observaciones estáticas).
  - Scripts inline no analizados en `authorization-page.html`, `index-jsd.html`, `undocked-container.html`, `undocked.html`.
  - Parseo `partial` en 12 archivos (esperado en bundles minificados).

### `install` — flujos de instalador, login y add-ons (5 sub-apps)

- Sub-aplicaciones: `addons_ui`, `installer_login`, `install_management_ui`, `product_installer_ui`, `supportsoftwareclient`.
- Namespaces dominantes: `product_installer_ui`, `mw-login`, `mw-remote`, `installer_login`, `addons_ui`; módulos concretos `mw-login/login` y `mw-remote/Remote`.
- Endpoints observados (39): `evergreen.bundle`, `evergreen.loader.skip`, `evergreen.login.skip`, `evergreen.modules.login`, `entitlementid`, `addonType`, `artifactType`, `downloadFolder`, `backend`, `entryPoint`, `dropDownNeverDisabled`, etc.
- Los endpoints `evergreen.*` documentan el canal login/entitlement del cliente de add-ons.

### `help` — navegador de documentación (3 sub-apps)

- Sub-aplicaciones: `helpbrowser` (`bundle.index.js` + `bundle.helpservices.js`), `helpwin` y `richtextdoc`.
- 31 endpoints orientados a widgets de UI (`buttonGroup`, `checkableNode`, `closeMenuOnClick`, `dropDownNeverDisabled`, …).
- El grafo semántico llegó al techo por archivo (20 039 nodos); aplica el mismo perfil de truncamiento aceptado en `jsconsole`.

### `academyinteractions` — paneles de MATLAB Academy

- Bundles: `academy_modules-lib` y `trainer_panel` (+ `academy_grading` con `+connector`).
- Namespaces relevantes: `academy_modules-lib` (191 módulos; `InteractionLoader`, `InteractionMessageQueue`, `AcademyDefaultLayout`, …), `dojo` (170), `mw-menu` (166), `equationrenderercore` (126 — renderizado de ecuaciones LaTeX), `dijit` (124), `mw-dialogs` (48), `mw-mvm` (46), `MW` (35; `MW/uiframework/*`, `MW/window/{CEFController, DialogController, SystemBrowserController}`), `mw-popout`, `lit`, `mw-peermodel`.
- Endpoints (12): `user-mvm`, `open`, `layout`, `isVisible`, `disabled`, `content`, `hasDynamicMenu`, `menu`, `target`, `type`, `displayState`, `origin`.
- El presupuesto de resultado se consumió en la expansión del grafo (2804 nodos): solo 26 nodos semánticos retenidos.

### `desktop-default-plugins` — plugins de escritorio

- Descriptores retenidos: `matlab/resources/extensions.json` (claves `desktopPlugins`, `jsModules`, `jsModulesDebug`) y `generatedModuleDef.json`; manifest del bundle.
- El bundle principal (≈7.7 MB) excedió el presupuesto del padre: los hechos estáticos completos quedaron retenidos en el nodo de archivo, sin expansión de grafo (9 nodos).

### `mw-taskbar` — barra de tareas

- Único componente sin restricciones de recursos: grafo semántico completo (4381 nodos, 4444 relaciones, sin truncamiento).
- 9 módulos; evidencia idónea como muestra 1:1 de la calidad de análisis cuando el presupuesto no se agota.

## Integridad de la evidencia

| Componente | `evidence_id` | SHA-256 del JSON | SHA-256 del artefacto raíz |
|---|---|---|---|
| `webgui` | `ev_da1e2abbbf772ca13bea984414666794c07745b53e66e9b33dcd6fc52df5d6b5` | `0645b373a895fd9d20f27124df490933d069bb45431c5ed50762b1fd656d2299` | `7e6d7ef589dba4972517bc04674fdef5030f6142dc24aa441adfcea43e06d8ed` |
| `install` | `ev_c7703f2a1fb01c980d68851ba41a5817cc36f51766d23228516151cf3ff90022` | `5245036ad9b1c42de801e9ebba93242733839dd1457d0dbe17000a26d991aee9` | `86a4138d65526a8ddee230723ff188de5fbdd109ad9dca0f183bf808cee3b3c8` |
| `academyinteractions` | `ev_c68394c5c1e281d403897d7498add6237826cdf0d1df657d6f32c8ac4df01f25` | `eec4a3c8eef862536dab838e844bdabb66e4ce977c6abc76205e013b16066cd7` | `31a22ae7b2adc79df1b921048f616d000f57a3023ecc9989f74a87771d7db958` |
| `help` | `ev_34a4488159d67de9787b3b4e2192d467e685b3502f3d0f7381de29e2e7597e76` | `53c7f9322a41b4056b6bae48080d26f594800479560d6a46fda2838cfe9c3f54` | `3650eda4c111995e7aae34e9d1290e69c6f49b1915daf50ca1ead8ad06ce2ca2` |
| `desktop-default-plugins` | `ev_5e26e75abdb805b3056f71fd5f4b694ff94b59f17c91725387756ed2c5ed5782` | `dcf376ffa3d660e59a7b1203f562435995a47b4d013dbfc399a9caf9a614d58c` | `d822439995ac287193d76b7e8a241dd26fa3443e93c49758d717fb5fce2809ca` |
| `mw-taskbar` | `ev_76963116617defae75f0ae0a0e09818f10ac5ca4dd13f6c60e18581bbad8d260` | `3ab29e9589532329dadc26c6b7b4e9d5c52301932693a52e18bb65e3692be49f` | `7826be103a01c1ee931df0b01af6d4dab1eb704ccfb3df5f37465e5d63a7d9f0` |

Hashes de todos los artefactos auxiliares en `evidence-integrity.json`.

## Limitaciones globales (válidas para todo el lote)

1. **Sin ejecución**: JavaScript y HTML se parsearon como texto inerte; el bootstrap de los bundles nunca se ejecutó. Las importaciones, entrypoints, endpoints y relaciones estáticas no prueban ejecución en runtime.
2. **Truncamiento por presupuesto**: varios componentes agotaron el presupuesto de resultado del padre antes de expandir todas las relaciones; los hechos quedaron retenidos en el nodo de archivo con la limitación explícita. Un `parse_status: partial` en bundles minificados es el comportamiento esperado (igual que en `jsconsole`).
3. **Cobertura incompleta declarada**: `Graph coverage is incomplete; unavailable facts remain explicit and must not be read as absence.` Los `unknowns` semánticos típicos son `ambiguous-target`, `unknown-value`, `dynamic-call`, `dynamic-property` y `resource-limit`.
4. **HTML inline**: los bloques `<script>` inline de varios HTML (p. ej. `webgui/src/index-jsd.html`) no fueron analizados; sus endpoints/storage no están en la evidencia.

## Próximos pasos sugeridos

1. **Reconstrucción de fuentes** por componente con `rea recover-javascript-sources` (Wakaru), como se hizo con `jsconsole` (469 módulos reconstruidos). Candidatos con más valor: `webgui` (appshell + chunk 361) y `academyinteractions` (equationrenderercore, MW/uiframework).
2. **Ledger de obligaciones** por componente: `rea build-reconstruction-obligation-ledger <evidencia.json> --out ...` para fijar los fingerprints estructurales verificables.
3. **`webgui/bundle.361.js`**: al no expandirse por presupuesto, tratarlo con un flujo dedicado (recuperación de fuentes y split por AST) en lugar de reejecutar el analizador.
4. **Reintentos con presupuestos mayores** (`--max-semantic-nodes`, `--max-semantic-nodes-per-file`) para `academyinteractions` y `desktop-default-plugins` si se requiere su grafo expandido; considerar el costo de tamaño de evidencia.
5. **Registro MCP** (opcional): `npx -y rea-agents@6.5.0 setup --client opencode` + reinicio del cliente, para disponer de las herramientas REA interactivas en lugar del CLI.
