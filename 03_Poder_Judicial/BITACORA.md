# Bitácora — Poder Judicial

> **Bitácora del eje.** Registrar acá cada cambio con su fecha. Es la fuente para saber el
> estado de cada variable sin leer el código. Mantener «Pendientes» al día. Antes de editar,
> hacé *pull*; al terminar, *commit + push* (ver AGENTS.md → régimen de trabajo).

_Última revisión: 2026-06-25_

Eje 20%. Cobertura = independencia (titularidad) + funcional (vacantes sin cubrir) + flujo (nombramientos).

## Cobertura e independencia judicial  (`scraper_05_cobertura_judicial.py`)
- **Estado:** OK. STOCK del snapshot oficial + FLUJO vía radar (meses sin nombramiento) + STOCK ESTIMADO del mes corriente desde el padrón vivo.
- **Fuente:** datos.jus (IP AR); puente nombramientos vía repo
- **Última actualización:** 2026-06-25
- **Pendientes:** Reconciliar al salir snapshot oficial nuevo.

## Padrón judicial vivo  (`padron_judicial.py`)
- **Estado:** NUEVO y OK. --construir (base oficial, reconcilia exacto) y --actualizar (aplica altas del radar; 46 designaciones de jun-2026 mapeadas, 0 a revisión).
- **Fuente:** datos.jus + nombramientos_jueces.csv
- **Última actualización:** 2026-06-25
- **Pendientes:** Detector de BAJAS (renuncias/ceses → bajas_jueces.csv); luego enchufarlo.

## Desempeño de la Corte (CSJN)  (`scraper_06_resolucion_csjn.py`)
- **Estado:** OK.
- **Fuente:** CSJN
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Integridad (secundaria)  (`scraper_10_integridad.py`)
- **Estado:** Secundaria / no pondera en el valor.
- **Fuente:** OA
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Registro de cambios
- 2026-06-25 — Padrón judicial vivo creado y calibrado (matching por tokens+número; sinónimo CABA; parser del cuerpo del BORA).
- 2026-06-25 — Cobertura: override de STOCK estimado del mes corriente.
- 2026-06-25 — Verificado que las renuncias/ceses de jueces existen en el BORA (decretos 529/2025, 530/2025, etc.).
