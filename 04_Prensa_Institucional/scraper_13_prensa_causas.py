"""
ICIA — Módulo 13: Causas judiciales contra periodistas [Prensa, 4%]
====================================================================
Event-count (método del Human Freedom Index) de ACCIONES JUDICIALES contra periodistas
y medios (categoría 10 de FOPEA: "Acciones judiciales civiles o penales" — demandas,
querellas, hostigamiento judicial). NO se consideran otros tipos de ataque a la prensa.
Signo: más causas judiciales = peor (uso del aparato judicial para acallar a la prensa).

Como son eventos escasos (~20/año), se reporta con ventana móvil de 12 meses.
Se distingue, como aproximación, el subconjunto con agresor estatal/funcionario.

Fuente: https://monitoreo.fopea.org/wp-json/wp/v2/comunicados (WordPress REST, abierta).
La categoría y el agresor solo están en el HTML del caso (no en la REST), por eso se
parsea cada caso. Cacheado por id en ./output/_cache_fopea.json.

Uso:
    py scraper_13_prensa_causas.py --desde 2023-01 --hasta 2026-05
    py scraper_13_prensa_causas.py --desde 2023-01 --hasta 2026-05 --no-clasificar   # solo total, rápido
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

API = "https://monitoreo.fopea.org/wp-json/wp/v2/comunicados"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
CACHE = OUTPUT_DIR / "_cache_fopea.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept": "*/*", "Accept-Language": "es-AR,es;q=0.9"}
THROTTLE = 0.4
TAG_JUDICIAL = "acciones-judiciales-civiles-o-penales"
ESTADO_KW = re.compile(r"\b(milei|presidente|gobierno|ministr|funcionari|gobernador|intendente|"
                       r"oficial|estado|afi|organismo|secretar|jefe de gabinete|vocero)\b", re.I)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("prensa_causas")


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
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    return df


def clasificar(df: pd.DataFrame, s: requests.Session, cache: dict) -> pd.DataFrame:
    nuevos = 0
    for r in df.itertuples():
        key = str(r.id)
        if key in cache:
            continue
        try:
            html = s.get(r.link, timeout=30).text.lower()
            judicial = (TAG_JUDICIAL in html) or ("acciones judiciales" in html)
            estado = bool(ESTADO_KW.search(html))
            cache[key] = {"judicial": judicial, "estado": estado}
        except Exception:  # noqa: BLE001
            cache[key] = {"judicial": False, "estado": False}
        nuevos += 1
        if nuevos % 25 == 0:
            log.info("  ...%s casos clasificados", nuevos); CACHE.write_text(json.dumps(cache))
        time.sleep(THROTTLE)
    CACHE.write_text(json.dumps(cache))
    df["judicial"] = df["id"].astype(str).map(lambda k: cache.get(k, {}).get("judicial", False))
    df["jud_estado"] = df["id"].astype(str).map(lambda k: cache.get(k, {}).get("judicial", False) and cache.get(k, {}).get("estado", False))
    log.info("Clasificación: %s nuevos | judiciales=%s | judiciales del Estado=%s",
             nuevos, int(df["judicial"].sum()), int(df["jud_estado"].sum()))
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 13 — Hostigamiento a la prensa (FOPEA)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    df = get_casos(s)
    if df.empty:
        log.error("Sin casos (¿API caída o bloqueada?)."); return 1
    log.info("Casos totales en la base: %s | rango %s a %s", len(df), df["fecha"].min().date(), df["fecha"].max().date())

    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    win = df[(df["fecha"] >= args.desde + "-01")].copy()
    win = clasificar(win, s, cache)   # clasifica cada caso (cacheado) para hallar las judiciales

    jud = win[win["judicial"]].copy()
    jud["periodo"] = jud["fecha"].dt.to_period("M")
    periods = pd.period_range(args.desde, args.hasta, freq="M")
    g = pd.DataFrame(index=periods)
    g["n_causas_judiciales"] = jud[jud["judicial"]]["periodo"].value_counts().reindex(periods, fill_value=0)
    je = jud[jud["jud_estado"]]["periodo"].value_counts()
    g["n_causas_jud_estado"] = [int(je.get(p, 0)) for p in periods]
    g["causas_jud_12m"] = g["n_causas_judiciales"].rolling(12, min_periods=6).sum()
    g["causas_estado_12m"] = pd.Series(g["n_causas_jud_estado"].values, index=periods).rolling(12, min_periods=6).sum()
    g = g.reset_index(names="periodo"); g["periodo"] = g["periodo"].astype(str)

    print("\n=== RESUMEN ANUAL (causas judiciales contra periodistas) ===")
    tmp = win.copy(); tmp["a"] = tmp["fecha"].dt.year
    print(tmp.groupby("a").agg(causas_judiciales=("judicial", "sum"),
                               de_las_cuales_del_estado=("jud_estado", "sum")).to_string())
    print("\n=== SERIE MENSUAL (cola) ===")
    print(g.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"prensa_causas_mensual_{stamp}.csv"
    g.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
