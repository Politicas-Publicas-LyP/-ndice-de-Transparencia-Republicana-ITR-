# Bitácora — Poder Ejecutivo

> **Bitácora del eje.** Registrar acá cada cambio con su fecha. Es la fuente para saber el
> estado de cada variable sin leer el código. Mantener «Pendientes» al día. Antes de editar,
> hacé *pull*; al terminar, *commit + push* (ver AGENTS.md → régimen de trabajo).

_Última revisión: 2026-06-25_

Eje 30%.

## DNU vs Leyes  (`scraper_01_dnu_leyes.py`)
- **Estado:** OK.
- **Fuente:** InfoLeg
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Discrecionalidad presupuestaria  (`scraper_04_discrecionalidad.py`)
- **Estado:** OK. Ojo: en mes en curso el flujo parcial distorsiona (ver muestra de junio).
- **Fuente:** DGSIAF (IP AR)
- **Última actualización:** 2026-06-25
- **Pendientes:** Marcar/avisar cuando el mes está incompleto.

## Transparencia (AIP)  (`scraper_11_transparencia_v2.py`)
- **Estado:** OK.
- **Fuente:** AAIP
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## ATN (federalismo)  (`scraper_16_atn.py`)
- **Estado:** OK. El índice usa el **share MENSUAL** (`atn_share_mensual`, crédito mensual DGSIAF),
  no el anual: refleja la discrecionalidad mes a mes. Columnas extra: `atn_share` (anual, referencia)
  y `atn_var_mom_pp` (variación vs mes anterior). **Inmutabilidad de publicación**: los meses
  cerrados quedan fijos en `output/atn_obs_mensual.csv` (versionado) y no se recalculan en corridas
  futuras. **Fallback** al share anual donde no hay mensual (años viejos) → no rompe el núcleo.
  Caché solo de años CERRADOS (el año en curso se recalcula).
- **Fuente:** DGSIAF crédito mensual y anual
- **Última actualización:** 2026-06-29
- **Pendientes:** ATN histórico para llegar a Macri (parqueado).

## Registro de cambios
- 2026-06-25 — Bitácora creada.
