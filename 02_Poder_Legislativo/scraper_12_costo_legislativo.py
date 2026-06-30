"""
ICIA — Módulo 12: Costo del Poder Legislativo (% del gasto)  [Legislativo, 3%]
==============================================================================
Mide el peso del costo de funcionamiento del Congreso sobre el gasto público total.
Signo: más caro = peor (eficiencia republicana). Inflación-neutral por trabajar con
participación (share), no con pesos nominales.

  costo_legislativo = devengado(Poder Legislativo) / devengado(total)

Fuente: DGSIAF crédito mensual (misma del Módulo 4/8). Jurisdicción "Poder Legislativo
Nacional" (incluye Senado, Diputados, Biblioteca, Imprenta, Defensoría del Pueblo y AGN).
Diagnóstico-aware: vuelca los servicios incluidos por si se quiere acotar a "costo puro".
Cacheado por año.

Uso:
    py scraper_12_costo_legislativo.py --desde 2023-01 --hasta 2026-05
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

MENSUAL = "https://dgsiaf-repo.mecon.gob.ar/repository/pa/datasets/{anio}/credito-mensual-{anio}.zip"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "ICIA-LyP/0.1 (politicaspublicas@libertadyprogreso.org)"}
COLS = ["impacto_presupuestario_mes", "jurisdiccion_desc", "servicio_desc", "credito_devengado"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("costo_legislativo")


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


# Organismos autónomos alojados en la jurisdicción Poder Legislativo que NO son
# "costo del Congreso" y se excluyen (la AGN, además, se mide aparte como control externo positivo).
EXCLUIR = "auditor|defensor|penitenciaria|tortura|cnpt"


def costo_anual(anio: int, s: requests.Session, diag: bool) -> dict[int, float]:
    cache = OUTPUT_DIR / f"_cache_costoleg_v2_{anio}.csv"
    usar_cache = anio < datetime.now().year   # cachear SOLO años cerrados; el año en curso se recalcula
    if usar_cache and cache.exists():
        d = pd.read_csv(cache)
        return dict(zip(d["mes"].astype(int), d["share"]))

    log.info("DGSIAF %s: descargando crédito mensual...", anio)
    try:
        resp = s.get(MENSUAL.format(anio=anio), timeout=240); resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.warning("DGSIAF %s: fallo (%s)", anio, e); return {}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = max((n for n in zf.namelist() if n.lower().endswith(".csv")),
                   key=lambda n: zf.getinfo(n).file_size)
        df = pd.read_csv(io.BytesIO(zf.read(name)), usecols=COLS, dtype=str, low_memory=False)

    df["mes"] = pd.to_numeric(df["impacto_presupuestario_mes"], errors="coerce")
    df["dev"] = _to_num(df["credito_devengado"])
    leg = df["jurisdiccion_desc"].fillna("").str.contains("legislativo", case=False)
    excl = df["servicio_desc"].fillna("").str.contains(EXCLUIR, case=False, regex=True)
    legcore = leg & ~excl   # aparato legislativo propio (cámaras + servicios del Congreso)

    if diag:
        print(f"\n  [DIAG {anio}] INCLUIDOS en costo del Congreso (devengado anual, millones):")
        print(df[legcore].groupby("servicio_desc")["dev"].sum().sort_values(ascending=False).to_string())
        print(f"  [DIAG {anio}] EXCLUIDOS (organismos autónomos):")
        print(df[leg & excl].groupby("servicio_desc")["dev"].sum().sort_values(ascending=False).to_string())

    out = {}
    for mes in sorted(int(m) for m in df["mes"].dropna().unique()):
        sub = df[df["mes"] == mes]
        tot = sub["dev"].sum()
        if tot <= 0:
            continue
        legdev = sub.loc[legcore & (df["mes"] == mes), "dev"].sum()
        out[mes] = round(legdev / tot, 6)
    if usar_cache:
        pd.DataFrame({"mes": list(out), "share": list(out.values())}).to_csv(cache, index=False)
    log.info("DGSIAF %s: costo legislativo (share) dic≈ %s", anio, out.get(12, out.get(max(out) if out else 0)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 12 — Costo del Legislativo")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--no-diag", action="store_true")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    anios = list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1))
    data = {a: costo_anual(a, s, not args.no_diag) for a in anios}

    periods = pd.period_range(args.desde, args.hasta, freq="M")
    rows = [{"periodo": str(p), "costo_legislativo": data.get(p.year, {}).get(p.month, float("nan"))}
            for p in periods]
    serie = pd.DataFrame(rows)

    print("\n=== RESUMEN ANUAL (share a diciembre / último mes) ===")
    for a in anios:
        d = data.get(a, {})
        if d:
            ult = d.get(12, d[max(d)])
            print(f"  {a}: costo Legislativo = {ult:.5f} ({ult*100:.3f}% del gasto)")

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"costo_legislativo_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
