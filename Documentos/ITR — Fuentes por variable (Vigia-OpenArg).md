# ITR — Fuentes de datos por variable: Vigía / OpenArg y fuentes primarias

**Departamento de Políticas Públicas — Fundación Libertad y Progreso**
Plan de fuentes duras, verificables y reproducibles para cada variable del índice, y evaluación de si **Vigía** u **OpenArg** pueden alimentarla **sin pasar por la capa de IA**.

---

## Principio rector (no negociable)
El valor publicado de cada variable se calcula con **conteos determinísticos / SQL / campos estructurados**, nunca con juicios de IA. La capa "a quién afecta" (resúmenes IA) es solo para exploración. Cada variable se versiona como pipeline: **fuente → query → transformación → valor**, con snapshot y fecha de corte.

## Estado de verificación de las plataformas

**OpenArg — endpoints reales pero HOSTEADO DETRÁS DE LOGIN (VERIFICADO de primera mano, junio 2026).** `openarg.org/api/v1/sandbox/tables` existe pero redirige a `/login?callbackUrl=…` (Google); la URL de callback filtra el host interno (`…:3000`). El sitio público es el producto de chat-IA, también logueado. → **No hay API anónima pública**; depender de él exige cuenta y, en el mejor caso, API keys (a confirmar logueado). La descripción de abajo es del README/self-host, no del deploy gestionado anónimo. Endpoints de dato (sin IA):
- `POST /api/v1/sandbox/query` — SQL de **solo lectura** sobre tablas cacheadas → COUNT/series exactos y auditables. **Usar este para el valor publicado.**
- `GET /api/v1/sandbox/tables` — lista de tablas cacheadas.
- `GET /api/v1/transparency/*` — presupuesto y DDJJ.
- `GET /api/v1/datasets/` , `/datasets/{id}/download` — dataset crudo (presigned S3).
- Conectores de dato: **BCRA**, **Series de Tiempo** (apis.datos.gob.ar/series, 30.000+), CKAN (3.000+ datasets, 20 portales), DDJJ, Staff (HCDN+Senado), Georef, Argentina Datos.
- **EVITAR para el valor publicado:** `query/smart` y `sandbox/ask` (NL2SQL) → usan Bedrock/Claude (IA + costo).

**Vigía — datos y arquitectura CONFIRMADOS; SIN API JSON pública (VERIFICADO, junio 2026).**
- FastAPI en `:8000`, **modo demo abierto** (`AUTH_ENABLED=false`). Feed/buscador/stats públicos sin login.
- Ingesta CONFIRMADA: **BORA 1ª y 2ª, InfoLEG, HCDN (proyectos/movimientos/dictámenes), Comisión Bicameral de DNU, BCRA Com."A", consultas públicas** (533.000+ normas).
- El **`resumen_ia` es un campo separado y OFF por default** → los campos estructurales (tipo de norma, fecha, organismo, sector, estado bicameral) **no dependen de la IA**.
- **VERIFICADO de primera mano (inspección de red en navegador, junio 2026):** el deploy en vivo `vigia.openarg.org` **no expone API JSON de datos** y, además, **`/feed` y `/search` ahora exigen login** (redirigen a `/auth/signin?callbackUrl=…`); la "demo pública sin cuenta" del README NO está activa. De todas las peticiones, la única `/api/...` es `/api/auth/session` (NextAuth, autenticación — no datos). El resto son chunks `/_next/static/...`, fuentes y payloads `?_rsc=` (React Server Components): los datos se renderizan server-side, detrás de login, sin REST/JSON consumible. La API FastAPI (`:8000`) solo corre en el deploy interno (lo confirma el `docker compose`: api :8000 / web :3000), no publicada. → **Sin self-host, Vigía NO es consumible como fuente del valor publicado** (solo quedaría loguearse y parsear RSC: frágil, requiere cuenta, zona gris de ToS — descartado). Para datos en la nube se usa OpenArg; PENDIENTE verificar que OpenArg tenga un host público llamable (no solo el repo).

