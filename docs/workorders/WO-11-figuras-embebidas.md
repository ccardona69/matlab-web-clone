# WO-11 — Figuras embebidas (plot/figure/surf)

## Objetivo

`plot`, `figure`, `bar`, `scatter`, etc. producen una figura web real dentro
del desktop — la pieza más compleja del clon.

## Estado actual

- `figure`/`plot`/`close all` ya responden OK (eval pasa).
- El profesor, al hacer `plot`, abre un **segundo attach MVM** y eventos de
  grupo `UserGroup` (capturado en ronda 1 y 2).

## Apuntes disponibles

- `ml-mirror/_captures/_ronda2/wire-20261016-221912.jsonl` — comandos fig2:
  plot con datos, title/xlabel/ylabel, hold on, legend, figure(2), bar,
  subplot, scatter.
- FALTA COSECHAR EN DETALLE: los canales embedded-figures / graphics que se
  abren con el segundo attach (datos de geometría, renderers).

## Tareas

1. Cosecha profunda del canal de figuras (attach secundario + suscripciones).
2. Decidir renderer propio: el panel de figura JSD espera datos/render
   — evaluar enviar imagen/SVG generada (matplotlib) vs datos MDA.
3. Implementar el segundo attach + publicación de figura.

## Verificación

`plot(1:10)` en el Command Window produce una figura visible en el desktop;
`pytest -q` verde.

## Nota de alcance

Es la WO más grande: puede dividirse (WO-11a solo figura estática renderizada,
WO-11b interactividad/zoom). No bloquea el uso básico del clon para estudios.
