"""
ICIA — Módulo 2: Calidad Normativa (Poder Legislativo, 10%)  [PRODUCCIÓN]
==========================================================================
Diseño acordado (normalizar-y-combinar en Sprint 6, NO ratio crudo):

  calidad_normativa = w1 · produccion_sustantiva_norm + w2 · (1 − ruido_simbolico_norm)

Este módulo SOLO extrae las series mensuales crudas; la normalización 0–1 contra el
período base y los pesos w1/w2 se definen en el módulo de normalización.

  - produccion_sustantiva = LEYES SANCIONADAS por mes (InfoLEG, por fecha de sanción).
  - ruido_simbolico        = DECLARACIONES / RESOLUCIONES / COMUNICACIONES PRESENTADAS
                             por mes (buscador HCDN, cuenta por fecha de ingreso).

Robustez: el buscador de HCDN es frágil (sin CDN). Se consulta SOLO el total (liviano),
con throttling, reintentos y CACHÉ en ./output/_cache_congreso.json para reanudar.

Uso:
    py scraper_02_calidad_normativa.py --desde 2023-01 --hasta 2025-12
    py scraper_02_calidad_normativa.py --desde 2023-01 --hasta 2025-12 --zip-local base-infoleg.zip

Requisitos: pip install pandas requests beautifulsoup4 lxml  (+ infoleg_source.py)
"""
from __future__ import annotations

import argparse
import calendar
import json
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

RESULT_URL = "https://www.hcdn.gob.ar/proyectos/resultado.html"
REFERER = "https://www.hcdn.gob.ar/proyectos/"
USER_AGENT = "ICIA-LyP/0.1 (indicador calidad institucional; politicaspublicas@libertadyprogreso.org)"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
CACHE_FILE = OUTPUT_DIR / "_cache_congreso.json"
THROTTLE = 2.5
TIPOS_SIMBOLICOS = ["declaracion", "resolucion", "comunicacion"]
TOTAL_RE = re.compile(r"([\d.]+)\s+Proyectos?\s+Encontrados", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("calidad_normativa")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=3.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET", "POST"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update({"User-Agent": USER_AGENT, "Referer": REFERER,
                      "Accept-Language": "es-AR,es;q=0.9",
                      "Origin": "https://www.hcdn.gob.ar"})
    return s


def count_presentados(s: requests.Session, tipo: str, desde: str, hasta: str):
    """Total de proyectos de un tipo con fecha de ingreso en [desde, hasta] (DD/MM/AAAA)."""
    payload = {
        "zezion": "true", "strTipo": tipo,
        "strNumExp": "", "strNumExpOrig": "", "strNumExpAnio": "",
        "strCamIni": "", "strFirmante": "", "strTipoFirmante": "",
        "strComision": "", "strFechaInicio": desde, "strFechaFin": hasta,
        "strPalabras": "", "strOrdenDelDiaNro": "", "strOrdenDelDiaAnio": "",
        "strLey": "", "strSancionDefinitiva": "", "strCantPagina": "10",
    }
    try:
        resp = s.post(RESULT_URL, data=payload, timeout=60)
        if resp.status_code != 200:
            return None
        m = TOTAL_RE.search(BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True))
        return int(m.group(1).replace(".", "")) if m else None
    except Exception as e:  # noqa: BLE001
        log.warning("Fallo %s %s..%s: %s", tipo, desde, hasta, type(e).__name__)
        return None


# --------------------------------------------------------------------------- #
class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.d = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v):
        self.d[k] = v

    def save(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.d), encoding="utf-8")


def leyes_sancionadas(zip_local: str | None, periods) -> pd.Series:
    """Leyes sancionadas por mes (InfoLEG, por fecha de SANCIÓN)."""
    df = load_infoleg_df(zip_local=zip_local)
    ley = df[df["tipo_norma"] == "Ley"].copy()
    fs = pd.to_datetime(ley["fecha_sancion"], errors="coerce", format="ISO8601")
    fs = fs.where(fs <= pd.Timestamp.today().normalize())
    per = fs.dt.to_period("M")
    cnt = per.value_counts()
    return pd.Series({p: int(cnt.get(p, 0)) for p in periods}, name="n_leyes_sancionadas")


def harvest_simbolicos(periods, cache: Cache) -> pd.DataFrame:
    s = session()
    data = {t: [] for t in TIPOS_SIMBOLICOS}
    total = len(periods) * len(TIPOS_SIMBOLICOS)
    i = 0
    for p in periods:
        y, mth = p.year, p.month
        desde = f"01/{mth:02d}/{y}"
        hasta = f"{calendar.monthrange(y, mth)[1]:02d}/{mth:02d}/{y}"
        for t in TIPOS_SIMBOLICOS:
            i += 1
            key = f"{t}|{p}"
            val = cache.get(key)
            if val is None:
                val = count_presentados(s, t, desde, hasta)
                cache.set(key, val)
                if i % 10 == 0:
                    cache.save()
                    log.info("  progreso %s/%s", i, total)
                time.sleep(THROTTLE)
            data[t].append(val)
    cache.save()
    idx = [str(p) for p in periods]
    return pd.DataFrame({f"n_{t}_pres": data[t] for t in TIPOS_SIMBOLICOS}, index=idx)


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 2 — Calidad Normativa (producción)")
    ap.add_argument("--desde", required=True, help="AAAA-MM")
    ap.add_argument("--hasta", required=True, help="AAAA-MM")
    ap.add_argument("--zip-local", help="ZIP InfoLEG ya descargado")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    periods = list(pd.period_range(args.desde, args.hasta, freq="M"))
    log.info("Ventana: %s meses (%s..%s)", len(periods), args.desde, args.hasta)

    log.info("1/2 — Leyes sancionadas desde InfoLEG...")
    try:
        ser_leyes = leyes_sancionadas(args.zip_local, periods)
    except Exception as e:  # noqa: BLE001
        log.error("Fallo InfoLEG: %s", e)
        return 1

    log.info("2/2 — Simbólicos presentados desde HCDN (%s consultas, con caché)...",
             len(periods) * len(TIPOS_SIMBOLICOS))
    cache = Cache(CACHE_FILE)
    df_sim = harvest_simbolicos(periods, cache)

    out = df_sim.copy()
    out.insert(0, "n_leyes_sancionadas", [ser_leyes[p] for p in periods])
    out["n_simbolicas_pres"] = out[[f"n_{t}_pres" for t in TIPOS_SIMBOLICOS]].sum(axis=1, min_count=1)
    out = out.reset_index(names="periodo")

    # validación: cuántas celdas simbólicas fallaron (None)
    faltantes = out[[f"n_{t}_pres" for t in TIPOS_SIMBOLICOS]].isna().sum().sum()
    if faltantes:
        log.warning("VALIDACIÓN: %s celdas simbólicas sin dato (reintentá: usa caché).", int(faltantes))
    else:
        log.info("Validación OK: todas las celdas con dato.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"calidad_normativa_mensual_{stamp}.csv"
    out.to_csv(out_csv, index=False, encoding="utf-8")

    print("\n=== RESUMEN ANUAL (sanity) ===")
    tmp = out.copy()
    tmp["anio"] = tmp["periodo"].str[:4]
    print(tmp.groupby("anio")[["n_leyes_sancionadas", "n_declaracion_pres",
                               "n_resolucion_pres", "n_comunicacion_pres"]].sum().to_string())
    print("\n=== DataFrame mensual (cola) ===")
    print(out.tail(15).to_string(index=False))
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
