# Bitácora — Radar de Nombramientos (BORA)

> **Bitácora del eje.** Registrar acá cada cambio con su fecha. Es la fuente para saber el
> estado de cada variable sin leer el código. Mantener «Pendientes» al día. Antes de editar,
> hacé *pull*; al terminar, *commit + push* (ver AGENTS.md → régimen de trabajo).

_Última revisión: 2026-06-25_

Radar independiente que detecta, en una sola pasada por el BORA, ALTAS (designaciones) y BAJAS
(renuncias/ceses/etc.) de jueces, y las vuelca a output/nombramientos_jueces.csv y
output/bajas_jueces.csv. Corre en GitHub Actions (L–V).

## Radar de nombramientos — ALTAS y BAJAS  (`radar_nombramientos.py`)
- **Estado:** OK (test 8/8). Lee el BORA por fecha (/seccion/primera/AAAAMMDD), decide por el
  CUERPO del decreto. ALTAS: designaciones de jueces titulares (detectó las 46 del 25/06/2026).
  BAJAS: renuncia / cese / remoción / jubilación / límite de edad / fallecimiento de un juez
  (verificadas en el BORA: decretos 529, 530/2025, etc.). Salida en dos CSV puente.
- **Fuente:** BORA
- **Última actualización:** 2026-06-25
- **Pendientes:** Afinar la etapa del proceso de altas (pliego → acuerdo → decreto).

## Registro de cambios
- 2026-06-25 — Reescrito: lectura por fecha + detección sobre el cuerpo (arregla el bug del filtro por título).
- 2026-06-25 — Modo histórico por fecha (sin Vigía).
- 2026-06-25 — Integrado el detector de BAJAS (renuncias/ceses) → `bajas_jueces.csv`; el padrón lo lee para liberar cargos.
