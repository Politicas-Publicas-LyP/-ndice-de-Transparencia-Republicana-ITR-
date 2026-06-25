# ITR — Guía de arquitectura y operación (AGENTS.md)

Índice de Transparencia Republicana (ITR) — Fundación Libertad y Progreso. Índice mensual
de calidad republicana (0-100), con dato duro, **determinístico y auditable** (sin IA en el
valor publicado). Este documento es la referencia para operar y mantener el proyecto.

## Repositorio y régimen de trabajo (LEER PRIMERO)

- **Fuente única de verdad (remoto):** https://github.com/Politicas-Publicas-LyP/-ndice-de-Transparencia-Republicana-ITR-
  Siempre extraer la última versión de ahí antes de trabajar y subir los cambios al terminar.
- **Trabajo en paralelo:** el índice se desarrolla con varias cuentas/máquinas a la vez. La
  sincronización se hace con **GitHub Desktop** (pull antes de empezar, commit + push al cerrar).
  El repo debe quedar siempre actualizado; ante la duda, `pull` primero para no pisar trabajo ajeno.
- **Estado por variable:** cada carpeta de eje tiene un `BITACORA.md` con el estado, la fuente, la
  última actualización y los pendientes de cada variable. Es el lugar para leer/registrar novedades
  sin tener que abrir el código. Mantenerlo al día con cada cambio.
- **Qué versiona el repo:** código, configuración (`variables.yaml`, `contracts.yaml`), documentos,
  bitácoras y los CSV publicados (`output/*_mensual.csv`, `itr_*.csv`, el puente
  `nombramientos_jueces.csv` y el padrón). Lo regenerable (cachés `output/_cache_*`, `__pycache__`,
  locks) está excluido por `.gitignore`.

## Arquitectura de carpetas
- `00_Comun/` — ensamblador (`icia_ensamblado.py`), gráficos (`graficar_itr.py`), validador
  (`validar.py`), **`variables.yaml`** (fuente única de verdad), `contracts.yaml`, `requirements.txt`.
- `01_Poder_Ejecutivo/` … `05_Banco_Central/` — un scraper por variable (módulos numerados).
- `06_Historico/` — núcleo histórico (anual `itr_nucleo_historico.py`, mensual `itr_nucleo_mensual.py`) y `correr_nucleo_historico.bat`.
- `output/` — CSV generados, caches (`_cache_*`, `_balbcrhis.xls`, `_recaudacion.csv`) y salidas (`itr_mensual.csv`, `itr_nucleo_*.csv`).
- `Documentos/` — reportes y materiales. `Modelos y Administración/` — modelo de estilo LyP y nota metodológica.

## Fuente única de verdad: `variables.yaml`
Define las 18 variables: eje, peso, y por componente `archivo/col/mejor/peor/peso_intra/modo` + flag `nucleo`.
Lo leen el ensamblador y los ensambladores de núcleo. **Para cambiar una variable, anclas o pesos: editar el YAML, no el código.**
- `modo`: `suavizado` (media móvil 12m) · `sin_suavizar` (estado binario/puntual) · `arrastre` (evento puntual con decaimiento asimétrico, p. ej. acceso de prensa).
- `nucleo: true` → entra en el ITR Núcleo (serie larga comparable).

## Pipeline (mensual)
scrapers (idempotentes, con caché y `--desde/--hasta`) → `icia_ensamblado.py` → `validar.py` (QA) → reportes (.docx) → notificación.
```
py 01_Poder_Ejecutivo/scraper_01_dnu_leyes.py --desde 2023-01 --hasta 2026-05   # (cada scraper)
py 00_Comun/icia_ensamblado.py --desde 2023-01 --hasta 2026-05                  # ensambla -> output/itr_mensual.csv
py 00_Comun/validar.py                                                          # QA: notifica, no bloquea
```
Núcleo histórico: `06_Historico/correr_nucleo_historico.bat` (corre los scrapers de serie larga --desde 2003 y ensambla) → `itr_nucleo_mensual.py`.

