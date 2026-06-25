# Bitácora — Radar de Nombramientos (BORA)

> **Bitácora del eje.** Registrar acá cada cambio con su fecha. Es la fuente para saber el
> estado de cada variable sin leer el código. Mantener «Pendientes» al día. Antes de editar,
> hacé *pull*; al terminar, *commit + push* (ver AGENTS.md → régimen de trabajo).

_Última revisión: 2026-06-25_

Radar independiente que detecta designaciones de jueces en el BORA y las vuelca al puente output/nombramientos_jueces.csv. Corre en GitHub Actions (L–V).

## Radar de nombramientos  (`radar_nombramientos.py`)
- **Estado:** OK. Lee el BORA por fecha (/seccion/primera/AAAAMMDD), decide por el CUERPO del decreto. Detectó las 46 designaciones de jueces del 25/06/2026 (ALTA).
- **Fuente:** BORA
- **Última actualización:** 2026-06-25
- **Pendientes:** Detector de BAJAS (gemelo, renuncias/ceses); afinar etapa del proceso (pliego→acuerdo→decreto).

## Registro de cambios
- 2026-06-25 — Reescrito: lectura por fecha + detección sobre el cuerpo (arregla el bug del filtro por título).
- 2026-06-25 — Modo histórico por fecha (sin Vigía).
