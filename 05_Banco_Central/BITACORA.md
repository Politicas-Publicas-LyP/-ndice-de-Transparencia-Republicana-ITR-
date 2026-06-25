# Bitácora — Banco Central

> **Bitácora del eje.** Registrar acá cada cambio con su fecha. Es la fuente para saber el
> estado de cada variable sin leer el código. Mantener «Pendientes» al día. Antes de editar,
> hacé *pull*; al terminar, *commit + push* (ver AGENTS.md → régimen de trabajo).

_Última revisión: 2026-06-25_

Eje 15%.

## Financiamiento al Tesoro  (`scraper_18_bcra_financiamiento.py`)
- **Estado:** OK.
- **Fuente:** BCRA (balance)
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Letras intransferibles  (`scraper_18_bcra_balance.py`)
- **Estado:** OK.
- **Fuente:** BCRA (balance)
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Respeto de la Carta Orgánica (art. 20)  (`scraper_21_carta_organica.py`)
- **Estado:** OK. Recaudación vía API de Series de Tiempo.
- **Fuente:** BCRA + apis.datos.gob.ar/series
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Designación del Presidente del BCRA  (`scraper_17_bcra_designacion.py`)
- **Estado:** OK como variable; en jun-2026 quedó sin dato del mes (no hubo nombramiento).
- **Fuente:** BORA / decreto PEN + acuerdo del Senado
- **Última actualización:** 2026-06-25
- **Pendientes:** Detector en el BORA del decreto de designación del Presidente del BCRA (mismo mecanismo que el de jueces).

## Registro de cambios
- 2026-06-25 — Bitácora creada.
- 2026-06-25 — Propuesto detector BORA para la designación del Presidente del BCRA (ver Documento de Mejoras, sección E).
