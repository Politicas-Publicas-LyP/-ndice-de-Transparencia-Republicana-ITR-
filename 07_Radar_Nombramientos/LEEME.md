# ITR — Radar de Nombramientos Judiciales (BORA)

Radar **independiente** del Radar de Desregulación. Cada día hábil revisa la Primera
Sección del Boletín Oficial y detecta los **decretos de designación de jueces titulares**
(nombramiento del Poder Ejecutivo con acuerdo del Senado). Le da **cadencia** al flujo de
nombramientos del eje Judicial del ITR, que de otro modo depende del dataset de
magistrados (que se actualiza ~cada 2 años).

## Por qué un radar aparte
El Radar de Desregulación justamente **descarta** las normas de personal (designaciones).
Este hace lo inverso: las **busca**, pero solo las judiciales y de magistrados titulares.
Se mantiene separado para no superponer operaciones ni bases.

## Qué detecta (y qué no)
Marca como candidata una norma cuyo texto (título + resumen oficial + cuerpo del BORA)
combina: un verbo de designación (desígnase/nómbrase), referencia a **juez/jueza/magistrado**
y, para alta confianza, **acuerdo del Senado** + tipo **Decreto**.
- `ALTA`: Decreto + designa + juez + Senado → designación de titular casi segura.
- `MEDIA`: juez + designa, falta una señal → revisar.
- `BAJA`: señal débil.
Descarta las **subrogancias sin acuerdo del Senado** (reemplazos removibles, no titulares).

> Gobernanza no-IA del ITR: el radar es **alerta/insumo**, no el valor publicado. Las filas
> `ALTA` son candidatas firmes; el valor del flujo se confirma con revisión humana.

## Salida — el puente con el índice
Append idempotente (dedup por URL) a `output/nombramientos_jueces.csv`:
`fecha_deteccion, fecha_publicacion, tipo, organo, confianza, motivo, titulo, url`.
El scraper de Cobertura Judicial (`03_Poder_Judicial/scraper_05_cobertura_judicial.py`)
lee ese CSV y toma `max(fecha dataset, fecha radar)` para el flujo, manteniéndolo fresco
entre snapshots del dataset.

## Cómo lee el BORA (importante)
La Primera Sección se obtiene **por fecha exacta**: `/seccion/primera/AAAAMMDD` (render del
servidor, sin JS). El título del enlace de cada norma es del tipo
`JUSTICIA Decreto 545/2026 DECTO-2026-545-APN-PTE - Nombramiento.` — **no** dice "juez". El
asunto real (`Nómbrase JUEZ DEL JUZGADO…`, `acuerdo prestado por el H. SENADO…`) está en el
**cuerpo** de la ficha. Por eso el radar toma como candidata toda norma de Justicia /
Nombramiento y **decide leyendo el cuerpo**, nunca el título. (Filtrar por "juez" en el título
fue justamente el bug que hacía que no detectara nada.)

## Uso
```
py 07_Radar_Nombramientos\radar_nombramientos.py                       # escanea el BORA de hoy
py 07_Radar_Nombramientos\radar_nombramientos.py --fecha 2026-06-25    # una fecha puntual
py 07_Radar_Nombramientos\radar_nombramientos.py --desde 2026-06-01    # histórico (hasta=hoy)
py 07_Radar_Nombramientos\radar_nombramientos.py --desde 2026-06-01 --hasta 2026-06-25
py 07_Radar_Nombramientos\radar_nombramientos.py --test                # prueba la detección (sin red)
```
Requisitos: `pip install -r 07_Radar_Nombramientos/requirements.txt`

### Modo histórico (corrida única de recuperación)
Lee el BORA **directo por fecha** (sin Vigía): itera día por día de `--desde` a `--hasta`,
salta fines de semana, y para cada edición filtra candidatas y lee el cuerpo. El append es
idempotente (dedup por URL): se puede repetir sin duplicar. Funciona desde IP argentina y
desde GitHub Actions (el BORA responde en ambos).

## Automatización
El workflow vive ÚNICAMENTE en la **raíz** del repo (`.github/workflows/radar_nombramientos.yml`);
GitHub Actions solo ejecuta los que están ahí. No duplicar una copia dentro de esta carpeta.
Corre L–V 09:30 ART, actualiza y commitea el CSV puente. El BORA es accesible desde IP del exterior (GitHub Actions). Principio rector,
igual que el otro radar: **fallar avisando**, nunca decir "sin novedades" si no se pudo leer
el Boletín.