> **Nota de contexto:** el ITR ya tiene **scrapers propios determinísticos** contra las fuentes primarias para casi todas estas variables. Vigía/OpenArg se evalúan como (a) alternativa que **reduce fragilidad** (sobre todo el scraping de HCDN) y (b) **backend de datos en la nube** que, self-hosteado, resolvería de paso el problema de reproducibilidad y el de automatización con IP argentina.

---

## Fichas por variable

### EJECUTIVO (35%)

**1. DNU vs. leyes**
1. *Dato:* cuota de DNU sobre actos con rango legislativo = DNU / (DNU + leyes), ventana 12m. Unidad: ratio 0–1.
2. *Vigía/OpenArg:* **Vigía SÍ** — Tracker DNU + feed normativo; el conteo por **tipo de norma** es campo estructural (no IA). Fuente subyacente: BORA 1ª + InfoLEG + Bicameral DNU. **Endpoint JSON A-VERIFICAR.**
3. *Primaria (ya en uso):* InfoLEG (dataset normativa nacional, campo `clase_norma`) — `scraper_01_dnu_leyes.py`. **CONFIRMADO.**
4. *Facilidad/costo:* alta. API pública de Vigía (gratis) o nuestro scraper InfoLEG (gratis).
5. *Reproducibilidad:* snapshot del dataset InfoLEG + fecha de corte; si Vigía, guardar la respuesta JSON datada. Query versionada (definición de `clase_norma`).
   → **ALTO ROI, baja fricción.** Recomendado migrar a Vigía si confirma endpoint; si no, el scraper propio ya cumple.

**2. Discrecionalidad presupuestaria**
1. *Dato:* (a) ¿presupuesto aprobado por el Congreso? (binario) + (b) modificaciones por decreto (DA/DNU) en 12m, o reasignaciones sobre umbral. Unidad: flag + conteo/share.
2. *OpenArg:* **PARCIAL/A-VERIFICAR** — `transparency/*` (presupuesto) + `sandbox/query` sobre tablas de presupuesto. Hay que correr `sandbox/tables` para ver qué granularidad de crédito/modificaciones está cacheada.
3. *Primaria (ya en uso):* DGSIAF / Presupuesto Abierto + OPC (modificaciones) — `scraper_04_discrecionalidad.py`. **CONFIRMADO.**
4. *Facilidad/costo:* media. OpenArg `sandbox/query` daría el número auditable si la tabla está; si no, DGSIAF directo.
5. *Reproducibilidad:* snapshot DGSIAF anual + SQL versionado.
   → **A-VERIFICAR** tablas presupuestarias en `sandbox/tables`.

**3. Transparencia activa (AAIP)**
1. *Dato:* pedidos de acceso a la información respondidos en plazo / solicitados. Unidad: ratio.
2. *Vigía/OpenArg:* **NO (GAP).** Posible vía CKAN si OpenArg indexa el portal de Justicia (A-VERIFICAR), pero no garantizado.
3. *Primaria (ya en uso):* AAIP — microdato "Solicitudes de acceso a la información pública" (`sip.csv`) en datos.jus.gob.ar — `scraper_11_transparencia_v2.py`. **CONFIRMADO.**
4. *Facilidad/costo:* alta (CSV CKAN, gratis).
5. *Reproducibilidad:* snapshot del CSV + fecha.
   → **GAP en Vigía/OpenArg; resuelto con scraper propio.**

### LEGISLATIVO (25%)

**4. Eficacia de control (pedidos de informe / art. 101)**
1. *Dato:* cumplimiento del art. 101 CN (concurrencias del Jefe de Gabinete) o tasa de respuesta a pedidos de informe. Unidad: ratio 12m.
2. *Vigía:* **PARCIAL** — HCDN (proyectos/dictámenes) permite contar **pedidos de informe presentados** (tipo de proyecto, campo estructural). Pero la **respuesta/cumplimiento del Ejecutivo no está en HCDN.** **Endpoint A-VERIFICAR.**
3. *Primaria (ya en uso):* HCDN + Senado/JGM (concurrencias) — `scraper_03_eficacia_control.py` (+ suplemento JGM). **CONFIRMADO.**
4. *Facilidad/costo:* media.
5. *Reproducibilidad:* snapshot + query versionada.
   → Vigía cubre el numerador de "pedidos presentados"; la "respuesta" necesita Senado/JGM aparte.

