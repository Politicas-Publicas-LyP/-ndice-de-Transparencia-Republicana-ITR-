"""
ITR — Módulo 22: Acceso de la prensa al poder [Prensa / Libertad de Prensa]
==========================================================================
Mide cuánto el Estado restringe el ACCESO de la prensa a la información y a las
coberturas. Desde la mirada liberal: una prensa libre necesita poder acceder a
funcionarios, conferencias y lugares públicos; cerrar la sala de periodistas,
recortar acreditaciones u obstruir coberturas son formas de control del poder
sobre la prensa (peor). Ideal: acceso pleno y sin obstrucciones.

La variable COMBINA dos componentes (mismo patrón dato + tabla mantenida del BCRA):

  (1) acceso_estructural  -> ESTADO del régimen de acceso en Casa Rosada, tabla
      MANTENIDA a mano desde hechos documentados y datables. Niveles:
          1.0 = sala de prensa operativa + acreditaciones abiertas + conferencias
                con preguntas libres.
          0.5 = restricción parcial (sala cerrada pero acreditaciones/conferencias
                por otra vía, o acreditaciones acotadas).
          0.0 = sin sala / sin régimen de acreditaciones / acceso cerrado.
      Es un ESTADO PUNTUAL -> en el ensamblador va en NO_SUAVIZAR (vale por entero).

  (2) restricciones_12m   -> EVENT-COUNT (método FOPEA, igual que causas) de casos de
      RESTRICCIÓN DE ACCESO A LA INFORMACIÓN / OBSTRUCCIÓN A LA COBERTURA en ventana
      móvil de 12 meses. Signo: más restricciones = peor.

Fuente del componente (2): monitoreo.fopea.org (WordPress REST, abierta) — misma base
que scraper_13. La categoría exacta se detecta por tag-slug Y por palabras clave en el
HTML del caso (robusto a que cambie el slug). CONFIRMAR el slug con un caso real.

Uso:
    py scraper_22_acceso_prensa.py --desde 2023-01 --hasta 2026-05
    py scraper_22_acceso_prensa.py --desde 2023-01 --hasta 2026-05 --solo-estructural
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

# ----------------------------------------------------------------------------
# (1) TABLA MANTENIDA — régimen de acceso de la prensa en Casa Rosada.
# Cada tramo: (desde 'AAAA-MM', hasta 'AAAA-MM' o None=en curso, nivel, nota/fuente).
# nivel: 1.0 acceso pleno / 0.5 restricción parcial / 0.0 cierre.
#
# >>> PENDIENTE / CONFIRMAR <<<
# La fecha y el alcance del cierre de la sala de periodistas de Casa Rosada son un
# PLACEHOLDER hasta confirmar con fuente datada. Editar el tramo de abajo con la fecha
# real (y si hubo reapertura parcial, agregar un tramo a 0.5). No publicar el valor de
# esta variable hasta confirmar.
# ----------------------------------------------------------------------------
ACREDITACIONES = [
    ("2015-12", "2026-03", 1.0, "Régimen de acreditaciones y sala de prensa operativos"),
    ("2026-04", "2026-04", 0.0, "Cierre TOTAL de la sala de periodistas de Casa Rosada (comienzos de abril; cerrada ~todo abril)"),
    ("2026-05", None,      1.0, "Reapertura de la sala de prensa (comienzos de mayo)"),
]

# ----------------------------------------------------------------------------
# (2) FOPEA — restricciones de acceso / obstrucción a la cobertura
# ----------------------------------------------------------------------------
API = "https://monitoreo.fopea.org/wp-json/wp/v2/comunicados"
CACHE = OUTPUT_DIR / "_cache_fopea_acceso.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept": "*/*", "Accept-Language": "es-AR,es;q=0.9"}
THROTTLE = 0.4
# Categoría OFICIAL de FOPEA (tag de WordPress). CONFIRMADO con casos reales: cada ficha
# trae UNA "Categoría:" como enlace /tag/<slug>/. La de acceso es exactamente esta:
ACCESO_SLUGS = {"restricciones-al-acceso-a-la-informacion-publica"}
TAG_RE = re.compile(r"/tag/([a-z0-9\-]+)/", re.I)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("acceso_prensa")


def serie_estructural(periods: pd.PeriodIndex) -> pd.Series:
    val = pd.Series(pd.NA, index=periods, dtype="Float64")
    for d, h, nivel, _ in ACREDITACIONES:
        p0 = pd.Period(d, "M")
        p1 = periods.max() if h is None else pd.Period(h, "M")
        val[(periods >= p0) & (periods <= p1)] = nivel
    return val


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def get_casos(s: requests.Session) -> pd.DataFrame:
    rows, page = [], 1
    while True:
        try:
            resp = s.get(API, params={"per_page": 100, "page": page,
                                      "_fields": "id,date,link,title"}, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("REST page %s: %s", page, e); break
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        for c in data:
            rows.append({"id": c["id"], "fecha": c["date"][:10], "link": c.get("link", "")})
        log.info("REST page %s: %s casos (total %s)", page, len(data), len(rows))
        page += 1
        time.sleep(0.3)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    return df


def clasificar(df: pd.DataFrame, s: requests.Session, cache: dict) -> pd.DataFrame:
    """Extrae la CATEGORÍA oficial de cada ficha (el slug del enlace /tag/<slug>/, único por
    caso) y marca acceso = la categoría está en ACCESO_SLUGS. Determinístico y auditable."""
    nuevos = 0
    for r in df.itertuples():
        key = str(r.id)
        if key in cache and "categoria" in cache[key]:   # re-clasifica entradas viejas
            continue
        try:
            html = s.get(r.link, timeout=30).text
            m = TAG_RE.search(html)
            cache[key] = {"categoria": m.group(1).lower() if m else ""}
        except Exception:  # noqa: BLE001
            cache[key] = {"categoria": ""}
        nuevos += 1
        if nuevos % 25 == 0:
            log.info("  ...%s casos clasificados", nuevos); CACHE.write_text(json.dumps(cache))
        time.sleep(THROTTLE)
    CACHE.write_text(json.dumps(cache))
    df["categoria"] = df["id"].astype(str).map(lambda k: cache.get(k, {}).get("categoria", ""))
    df["acceso"] = df["categoria"].isin(ACCESO_SLUGS)
    log.info("Clasificación: %s nuevos | acceso=%s de %s casos", nuevos, int(df["acceso"].sum()), len(df))
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 22 — Acceso de la prensa")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--solo-estructural", action="store_true",
                    help="no consultar FOPEA; solo el flag de acreditaciones")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    periods = pd.period_range(args.desde, args.hasta, freq="M")
    out = pd.DataFrame({"periodo": periods.astype(str)})
    out["acceso_estructural"] = serie_estructural(periods).values

    if args.solo_estructural:
        out["n_restricciones"] = pd.NA
        out["restricciones_12m"] = pd.NA
    else:
        s = session()
        df = get_casos(s)
        if df.empty:
            log.warning("FOPEA sin casos (¿API caída/bloqueada?). Sigo solo con estructural.")
            out["n_restricciones"] = pd.NA
            out["restricciones_12m"] = pd.NA
        else:
            log.info("Casos totales en la base: %s | rango %s a %s",
                     len(df), df["fecha"].min().date(), df["fecha"].max().date())
            cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
            win = df[df["fecha"] >= args.desde + "-01"].copy()
            win = clasificar(win, s, cache)
            acc = win[win["acceso"]].copy()
            acc["periodo"] = acc["fecha"].dt.to_period("M")
            n = acc["periodo"].value_counts().reindex(periods, fill_value=0)
            out["n_restricciones"] = n.values
            out["restricciones_12m"] = n.rolling(12, min_periods=6).sum().values

            print("\n=== DISTRIBUCIÓN DE CATEGORÍAS FOPEA (auditar el filtro) ===")
            print(win["categoria"].value_counts().head(25).to_string())
            print("\n=== RESUMEN ANUAL (restricciones de acceso a la información pública) ===")
            tmp = win.copy(); tmp["a"] = tmp["fecha"].dt.year
            print(tmp.groupby("a")["acceso"].sum().to_string())

    print("\n=== SERIE MENSUAL (cola) ===")
    print(out.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"acceso_prensa_mensual_{stamp}.csv"
    out.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado: %s", out_csv)
    log.warning("Recordá CONFIRMAR la fecha/alcance del cierre de la sala de prensa en ACREDITACIONES "
                "antes de publicar esta variable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
