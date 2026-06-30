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
scrapers (idempotentes, con caché y `--desde/--hasta`) → **padrón judicial** (construir/actualizar) → `icia_ensamblado.py` → `validar.py` (QA) → reportes (.docx) → notificación.
```
py 01_Poder_Ejecutivo/scraper_01_dnu_leyes.py --desde 2023-01 --hasta 2026-05   # (cada scraper)
py 03_Poder_Judicial/padron_judicial.py --construir                             # base oficial de jueces
py 03_Poder_Judicial/padron_judicial.py --actualizar                            # aplica altas/bajas del BORA (estimado)
py 03_Poder_Judicial/scraper_05_cobertura_judicial.py --desde 2023-01 --hasta 2026-06  # cobertura: estimado padrón + flujo radar
py 00_Comun/icia_ensamblado.py --desde 2023-01 --hasta 2026-05                  # ensambla -> output/itr_mensual.csv
py 00_Comun/validar.py                                                          # QA: notifica, no bloquea
```
Orquestador mensual: **`correr_mensual.bat`** (Windows) / **`correr_mensual.sh`** (Linux/cloud) corre TODO el pipeline en orden (scrapers → padrón → cobertura → ensamblar → validar → gráficos). **DESDE = 2023-01 (colchón)** para que el suavizado de 12m esté completo al inicio; el índice **se publica desde 2024-01 (gestión Milei) ya suavizado**, vía `icia_ensamblado.py --publicar-desde 2024-01` (calcula con el colchón y recorta la salida). HASTA = mes en curso (provisional).
Núcleo histórico: `06_Historico/correr_nucleo_historico.bat` (corre los scrapers de serie larga --desde 2003 y ensambla) → `itr_nucleo_mensual.py`.

## Convenciones de scrapers
- Interfaz: `--desde AAAA-MM --hasta AAAA-MM`; salida a `output/<archivo>_<timestamp>.csv`; columna `periodo` (AAAA-MM).
- El ensamblador toma SIEMPRE el CSV más nuevo de cada patrón (`_latest`). Los viejos son inertes:
  se conserva solo el último de cada `*_mensual_*.csv`; los anteriores se pueden mover a
  `archivos_borrar/` (carpeta de limpieza, ignorada por git, que el equipo elimina del disco).
- Caches `_cache_*` y snapshots (`_balbcrhis.xls`, `_recaudacion.csv`) → reproducibilidad y corridas offline. No borrar.
- Variables estructurales: forward-fill con columna `stale_meses` (la usa el validador para la frescura).
- ESTADOS (`sin_suavizar`): el ensamblador los PERSISTE por ffill (último valor conocido). Así un estado sin fila nueva (p. ej. "Designación Pdte. BCRA" o "presupuesto aprobado") no se cae de la renormalización ni infla el eje en análisis del mes en curso.

## Mañas de las fuentes (CRÍTICO)
- **IP argentina:** DGSIAF (`dgsiaf-repo.mecon.gob.ar`), BCRA y `datos.jus.gob.ar` bloquean IPs de datacenter/exterior. Correr desde IP AR. `apis.datos.gob.ar/series` (recaudación) sí responde afuera.
- **BCRA:** balance histórico en `balbcrhis.xls` (cols por posición; ver scraper_18). Designación del Presidente: ESTADO mantenido a mano (scraper_17; 0=en comisión/sin Senado, 1=con acuerdo del Senado), con `05_Banco_Central/radar_bcra.py` como ALERTA del BORA para saber cuándo cambiarlo.
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
día hábil escanea la Primera Sección del BORA **por fecha** (`/seccion/primera/AAAAMMDD`) y, en
una sola pasada, detecta **ALTAS** (designaciones de jueces titulares, PEN + acuerdo del Senado)
y **BAJAS** (renuncia / cese / remoción / jubilación / límite de edad / fallecimiento de un juez).
Decide leyendo el CUERPO del decreto (el título del enlace no trae el dato).

- Detección por reglas (sin IA): verbo de designación + juez/magistrado; confianza ALTA si
  además es Decreto y menciona acuerdo del Senado; descarta subrogancias sin Senado. Las bajas
  exigen verbo de salida + juez (ALTA si es Decreto).
- Salida = **dos puentes CSV** (append idempotente, dedup por URL): `output/nombramientos_jueces.csv`
  (altas) y `output/bajas_jueces.csv` (bajas).
- `03_Poder_Judicial/scraper_05_cobertura_judicial.py` lo lee vía `fechas_radar()` (solo
  confianza **ALTA** o `confirmado=sí`) y lo fusiona con las `norma_fecha` del dataset:
  el flujo (`meses_sin_nombramiento`) toma `max(fecha dataset, fecha radar)` → no queda
  congelado entre snapshots (el dataset de magistrados se actualiza ~cada 2 años).
- Gobernanza: el radar es **alerta/insumo**, no el valor publicado. ALTA = candidata firme;
  MEDIA/BAJA quedan para revisión humana. La columna opcional `confirmado` permite forzar
  la confirmación o el descarte humano de una fila.
- Automatización: `.github/workflows/radar_nombramientos.yml` (L–V 09:30 ART) corre los **tres
  radares** (altas y bajas judiciales + Presidencia BCRA) y commitea sus CSV puente. El BORA es
  accesible desde IP del exterior (GitHub Actions). Principio: **fallar avisando**, nunca "sin
  novedades" si no se pudo leer el Boletín. El workflow vive SOLO en la raíz del repo.

## Padrón judicial vivo (03_Poder_Judicial/padron_judicial.py)

Padrón de cargos de jueces (un cargo por fila) que arranca del último snapshot oficial del
dataset de magistrados y el bot actualiza EN VIVO con los eventos del BORA.
- `--construir`: baja el snapshot oficial y arma la base (reconcilia exacto con el dato duro;
  tasas sobre HABILITADOS).
- `--actualizar`: aplica ALTAS (`nombramientos_jueces.csv`) y BAJAS (`bajas_jueces.csv`)
  **posteriores al snapshot** (un evento anterior ya está en el dato oficial → se ignora).
  Matching por tokens + número de juzgado re-leyendo el cuerpo del decreto; lo no mapeable va a
  `output/padron_revision.csv` (revisión humana). Lee los puentes del repo (`ITR_RADAR_CSV_URL`
  para altas; la de bajas se deriva).
- Recalcula titularidad/subrogancia/sin-cobertura como **estimado** → `output/padron_tasas_estimadas.csv`.
  `scraper_05_cobertura_judicial.py` sobreescribe el STOCK del mes corriente con esas tasas
  (`cobertura_estimada=1`) si el archivo existe. Se reconcilia solo con cada snapshot oficial nuevo.

## Radar de la Presidencia del BCRA (05_Banco_Central/radar_bcra.py)

Radar liviano, **solo alerta**: escanea el BORA y avisa designación, renuncia o fin de mandato del
Presidente del BCRA. Distingue **«con acuerdo del Senado»** (única designación VÁLIDA por Carta
Orgánica/Constitución → `valida_constitucional=si`) de **«en comisión»** (sin Senado, no válida).
Evita trampas: Director/Vicepresidente y el boilerplate «Presidente de la Nación». Salida:
`output/bcra_presidencia_eventos.csv`. No toca el valor publicado; un humano confirma y actualiza
el estado de la variable "Designación Pdte. BCRA".