**5. Calidad normativa**
1. *Dato:* leyes sustantivas vs. proyectos simbólicos (declaraciones/resoluciones/comunicaciones); o leyes por sesión. Unidad: ratio.
2. *Vigía:* **SÍ** — HCDN (proyectos por tipo) + InfoLEG (leyes), conteo determinístico por **tipo de proyecto** (campo estructural). **Endpoint A-VERIFICAR.**
3. *Primaria (ya en uso):* InfoLEG + buscador HCDN — `scraper_02_calidad_normativa.py` + `scraper_14_sesiones.py`. **CONFIRMADO** (el buscador HCDN es frágil).
4. *Facilidad/costo:* alta vía Vigía.
5. *Reproducibilidad:* snapshot + query.
   → **ALTO ROI: Vigía reemplazaría el scraping frágil de HCDN** que hoy nos da problemas. Recomendado si confirma endpoint.

### JUDICIAL (25%)

**6. Integridad pública**
1. *Dato:* (en el ITR se concluyó que **no existe dato duro, periódico y automatizable** de celeridad/condena de causas de corrupción; la variable se descartó y su peso se redistribuyó).
2. *Vigía/OpenArg:* **NO (GAP).** OpenArg DDJJ mide cumplimiento de declaraciones patrimoniales (prevención), no integridad judicial.
3. *Primaria:* sin fuente dura limpia (ver Documento de Mejoras del ITR).
4–5. → **GAP confirmado.** Opción a validar: usar el conector **DDJJ de OpenArg** (tasa de presentación de declaraciones juradas, dato duro) como proxy de *integridad/transparencia patrimonial*, distinto de "integridad judicial".

**7. Celeridad en conflictos de competencia**
1. *Dato:* días de resolución de la competencia originaria / mediana de días de fallos CSJN. Unidad: días.
2. *Vigía/OpenArg:* **NO (GAP).**
3. *Primaria (ya en uso):* anuarios/estadísticas CSJN — `scraper_06_resolucion_csjn.py`. **CONFIRMADO** (dato anual/estructural).
4–5. → **GAP en Vigía/OpenArg; scraper propio CSJN.**

### PRENSA INSTITUCIONAL (15%)

**8. Escrutinio al poder**
1. *Dato:* conferencias de prensa con preguntas libres vs. cadenas nacionales. Unidad: ratio.
2. *Vigía/OpenArg:* **NO (GAP).**
3. *Primaria (ya en uso):* Casa Rosada — `scraper_07_escrutinio.py`. **CONFIRMADO.**
4–5. → **GAP; scraper propio.**

### NUEVAS VARIABLES

**9. Independencia del BCRA** *(definición operativa a validar)*
1. *Dato (propuesto, ya implementado en el ITR):* combinación de
   - (i) **financiamiento monetario al Tesoro** = adelantos transitorios (+ transferencias de utilidades) / base monetaria;
   - (ii) **letras intransferibles** / activo del BCRA;
   - (iii) **designación del Presidente del BCRA** con acuerdo del Senado vs. en comisión (binaria).
2. *OpenArg:* **PARCIAL/A-VERIFICAR** — conector **BCRA** + **Series de Tiempo** (apis.datos.gob.ar/series) exponen base monetaria, reservas y, vía `sandbox/query`, series del sector público; hay que confirmar el **id de serie** de "adelantos transitorios / financiamiento al sector público". Las **letras intransferibles** (balance) y la **designación** NO están → fuente propia.
3. *Primaria (ya en uso):* BCRA `balbcrhis.xls` (balance, saldos a fin de mes) — `scraper_18_bcra_balance.py`; designación — `scraper_17_bcra_designacion.py` (tabla mantenida). **CONFIRMADO.**
4. *Facilidad/costo:* media. OpenArg `sandbox/query` sobre Series BCRA = auditable y en la nube; el balance y la designación quedan con fuente propia.
5. *Reproducibilidad:* snapshot de la serie (id + rango + fecha) o del `balbcrhis.xls`.
   → **A-VERIFICAR** el id de serie de adelantos/financiamiento en OpenArg; el resto ya resuelto.

