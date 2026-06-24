"""
ICIA — Módulo 7: Escrutinio Abierto (Prensa Institucional, 8%)
==============================================================
Mide si el gobierno se expone al escrutinio periodístico (CONFERENCIAS DE PRENSA,
donde enfrenta preguntas) o comunica sin escrutinio (CADENAS NACIONALES, monólogo
de difusión obligatoria). Más conferencias relativo a cadenas = más apertura.

  escrutinio = n_conferencias / (n_conferencias + n_cadenas)   ∈ [0,1]

Fuente: Casa Rosada (Joomla, HTML server-side estable, sin anti-bot).
  - Conferencias: /informacion/conferencias (se filtran las "conferencia de prensa")
  - Cadenas: dentro de /informacion/discursos, títulos con "Cadena Nacional"
Paginado ?start=N (40 por página). Series crudas; normalización en Sprint 6.

Uso:
    py scraper_07_escrutinio.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests beautifulsoup4 lxml
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

BASE = "https://www.casarosada.gob.ar/informacion/{seccion}"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept-Language": "es-AR,es;q=0.9"}
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}
FECHA_RE = re.compile(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("escrutinio")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def _parse_fecha(texto: str) -> pd.Timestamp | None:
    m = FECHA_RE.search(texto)
    if not m:
        return None
    dia, mes, anio = int(m.group(1)), MESES.get(m.group(2).lower()), int(m.group(3))
    if not mes:
        return None
    try:
        return pd.Timestamp(anio, mes, dia)
    except ValueError:
        return None


def scrape(seccion: str, desde: pd.Timestamp, s: requests.Session) -> pd.DataFrame:
    """Recorre el listado paginado hasta pasar la fecha 'desde'. Devuelve fecha+título."""
    href_re = re.compile(rf"/informacion/{seccion}/\d+-")
    rows, start, vacios = [], 0, 0
    while True:
        url = BASE.format(seccion=seccion) + (f"?start={start}" if start else "")
        try:
            resp = s.get(url, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("%s start=%s: %s", seccion, start, e)
            break
        soup = BeautifulSoup(resp.text, "lxml")
        enlaces = [a for a in soup.find_all("a", href=True) if href_re.search(a["href"])]
        if not enlaces:
            break
        page_min = None
        for a in enlaces:
            txt = a.get_text(" ", strip=True)
            f = _parse_fecha(txt)
            if f is None:
                continue
            rows.append({"fecha": f, "titulo": txt, "url": a["href"]})
            page_min = f if page_min is None else min(page_min, f)
        log.info("%s start=%s: %s entradas (más vieja %s)", seccion, start, len(enlaces),
                 page_min.date() if page_min else "?")
        if page_min is not None and page_min < desde:
            break
        start += 40
        if start > 2000:  # tope de seguridad
            break
        time.sleep(0.8)
    df = pd.DataFrame(rows).drop_duplicates(subset="url")
    return df


def build(conf: pd.DataFrame, disc: pd.DataFrame, desde: str, hasta: str) -> pd.DataFrame:
    # conferencias de prensa (exposición a preguntas)
    es_conf = conf["titulo"].str.contains("conferencia de prensa", case=False, na=False)
    confp = conf[es_conf].copy()
    # cadenas nacionales (comunicación sin escrutinio)
    es_cad = disc["titulo"].str.contains("cadena nacional", case=False, na=False)
    cad = disc[es_cad].copy()

    periods = pd.period_range(desde, hasta, freq="M")
    cper = confp["fecha"].dt.to_period("M").value_counts()
    dper = cad["fecha"].dt.to_period("M").value_counts()
    serie = pd.DataFrame(index=periods)
    serie["n_conferencias"] = [int(cper.get(p, 0)) for p in periods]
    serie["n_cadenas"] = [int(dper.get(p, 0)) for p in periods]
    serie["conf_12m"] = serie["n_conferencias"].rolling(12, min_periods=6).sum()
    serie["cad_12m"] = serie["n_cadenas"].rolling(12, min_periods=6).sum()
    denom = serie["conf_12m"] + serie["cad_12m"]
    serie["escrutinio_12m"] = (serie["conf_12m"] / denom).where(denom > 0)
    serie = serie.reset_index(names="periodo")
    serie["periodo"] = serie["periodo"].astype(str)
    return serie, confp, cad


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 7 — Escrutinio Abierto")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    desde_ts = pd.Timestamp(args.desde + "-01")
    log.info("Scrapeando conferencias...")
    conf = scrape("conferencias", desde_ts, s)
    log.info("Scrapeando discursos (para cadenas)...")
    disc = scrape("discursos", desde_ts, s)
    log.info("Conferencias totales: %s | discursos totales: %s", len(conf), len(disc))

    serie, confp, cad = build(conf, disc, args.desde, args.hasta)

    print("\n=== CADENAS NACIONALES DETECTADAS (auditar) ===")
    print(cad.assign(fecha=cad["fecha"].dt.date).sort_values("fecha")[["fecha", "titulo"]]
          .to_string(index=False) if len(cad) else "  (ninguna)")
    print(f"\nConferencias de prensa detectadas: {len(confp)} | Cadenas: {len(cad)}")

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"escrutinio_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
