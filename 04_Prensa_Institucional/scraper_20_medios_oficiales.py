"""
ITR — Módulo 20: Aparato de medios estatales (Prensa Institucional)
===================================================================
Mide el TAMAÑO del aparato de medios del Estado (RTA/TV Pública, Radio Nacional,
Télam/agencia de noticias, Contenidos Públicos) como PORCIÓN del gasto devengado total.
Desde la mirada liberal: cuanto mayor es la maquinaria de medios estatales financiada
con fondos públicos, mayor la intervención del Estado en el ecosistema mediático y la
competencia desleal contra la prensa privada (peor). Su achicamiento (cierre de Télam,
downsizing de RTA) es una mejora institucional. Ideal: cerca de 0.

  medios_share = devengado en entidades de medios estatales / devengado TOTAL  (año completo)

Share -> INVARIANTE A LA INFLACIÓN. Fuente: DGSIAF crédito ANUAL (igual que pauta/costo/ATN).
Variable estructural/anual -> serie mensual por forward-fill con stale_flag.

NOTA v1: filtro por palabras clave en las columnas de descripción (jurisdicción/servicio/
entidad/programa) y REPORTA qué matcheó (diagnóstico), para confirmar/afinar las entidades
con el log local antes de fijarlo.

Uso:
    py scraper_20_medios_oficiales.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ANUAL = "https://dgsiaf-repo.mecon.gob.ar/repository/pa/datasets/{anio}/credito-anual-{anio}.zip"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "ITR-LyP/0.1 (politicaspublicas@libertadyprogreso.org)"}
DEV_COL = "credito_devengado"
# entidades de medios estatales (federales)
PATRON = re.compile(
    r"(?:radio\s+y\s+televisi|televisi[oó]n\s+p[uú]blica|radio\s+y\s+televisi[oó]n\s+argentina|"
    r"\brta\b|radio\s+nacional|radio\s+del\s+estado|t[eé]lam|contenidos\s+p[uú]blicos|"
    r"servicios?\s+de\s+radio\s+y\s+televisi)", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("medios")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=2.5, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def _to_num(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie.astype(str).str.replace(".", "", regex=False)
                         .str.replace(",", ".", regex=False), errors="coerce")


def medios_anual(anio: int, s: requests.Session) -> dict | None:
    cache = OUTPUT_DIR / f"_cache_medios_{anio}.csv"
    if cache.exists():
        r = pd.read_csv(cache).iloc[0]
        return {"share": float(r["share"]), "medios_dev": float(r["medios_dev"])}

    log.info("DGSIAF %s: descargando crédito anual...", anio)
    try:
        resp = s.get(ANUAL.format(anio=anio), timeout=180)
    except Exception as e:  # noqa: BLE001
        log.warning("DGSIAF %s: fallo (%s)", anio, e)
        return None
    if resp.status_code != 200:
        log.info("DGSIAF %s: sin archivo anual (HTTP %s)", anio, resp.status_code)
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = max((n for n in zf.namelist() if n.lower().endswith(".csv")),
                   key=lambda n: zf.getinfo(n).file_size)
        raw = zf.read(name)
    header = pd.read_csv(io.BytesIO(raw), nrows=0, dtype=str)
    desc_cols = [c for c in header.columns if "desc" in c.lower()]
    if DEV_COL not in header.columns:
        log.error("DGSIAF %s: no está %s. Cols: %s", anio, DEV_COL, list(header.columns))
        return None
    df = pd.read_csv(io.BytesIO(raw), usecols=list(dict.fromkeys(desc_cols + [DEV_COL])),
                     dtype=str, low_memory=False)
    df["dev"] = _to_num(df[DEV_COL])

    mask = pd.Series(False, index=df.index)
    hit_cols = {}
    for c in desc_cols:
        m = df[c].fillna("").str.contains(PATRON) & ~df[c].fillna("").str.contains("universidad", case=False)
        if m.any():
            mask |= m
            hit_cols[c] = sorted(df.loc[m, c].dropna().unique())[:8]
    medios = df.loc[mask, "dev"].sum()
    tot = df["dev"].sum()
    if tot <= 0:
        return None
    log.info("DGSIAF %s: filas medios=%d | match: %s", anio, int(mask.sum()), hit_cols)
    res = {"share": round(medios / tot, 8), "medios_dev": round(medios, 1)}
    pd.DataFrame([{"anio": anio, **res}]).to_csv(cache, index=False)
    log.info("DGSIAF %s: medios_devengado=%.0f | share=%.6f (%.4f%% del gasto)",
             anio, medios, res["share"], res["share"] * 100)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 20 — Medios estatales (share anual)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    anios = list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1))
    data = {a: medios_anual(a, s) for a in anios}
    data = {a: v for a, v in data.items() if v}
    if not data:
        log.error("No se obtuvo ningún año (¿bloqueo de IP o filtro sin match?).")
        return 1

    print("\n=== MEDIOS ESTATALES POR AÑO (auditar el filtro) ===")
    for a in sorted(data):
        print(f"  {a}: medios_devengado={data[a]['medios_dev']:,.0f} | "
              f"share={data[a]['share']:.6f} ({data[a]['share']*100:.4f}% del gasto)")

    periods = pd.period_range(args.desde, args.hasta, freq="M")
    rows = []
    for p in periods:
        usable = [a for a in data if a <= p.year]
        if not usable:
            rows.append({"periodo": str(p), "medios_share": float("nan"), "stale_meses": float("nan")})
            continue
        a = max(usable)
        stale = 0 if a == p.year else (p - pd.Period(f"{a}-12", "M")).n
        rows.append({"periodo": str(p), "medios_share": data[a]["share"], "stale_meses": stale})
    serie = pd.DataFrame(rows)

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"medios_oficiales_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