**10. Calidad de prensa** *(definición operativa A DEFINIR — pregunta abierta)*
1. *Dato:* depende de qué se entienda por "calidad de prensa". Opciones de **dato duro**:
   - **Ambiente/libertad de prensa:** causas judiciales contra periodistas (FOPEA) + intensidad de pauta oficial + tamaño del aparato de medios estatales (DGSIAF) — *ya implementadas en el ITR* (`scraper_13`, `scraper_08`, `scraper_20`).
   - **Pluralismo / concentración de pauta:** dataset de pauta por medio — **dato congelado en 2022, inviable** para serie actual.
   - **"Calidad periodística" en sí:** no es medible con dato duro reproducible (requeriría percepción/curaduría → viola el principio rector).
2. *Vigía/OpenArg:* **NO (GAP).**
3–5. → **Necesita definición operativa.** Recomendación: definir "calidad/ambiente de prensa" con los **proxies duros ya construidos** (causas contra periodistas + pauta + medios estatales) y **no** con índices de percepción (RSF, Freedom House).

---

## GAPs (no cubiertos por Vigía ni OpenArg) → fuente propia
- **Transparencia AAIP** → AAIP/datos.jus (`sip.csv`). Resuelto.
- **Judicial (integridad y celeridad)** → CSJN; integridad sin dato duro (descartada). Resuelto/diferido.
- **Prensa (escrutinio y calidad)** → Casa Rosada, FOPEA, DGSIAF. Resuelto (calidad a definir).

## Recomendaciones
1. **Migrar a Vigía las variables normativo-legislativas** (DNU/leyes, calidad normativa, pedidos de informe) **si confirma endpoints JSON** — sobre todo para **eliminar el scraping frágil de HCDN**. Alto ROI.
2. **Usar OpenArg `sandbox/query` (SQL determinístico)** para BCRA/series y presupuesto; **nunca** `query/smart` ni `sandbox/ask` (IA) para el valor publicado.
3. **Self-host de Vigía + OpenArg en un VPS** (MIT lo permite): resuelve a la vez (a) reproducibilidad ante cambios de terceros, (b) el problema de **automatización con IP argentina** que quedó parqueado — el VPS ingesta las fuentes AR y el índice consulta su Postgres/API. Dejar los sitios públicos solo para exploración.
4. **GAPs (AAIP, Judicial, Prensa):** mantener scrapers propios; no forzar Vigía.
5. **Reproducibilidad:** por cada variable, guardar en git: fuente (URL/endpoint), query/SQL versionado, snapshot del insumo y fecha de corte.

## A-VERIFICAR (pendiente, requiere correr/consultar)
- Endpoints JSON exactos de Vigía (`/openapi.json` self-host) para: tipo de norma, proyectos por tipo, tracker DNU.
- En OpenArg `sandbox/tables`: qué tablas de **presupuesto/crédito** y qué **series BCRA** (id de adelantos transitorios / financiamiento al sector público) están cacheadas.
- Si CKAN de OpenArg indexa el portal de Justicia (AAIP `sip.csv`) — sería un bonus.

## Preguntas para decidir (tuyas)
1. **Definición de "independencia del BCRA":** ¿confirmás la combinación (financiamiento + letras + designación) o querés otra ponderación/variable?
2. **Definición de "calidad de prensa":** ¿ambiente/libertad (proxies duros que ya tenemos) o pluralismo (dato congelado)? — definir para no caer en percepción.
3. **API pública vs self-host:** ¿vamos a self-hostear Vigía/OpenArg (recomendado, resuelve reproducibilidad + automatización) o consumimos sus APIs públicas?
4. **Migración HCDN→Vigía:** ¿priorizamos confirmar los endpoints de Vigía para reemplazar el scraper frágil de HCDN?

---

## Decisiones y diseño — ronda 2 (junio 2026)

