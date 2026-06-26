# Bitácora — Común / Ensamblado

> **Bitácora del eje.** Registrar acá cada cambio con su fecha. Es la fuente para saber el
> estado de cada variable sin leer el código. Mantener «Pendientes» al día. Antes de editar,
> hacé *pull*; al terminar, *commit + push* (ver AGENTS.md → régimen de trabajo).

_Última revisión: 2026-06-25_

Motor del índice y configuración transversal.

## Ensamblador  (`icia_ensamblado.py`)
- **Estado:** OK. Lee variables.yaml; anclaje al ideal, suavizado 12m, arrastre y carryover; renormaliza por categoría sobre variables disponibles. Los ESTADOS (`sin_suavizar`) persisten por ffill: no se caen de la renormalización en meses sin fila nueva.
- **Fuente:** output/*_mensual.csv
- **Última actualización:** 2026-06-26
- **Pendientes:** —

## Fuente única de variables  (`variables.yaml`)
- **Estado:** OK. 18 variables con eje/peso/componentes/modo. Pesos macro fijos 30/20/20/15/15.
- **Fuente:** —
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## QA y frescura  (`validar.py + contracts.yaml`)
- **Estado:** OK. Notifica (no bloquea): escribe output/_alertas_validacion.md, exit 2 si hay alertas.
- **Fuente:** —
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Gráficos  (`graficar_itr.py`)
- **Estado:** OK. Consolidado, 5 ejes y núcleo.
- **Fuente:** output/itr_mensual.csv
- **Última actualización:** 2026-06-25
- **Pendientes:** —

## Registro de cambios
- 2026-06-26 — Estados (`sin_suavizar`) ahora persisten por ffill: corrige la inflación de ejes
  en meses parciales cuando un estado no tiene fila nueva (Designación Pdte. BCRA, presupuesto aprobado).
- 2026-06-25 — Override de cobertura ESTIMADA del mes corriente desde el padrón vivo (vía scraper_05).
- 2026-06-25 — Bitácora creada.
