"""
ICIA — Módulo 4: Discrecionalidad Presupuestaria vía DNU/DA (Poder Ejecutivo, 15%)
==================================================================================
Mide cuán discrecionalmente maneja el Ejecutivo el presupuesto, con DOS señales
robustas (la magnitud en pesos desde DGSIAF se descartó: el crédito tiene rarezas
contables —ceros de prórroga, reorganización ministerial dic-2023, valores
negativos/contra— que hacen inestable cualquier métrica composicional):

  1) presupuesto_aprobado (SEÑAL DOMINANTE): ¿hay ley de presupuesto ese año, o se
     gobierna por prórroga? Gobernar sin presupuesto = control parlamentario nulo
     sobre el gasto = falla institucional grave. Verificado vía Boletín Oficial.

  2) Conteo de modificaciones por Decisión Administrativa (JGM) y DNU, según la OPC
     (única fuente que ata cada reasignación a su instrumento). Frecuencia con que
     el Ejecutivo rehace el presupuesto por decreto. Fecha cruzada con InfoLEG.

Series crudas; normalización y pesos en Sprint 6 (presupuesto_aprobado=0 penaliza fuerte).
Cobertura: la OPC publica el análisis por instrumento desde 2024; años previos van
con conteo NaN (dato inexistente, no 0). El flag de régimen cubre todos los años.

Uso:
    py scraper_04_discrecionalidad.py --desde 2023-01 --hasta 2026-05
    py scraper_04_discrecionalidad.py --desde 2023-01 --hasta 2025-12 --zip-local base-infoleg.zip
Requisitos: pip install pandas requests beautifulsoup4 lxml  (+ infoleg_source.py)
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from infoleg_source import load_infoleg_df

OPC_YEAR_URL = ("https://opc.gob.ar/ejecucion-presupuestaria/modificaciones-presupuestarias/"
                "modificaciones-presupuestarias-{anio}/")
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9",
}
MODIF_RE = re.compile(r"N[°º]\s*\d+\s*[-–]\s*(DA|DNU)\s*(\d+)", re.IGNORECASE)

# Régimen presupuestario por ejercicio (verificado vía Boletín Oficial, jun-2026).
#   2023: Ley 27.701            | 2024: prórroga Dec. 88/2023
#   2025: prórroga Dec. 1131/24 | 2026: Ley 27.798 (Presupuesto 2026, B.O. 02/01/2026)
PRESUPUESTO_APROBADO = {2023: 1, 2024: 0, 2025: 0, 2026: 1}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("discrecionalidad")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def fetch_modificaciones(anios: list[int], s: requests.Session) -> tuple[pd.DataFrame, set[int]]:
    rows, covered = [], set()
    for anio in anios:
        try:
            resp = s.get(OPC_YEAR_URL.format(anio=anio), timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("OPC %s: fallo %s", anio, e)
            continue
        if resp.status_code != 200:
            log.warning("OPC %s: HTTP %s (OPC no publica análisis por instrumento de ese año)", anio, resp.status_code)
            continue
        covered.add(anio)
        for a in BeautifulSoup(resp.text, "lxml").find_all("a", href=True):
            if "/download/" not in a["href"]:
                continue
            m = MODIF_RE.search(a.get_text(" ", strip=True))
            if m:
                rows.append({"anio": anio, "tipo": m.group(1).upper(), "nro": m.group(2),
                             "texto": a.get_text(" ", strip=True)})
        time.sleep(1.0)
    df = pd.DataFrame(rows).drop_duplicates(subset=["anio", "tipo", "nro"])
    log.info("Modificaciones detectadas en OPC: %s (años cubiertos: %s)", len(df), sorted(covered))
    return df, covered


def chequear_presupuesto(inf: pd.DataFrame) -> None:
    """Diagnóstico best-effort: lista posibles leyes de presupuesto en InfoLEG."""
    ley = inf[inf["tipo_norma"] == "Ley"].copy()
    blob = ley[["titulo_resumido", "titulo_sumario"]].fillna("").agg(" ".join, axis=1).str.upper()
    pres = ley[blob.str.contains("PRESUPUESTO") & (ley["_fecha"].dt.year >= 2021)]
    print("\n=== Posibles leyes de PRESUPUESTO en InfoLEG (referencia; flag es el verificado) ===")
    if len(pres):
        print(pres.assign(fecha=pres["_fecha"].dt.date)[["fecha", "numero_norma", "titulo_resumido"]]
              .head(12).to_string(index=False))
    else:
        print("  (ninguna por título; flag de régimen viene de verificación en Boletín Oficial)")
    print("Flag de régimen configurado:", PRESUPUESTO_APROBADO)


def fechar_via_infoleg(mods: pd.DataFrame, inf: pd.DataFrame) -> pd.DataFrame:
    inf = inf.dropna(subset=["_fecha"]).copy()
    inf["num"] = inf["numero_norma"].astype(str).str.strip()
    inf["anio_f"] = inf["_fecha"].dt.year
    da = inf[inf["tipo_norma"] == "Decisión Administrativa"]
    dnu = inf[inf["clase_norma"] == "DNU"]
    fechas = []
    for r in mods.itertuples():
        base = da if r.tipo == "DA" else dnu
        cand = base[(base["num"] == r.nro) & (base["anio_f"] == r.anio)]
        fechas.append(cand["_fecha"].min() if len(cand) else pd.NaT)
    mods = mods.copy()
    mods["fecha"] = fechas
    return mods


def build(mods: pd.DataFrame, covered: set[int], desde: str, hasta: str):
    ok = mods.dropna(subset=["fecha"]).copy()
    ok["periodo"] = ok["fecha"].dt.to_period("M")
    periods = pd.period_range(desde, hasta, freq="M")
    nan = float("nan")

    da = ok[ok["tipo"] == "DA"]["periodo"].value_counts()
    dnu = ok[ok["tipo"] == "DNU"]["periodo"].value_counts()
    serie = pd.DataFrame(index=periods)
    # SEÑAL DOMINANTE: ¿hay ley de presupuesto ese año?
    serie["presupuesto_aprobado"] = [PRESUPUESTO_APROBADO.get(p.year, nan) for p in periods]
    # conteo OPC: NaN para años sin cobertura (no inventar 0)
    serie["n_modif_da"] = [float(da.get(p, 0)) if p.year in covered else nan for p in periods]
    serie["n_modif_dnu"] = [float(dnu.get(p, 0)) if p.year in covered else nan for p in periods]
    serie["n_modif_total"] = serie["n_modif_da"] + serie["n_modif_dnu"]
    serie["modif_12m"] = serie["n_modif_total"].rolling(12, min_periods=6).sum()
    serie = serie.reset_index(names="periodo")
    serie["periodo"] = serie["periodo"].astype(str)
    return serie, ok.sort_values("fecha")


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 4 — Discrecionalidad Presupuestaria")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--zip-local", help="ZIP InfoLEG ya descargado")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    anios = list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1))
    s = session()

    mods, covered = fetch_modificaciones(anios, s)
    if mods.empty:
        log.error("No se detectaron modificaciones (¿OPC bloqueó o cambió el HTML?).")
        return 1
    inf = load_infoleg_df(zip_local=args.zip_local)
    chequear_presupuesto(inf)
    mods = fechar_via_infoleg(mods, inf)

    sin_fecha = mods[mods["fecha"].isna()]
    if len(sin_fecha):
        log.warning("VALIDACIÓN: %s modificaciones sin fecha:", len(sin_fecha))
        print(sin_fecha[["anio", "tipo", "nro", "texto"]].to_string(index=False))

    serie, detalle = build(mods, covered, args.desde, args.hasta)

    print("\n=== MODIFICACIONES FECHADAS (auditar) ===")
    print(detalle[["fecha", "tipo", "nro", "texto"]].to_string(index=False))
    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"discrecionalidad_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
