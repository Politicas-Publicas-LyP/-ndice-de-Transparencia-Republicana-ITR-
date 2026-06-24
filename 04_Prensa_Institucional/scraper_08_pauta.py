"""
ICIA — Módulo 8: Pauta Publicitaria Oficial (Prensa Institucional, 7%)
======================================================================
Sustitución acordada (la concentración/HHI es inviable: dataset por medio congelado
en 2022): INTENSIDAD de la pauta oficial = gasto DEVENGADO en "Publicidad y propaganda"
como PROPORCIÓN del gasto devengado total. Share -> INVARIANTE A LA INFLACIÓN.
Desde la mirada liberal: más pauta = más aparato de propaganda e intervención estatal
en medios (peor); su reducción es una mejora institucional.

  intensidad_pauta = devengado_publicidad / devengado_total   (año completo)

Fuente: DGSIAF crédito ANUAL (devengado de año completo, sin la ambigüedad
acumulado/mensual del archivo mensual). Partida: Inciso 3 "Servicios no personales",
principal "Publicidad y propaganda" (validado). Variable estructural/anual ->
serie mensual por forward-fill con stale_flag. (El share por crédito VIGENTE se
descartó: tiene valores negativos/contra que lo hacen inestable.)

Uso:
    py scraper_08_pauta.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import io
import logging
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
HEADERS = {"User-Agent": "ICIA-LyP/0.1 (politicaspublicas@libertadyprogreso.org)"}
COLS = ["principal_desc", "parcial_desc", "credito_devengado"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("pauta")


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


def intensidad_anual(anio: int, s: requests.Session) -> dict | None:
    cache = OUTPUT_DIR / f"_cache_pauta_anual_{anio}.csv"
    if cache.exists():
        r = pd.read_csv(cache).iloc[0]
        return {"intensidad": float(r["intensidad"]), "pub_dev": float(r["pub_dev"])}

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
        df = pd.read_csv(io.BytesIO(zf.read(name)), usecols=COLS, dtype=str, low_memory=False)

    df["dev"] = _to_num(df["credito_devengado"])
    mask = (df["principal_desc"].fillna("") + " " + df["parcial_desc"].fillna("")).str.contains(
        "publicidad", case=False)
    pub = df.loc[mask, "dev"].sum()
    tot = df["dev"].sum()
    if tot <= 0:
        return None
    res = {"intensidad": round(pub / tot, 6), "pub_dev": round(pub, 1)}
    pd.DataFrame([{"anio": anio, **res}]).to_csv(cache, index=False)
    log.info("DGSIAF %s: pub_devengado=%.0f millones | intensidad=%.5f (%.4f%% del gasto)",
             anio, pub, res["intensidad"], res["intensidad"] * 100)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 8 — Pauta (intensidad anual)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    anios = list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1))
    data = {a: intensidad_anual(a, s) for a in anios}
    data = {a: v for a, v in data.items() if v}
    if not data:
        log.error("No se obtuvo ningún año.")
        return 1

    print("\n=== INTENSIDAD DE PAUTA POR AÑO (auditar) ===")
    for a in sorted(data):
        print(f"  {a}: pub_devengado={data[a]['pub_dev']:,.0f} millones | "
              f"intensidad={data[a]['intensidad']:.5f} ({data[a]['intensidad']*100:.4f}% del gasto)")

    # serie mensual estructural: año con dato propio, o forward-fill con stale_flag
    periods = pd.period_range(args.desde, args.hasta, freq="M")
    rows = []
    for p in periods:
        usable = [a for a in data if a <= p.year]
        if not usable:
            rows.append({"periodo": str(p), "intensidad_pauta": float("nan"), "stale_meses": float("nan")})
            continue
        a = max(usable)
        stale = 0 if a == p.year else (p - pd.Period(f"{a}-12", "M")).n
        rows.append({"periodo": str(p), "intensidad_pauta": data[a]["intensidad"], "stale_meses": stale})
    serie = pd.DataFrame(rows)

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"pauta_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