## Convenciones de scrapers
- Interfaz: `--desde AAAA-MM --hasta AAAA-MM`; salida a `output/<archivo>_<timestamp>.csv`; columna `periodo` (AAAA-MM).
- El ensamblador toma SIEMPRE el CSV más nuevo de cada patrón (`_latest`). Los viejos son inertes.
- Caches `_cache_*` y snapshots (`_balbcrhis.xls`, `_recaudacion.csv`) → reproducibilidad y corridas offline. No borrar.
- Variables estructurales: forward-fill con columna `stale_meses` (la usa el validador para la frescura).

## Mañas de las fuentes (CRÍTICO)
- **IP argentina:** DGSIAF (`dgsiaf-repo.mecon.gob.ar`), BCRA y `datos.jus.gob.ar` bloquean IPs de datacenter/exterior. Correr desde IP AR. `apis.datos.gob.ar/series` (recaudación) sí responde afuera.
- **BCRA:** balance histórico en `balbcrhis.xls` (cols por posición; ver scraper_18). Designación del Presidente: tabla mantenida a mano (scraper_17).
- **HCDN:** el buscador es frágil/lento; InfoLEG (dataset) es robusto.
- **FOPEA:** las categorías vienen en el HTML de cada ficha como `/tag/<slug>/`. Acceso = `restricciones-al-acceso-a-la-informacion-publica`; causas = `acciones-judiciales-civiles-o-penales`.
- **Recaudación (Carta Orgánica):** serie `172.3_TL_RECAION_M_0_0_17` de Series de Tiempo; snapshot en `output/_recaudacion.csv`.
- **OneDrive:** la carpeta sincroniza; al editar archivos puede verse una copia truncada hasta que sincronice. Escribir archivos completos, no parches parciales, si se edita fuera de la app.

## Decisiones firmes
- **Vigía / OpenArg: NO se usan como fuente** del valor publicado (no exponen API JSON anónima; verificado jun-2026).
- **Sin self-host; todo cloud-activable.** Para el deploy, la incógnita abierta es el egress con IP argentina.
- **Human-in-the-loop no negociable:** anclas, pesos, tabla de designación del BCRA, tabla de acreditaciones (acceso de prensa) y toda decisión de diseño.
- **Validación = notificar, no bloquear:** `validar.py` avisa (exit 2 + `output/_alertas_validacion.md`) pero la publicación no se frena; el equipo evalúa.

## Capa de IA (solo exploración, nunca el valor publicado)
Reservada para: reparar scrapers, redactar el informe (voz LyP, skill `lyp-pp`), QA/anomalías y el futuro Radar de eventos institucionales. El número del ITR se calcula solo con conteos determinísticos.

## Radar de Nombramientos Judiciales (07_Radar_Nombramientos)

Radar **independiente** del Radar de Desregulación (no comparten base ni operación). Cada
día hábil escanea la Primera Sección del BORA y detecta **decretos de designación de jueces
titulares** (PEN + acuerdo del Senado). Reusa la lectura del BORA del radar de desregulación
(lista de la 1ra sección + texto completo de cada norma), pero con detección POSITIVA de
designaciones judiciales — lo inverso de `es_norma_de_rrhh`, que las descarta.

- Detección por reglas (sin IA): verbo de designación + juez/magistrado; confianza ALTA si
  además es Decreto y menciona acuerdo del Senado; descarta subrogancias sin Senado.
- Salida = **puente CSV**: `output/nombramientos_jueces.csv` (append idempotente, dedup por URL).
- `03_Poder_Judicial/scraper_05_cobertura_judicial.py` lo lee vía `fechas_radar()` (solo
  confianza **ALTA** o `confirmado=sí`) y lo fusiona con las `norma_fecha` del dataset:
  el flujo (`meses_sin_nombramiento`) toma `max(fecha dataset, fecha radar)` → no queda
  congelado entre snapshots (el dataset de magistrados se actualiza ~cada 2 años).
- Gobernanza: el radar es **alerta/insumo**, no el valor publicado. ALTA = candidata firme;
  MEDIA/BAJA quedan para revisión humana. La columna opcional `confirmado` permite forzar
  la confirmación o el descarte humano de una fila.
- Automatización: `.github/workflows/radar_nombramientos.yml` (L–V 09:30 ART; commitea el
  CSV puente). El BORA es accesible desde IP del exterior (GitHub Actions). Principio:
  **fallar avisando**, nunca "sin novedades" si no se pudo leer el Boletín.