**Arquitectura: sin self-host → consumir APIs públicas en la nube.**
- OpenArg: API pública CONFIRMADA → usar `sandbox/query` (SQL determinístico) y `transparency/*`; nunca `query/smart`/`sandbox/ask` (IA).
- Vigía: **el sitio público sirve la WEB (Next.js :3000); la API JSON no aparece en paths obvios** (`/openapi.json`, `/api/docs` → 404/vacío). RIESGO para "consumir API sin self-host". **Acción pendiente (usuario):** abrir `vigia.openarg.org/feed` → F12 → Network → Fetch/XHR → identificar si hay una API JSON pública y su URL. Si no la hay: seguir con scrapers propios (InfoLEG es robusto; lo frágil es solo el buscador HCDN) o reconsiderar self-host solo para Vigía.
- GAPs (AAIP, CSJN, Casa Rosada, balance BCRA, DGSIAF): no cubiertos por las APIs → siguen necesitando egress argentino; pieza cloud = proxy/función en región AR.

**Prensa → se renombra el eje "Libertad de Prensa".** Se decide NO medir pluralismo ideológico ni concentración de propiedad (subjetivo / no institucional desde la mirada liberal: la concentración privada no es per se un problema y penalizarla invitaría a una lógica regulatoria antiliberal). El eje mide la RELACIÓN ESTADO–PRENSA con dato duro.

**Nueva variable: "Acceso de la prensa"** (sub-variable de Libertad de Prensa), combina dos componentes:
1. *Restricciones (evento):* event-count del Monitoreo FOPEA, categoría restricción de acceso/obstrucción a la cobertura, 12m, negativo (reúsa el scraper FOPEA; A-VERIFICAR que la taxonomía tenga la categoría).
2. *Acreditaciones/sala (estructural):* flag graduado del régimen de acceso en Casa Rosada — 1,0 sala+acreditaciones+conferencias / 0,5 restricción parcial 
---

## Decisión de arquitectura (junio 2026): Opción 1 — scrapers propios en la nube

Tras verificar de primera mano que **ni Vigía ni OpenArg exponen una API JSON anónima** (ambos hosteados detrás de login), se descarta depender de esas plataformas para el valor publicado. Arquitectura elegida:

- **Mantener los scrapers determinísticos propios** del ITR (ya construidos, auditables, reproducibles) como única fuente del valor publicado.
- **Ejecución cloud-activable** (runner en la nube, p. ej. GitHub Actions) + **proxy/egress liviano en región AR** para las fuentes de gobierno que bloquean IP extranjera (DGSIAF, BCRA, datos.jus, AAIP, CSJN, Casa Rosada). Es "cloud-activable", no self-host del stack.
- OpenArg queda como posible complemento NO crítico, **solo si emite API keys** para uso programático (en revisión por el usuario). No bloquea la arquitectura.

PENDIENTE: diseñar el runner cloud + proxy AR (lista de fuentes que requieren egress AR, mecanismo de snapshot datado por variable para reproducibilidad).

### Cierre OpenArg (junio 2026): descartado como backend del índice
Se verificó (cuenta logueada) que OpenArg **sí emite API keys** y el host real es `api.openarg.org`. Pero:
- **Cuota free beta: 2 consultas/minuto, 5 consultas/día** → inviable para alimentar un índice de ~18 variables con series históricas.
- El endpoint documentado en el ejemplo es `/api/v1/ask` (capa de IA / NL2SQL), que se descarta para el valor publicado por no determinístico.
→ **OpenArg queda fuera** como fuente del ITR (incluso como complemento). Revisable solo si hubiera un plan con cuota alta + acceso al endpoint `sandbox/query` determinístico. Confirma la **Opción 1** (scrapers propios en la nube + proxy AR) como arquitectura.

---

## Estado de implementación de las 2 variables nuevas (junio 2026) — CONSTRUIDAS

