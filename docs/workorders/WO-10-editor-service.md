# WO-10 — Editor de archivos .m funcional

## Objetivo

El Editor del desktop real abre, muestra, edita y guarda archivos `.m` del
disco del usuario — como el MATLAB real (ya abrió `ejemplo1_regresion.m`
durante las pruebas con el connector).

## Estado actual

- `filesystem/listfolder` ya responde con contenido real del disco
  (`backend/e1_bus_services.py`): raíz, cwd, getchildren, exists, watch.
- Falta: servicio de documentos del editor (open/read/save/buffer), y la
  sincronización Editor <-> Current Folder.

## Apuntes disponibles

- Capturas filesystem en `ml-mirror/_captures/` y el mapa de canales en
  `docs/acceptance/ui/e1-request-map.md` (iteración 3).
- FALTA COSECHAR: abrir un `.m` en el editor real y grabar los canales
  `/matlab/editor*`, `/matlab/editorservice*`, `FileDataServiceChannel`.

## Tareas

1. Cosechar wire del Editor (abrir/guardar `.m` en sesión JSD real).
2. Implementar servicio de documentos (leer archivo real del disco vía
   filesystem backend ya existente).
3. Guardar: escritura al disco (cuidado: rutas del usuario).

## Verificación

Editor abre `ejemplo1_regresion.m` con contenido correcto; `pytest -q` verde.
