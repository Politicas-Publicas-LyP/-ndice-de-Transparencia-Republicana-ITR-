"""
ITR — Módulo 16: ATN — Aportes del Tesoro Nacional (Poder Ejecutivo)
====================================================================
Federalismo / discrecionalidad federal. Los ATN son un fondo que el Ejecutivo
(Ministerio del Interior) reparte A DEDO a las provincias, por fuera de la
coparticipación automática. Desde la mirada liberal: más ATN = más palanca política
sobre los gobernadores y menos correspondencia fiscal = PEOR institucionalidad.
Su reducción (uso solo para emergencias reales, su fin legal) es una mejora.

  atn_share = devengado en "Aportes del Tesoro Nacional" / devengado TOTAL   (año completo)

Share -> INVARIANTE A LA INFLACIÓN. Fuente: DGSIAF crédito ANUAL (mismo origen que
pauta y costo legislativo). Variable estructural/anual -> serie mensual por
forward-fill con stale_flag.

NOTA v1: el filtro busca "aportes del tesoro nacional" en TODAS las columnas de
descripción y reporta qué encontró (diagnóstico), para confirmar/afinar la línea
exacta con el log local antes de fijarla. El denominador (devengado total) replica
el de pauta; si se prefiere, luego se cambia a "total transferencias a provincias".

Uso:
    py scraper_16_atn.py --desde 2023-01 --hasta 2026-05
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
PATRON = re.compile(r"aportes?\s+del\s+tesoro\s+nacional", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("atn")


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


def atn_anual(anio: int, s: requests.Session) -> dict | None:
    cache = OUTPUT_DIR / f"_cache_atn_{anio}.csv"
    if cache.exists():
        r = pd.read_csv(cache).iloc[0]
        return {"share": float(r["share"]), "atn_dev": float(r["atn_dev"])}

    log.info("DGSIAF %s: descargando crédito anual...", anio)
    try:
        resp = s.get(ANUAL.format(anio=anio), timeout=180)
    except Exception as e:  # noqa: BLE001
        log.warning("DGSIAF %s: fallo (%s)", anio, e)
        return None
    if resp.status_code != 200:
        log.info("DGSIAF %s: sin archivo anual (HTTP %s) — año en curso o no publicado", anio, resp.status_code)
        return None

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = max((n for n in zf.namelist() if n.lower().endswith(".csv")),
                   key=lambda n: zf.getinfo(n).file_size)
        raw = zf.read(name)

    # 1) header para ubicar columnas de descripción + devengado
    header = pd.read_csv(io.BytesIO(raw), nrows=0, dtype=str)
    desc_cols = [c for c in header.columns if c.lower().endswith("_desc") or "desc" in c.lower()]
    if DEV_COL not in header.columns:
        log.error("DGSIAF %s: no está la columna %s. Columnas: %s", anio, DEV_COL, list(header.columns))
        return None
    use = list(dict.fromkeys(desc_cols + [DEV_COL]))
    df = pd.read_csv(io.BytesIO(raw), usecols=use, dtype=str, low_memory=False)

    df["dev"] = _to_num(df[DEV_COL])
    # 2) máscara ATN: cualquier columna de descripción contiene "aportes del tesoro nacional"
    mask = pd.Series(False, index=df.index)
    hit_cols = {}
    for c in desc_cols:
        m = df[c].fillna("").str.contains(PATRON)
        if m.any():
            mask |= m
            hit_cols[c] = sorted(df.loc[m, c].dropna().unique())[:6]
    atn = df.loc[mask, "dev"].sum()
    tot = df["dev"].sum()
    if tot <= 0:
        return None

    # diagnóstico (clave para validar el filtro en el log local)
    log.info("DGSIAF %s: filas ATN=%d | columnas con match: %s", anio, int(mask.sum()),
             {k: v for k, v in hit_cols.items()})
    res = {"share": round(atn / tot, 8), "atn_dev": round(atn, 1)}
    pd.DataFrame([{"anio": anio, **res}]).to_csv(cache, index=False)
    log.info("DGSIAF %s: ATN_devengado=%.0f | share=%.6f (%.4f%% del gasto total)",
             anio, atn, res["share"], res["share"] * 100)
    return res


def diagnostico(anio: int, s: requests.Session) -> None:
    """Vuelca, para un año, los valores de descripción que mencionan tesoro/aporte/
    provincia/asistencia financiera, con su devengado, para ubicar dónde figura el ATN
    en los archivos viejos (la etiqueta de actividad cambió con el tiempo)."""
    pat = re.compile(r"tesoro|aporte|provincia|asistencia\s+financ|coparticip", re.IGNORECASE)
    try:
        resp = s.get(ANUAL.format(anio=anio), timeout=180)
    except Exception as e:  # noqa: BLE001
        log.error("fallo %s: %s", anio, e); return
    if resp.status_code != 200:
        log.error("año %s sin archivo (HTTP %s)", anio, resp.status_code); return
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = max((n for n in zf.namelist() if n.lower().endswith(".csv")),
                   key=lambda n: zf.getinfo(n).file_size)
        raw = zf.read(name)
    df = pd.read_csv(io.BytesIO(raw), dtype=str, low_memory=False)
    df["_d"] = _to_num(df[DEV_COL]) if DEV_COL in df.columns else 0
    desc = [c for c in df.columns if "desc" in c.lower()]
    print(f"\n=== DIAGNÓSTICO ATN {anio} — valores de descripción que mencionan tesoro/aporte/provincia ===")
    for c in desc:
        m = df[c].fillna("").str.contains(pat)
        if m.any():
            vals = df.loc[m].groupby(c)["_d"].sum().sort_values(ascending=False)
            print(f"\n-- columna {c} --")
            for k, v in vals.head(12).items():
                print(f"   {v:>16,.0f}  | {k}")


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 16 — ATN (share anual)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--diagnostico", type=int, default=None,
                    help="año a inspeccionar para descubrir cómo se etiqueta el ATN viejo")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    if args.diagnostico:
        diagnostico(args.diagnostico, s)
        return 0
    anios = list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1))
    data = {a: atn_anual(a, s) for a in anios}
    data = {a: v for a, v in data.items() if v}
    if not data:
        log.error("No se obtuvo ningún año (¿bloqueo de IP o filtro sin match?).")
        return 1

    print("\n=== ATN POR AÑO (auditar el filtro) ===")
    for a in sorted(data):
        print(f"  {a}: ATN_devengado={data[a]['atn_dev']:,.0f} | "
              f"share={data[a]['share']:.6f} ({data[a]['share']*100:.4f}% del gasto)")

    periods = pd.period_range(args.desde, args.hasta, freq="M")
    rows = []
    for p in periods:
        usable = [a for a in data if a <= p.year]
        if not usable:
            rows.append({"periodo": str(p), "atn_share": float("nan"), "stale_meses": float("nan")})
            continue
        a = max(usable)
        stale = 0 if a == p.year else (p - pd.Period(f"{a}-12", "M")).n
        rows.append({"periodo": str(p), "atn_share": data[a]["share"], "stale_meses": stale})
    serie = pd.DataFrame(rows)

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"atn_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