**Prensa → ahora 5 variables** (pesos intra relativos 6/5/4/4/**4**, ajustables; el sub-índice renormaliza):
- **Acceso de la prensa** — `04_Prensa_Institucional/scraper_22_acceso_prensa.py`. Combina:
  - `acceso_estructural` (1,0/0,5/0,0; tabla mantenida ACREDITACIONES; **NO_SUAVIZAR**) → ancla 1,0→100 ; 0,0→0 (peso .5).
  - `restricciones_12m` (event-count FOPEA, slug+keywords) → ancla 0→100 ; 10→0 (peso .5).
  - Salida: `acceso_prensa_mensual_*.csv`.

**Banco Central → ahora 4 variables** (pesos intra 6/5/4/**5**, ajustables):
- **Respeto Carta Orgánica** — `05_Banco_Central/scraper_21_carta_organica.py`. `exceso = max(adelantos/(0,12·base+0,10·recaudación_12m) − 1, 0)` → ancla 0,0→100 (dentro de la ley) ; 0,5→0 (excede el tope 50% = colapso). Reutiliza el balance del módulo 18; recaudación por CSV local o Series de Tiempo. Salida: `carta_organica_mensual_*.csv`.

Integradas en `00_Comun/icia_ensamblado.py` (REG + NO_SUAVIZAR + docstring de anclas). Verificado: anclaje correcto (100/50/0) y el ensamblador corre sin romper.

**PENDIENTES de confirmación antes de publicar estas variables:**
1. **Fecha y alcance del cierre de la sala de prensa de Casa Rosada** → editar `ACREDITACIONES` en scraper_22 (hoy hay un tramo PLACEHOLDER a 0,5 desde 2024-03).
2. **Serie de recaudación nacional** (ID de Series de Tiempo de datos.gob.ar o CSV `output/_recaudacion.csv`) → sin ella, el módulo 21 corre en MODO SIMPLE (solo 0,12·base, subestima el tope).
3. **Texto vigente del art. 20 de la Ley 24.144** (coeficientes 12%/10% y extensiones).
4. **Slug de la categoría FOPEA** de restricciones de acceso → confirmar con un caso real (hay respaldo por keywords).

### Corrección FOPEA + calibración (junio 2026) — Acceso de la prensa
- **Bug corregido:** la 1ª versión filtraba por keywords y marcaba 523/523 casos. Se reescribió para filtrar por la **categoría oficial de FOPEA** (slug del enlace `/tag/<slug>/`, único por ficha). Slug confirmado: **`restricciones-al-acceso-a-la-informacion-publica`**.
- Resultado: **68/523** casos de acceso. Distribución: discurso-estigmatizante 156, ataques-a-la-integridad 131, acceso 68, judiciales 39, censura 27, pauta-oficial 18, otros-abusos 16, etc. (46 sin categoría detectada ≈ 9%, tratados como no-acceso).
- Conteo anual de acceso: 2023=4, 2024=21, 2025=28, 2026=15 (medio año).
- **Ancla recalibrada:** `restricciones_12m` 0→100 ; **40→0** (antes 10, que clavaba el componente en 0). Proporcional al ancla de causas (0→20).
- **Alcance:** se mantiene la categoría oficial completa (es "información PÚBLICA", inherente a organismos públicos); no se filtra por actor estatal con keywords para evitar ruido (ej. "presidente de la Liga").
- Verificado en el ensamblador: Acceso ~68-72 normal, 19,6 en abril 2026 (cierre); sub_Prensa 74→64,6→72,6. ITR de 18 variables, coherente.

### Recaudación automatizada — Carta Orgánica en modo COMPLETO (junio 2026)
- Serie CONFIRMADA y cableada: **`172.3_TL_RECAION_M_0_0_17`** ("Total recaudación", mensual, millones de $; Secretaría de Hacienda) vía API Series de Tiempo (`apis.datos.gob.ar/series`). Es el proxy de "recursos en efectivo" del art. 20.
- El módulo 21 la baja **automáticamente** (no requiere carga manual). Prioridad: CSV local `output/_recaudacion.csv` (snapshot) → API → modo simple.
- Snapshot fechado de 53 meses (2022-01 a 2026-05) guardado en `_recaudacion.csv` para reproducibilidad y resiliencia ante caída de la API. Escala: millones → miles (×1000) para igualar al balance del BCRA.
- Verificado modo completo: ratio ~0,12-0,14 (dentro del tope) → Respeto Carta Orgánica = 100 ; sub_Banco Central ~66.
