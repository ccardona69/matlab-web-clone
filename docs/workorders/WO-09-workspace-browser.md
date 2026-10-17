# WO-09 — Workspace browser con variables reales

## Objetivo

El panel Workspace del desktop real muestra las variables del `mvm_engine`
(nombre, valor, clase, tamaño) y se actualiza tras cada comando — como hace el
MATLAB real.

## Estado actual

- El panel renderiza vacío: los servicios mf.zero / matlabdatamodel responden
  shapes válidos pero sin contenido (suficiente para boot, no para datos).
- El motor (`backend/mvm_engine.py`) sí mantiene el workspace real: ver
  `GET /api/mvm/workspace` y `GET /api/mvm/variable/{name}` ya implementados.

## Apuntes disponibles

- `ml-mirror/_captures/wire-20261016-220151.jsonl` — comandos `who`, `whos`,
  `clear`, asignaciones (salida de Command Window).
- FALTA COSECHAR: el canal de datos del panel Workspace
  (`/matlab/matlabdatamodel/*`, `*/datamodel/*`, eventos de cambio de variable).
  El profesor debe correr con el desktop JSD abierto en el panel Workspace.

## Tareas

1. Cosechar wire del panel Workspace (sesión JSD: abrir panel, crear vars).
2. Implementar el servicio datamodel: lista de variables, cambios
   (create/update/delete) publicados como eventos.
3. Serialización MDA de valores (shape/type/preview) — reusa el trabajo de
   `<RICH_OUTPUT>` de WO-08.

## Verificación

Panel Workspace del desktop muestra `A`, `a`, `ans` tras los comandos del
curriculum; `pytest -q` sigue verde.
