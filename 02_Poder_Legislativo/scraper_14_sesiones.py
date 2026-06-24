"""
ICIA — Módulo 14: Sesiones del Congreso (Diputados) — cumplimiento del calendario
==================================================================================
Insumo para mejorar Calidad Normativa (Legislativo). Dos señales:
  - cumplimiento_sesiones = sesiones realizadas / sesiones citadas (¿el Congreso se reúne?)
  - n_sesiones_realizadas  = base para el ratio "leyes sustantivas por sesión" (se combina
    en el ensamblado con las leyes sustantivas del Módulo 2).
Signo: más cumplimiento = mejor (un Congreso que se reúne y sesiona).

Fuente: https://www.hcdn.gob.ar/sesiones/ (HTML server-side; lista todas las sesiones por
período, marcando "CITADA - NO EFECTUADA" / "CITADA - FRACASADA" / "Expresiones en Minoría"
= citadas pero no realizadas). Una sola página trae todos los períodos.

Uso:
    py scraper_14_sesiones.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests beautifulsoup4 lxml
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://www.hcdn.gob.ar/sesiones/"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept": "text/html", "Accept-Language": "es-AR,es;q=0.9"}
FECHA_RE = re.compile(r"\((\d{2}/\d{2}/\d{4})\)")
# texto que indica sesión citada pero NO realizada
NO_REALIZADA = re.compile(r"no efectuada|fracasada|en minor[ií]a", re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("sesiones")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=4, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def scrape(s: requests.Session) -> pd.DataFrame:
    resp = s.get(URL, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    rows = []
    for a in soup.find_all("a", href=True):
        if "sesion.html" not in a["href"]:
            continue
        txt = a.get_text(" ", strip=True)
        m = FECHA_RE.search(txt)
        if not m:
            continue
        try:
            fecha = pd.Timestamp(datetime.strptime(m.group(1), "%d/%m/%Y"))
        except ValueError:
            continue
        # "Asamblea Legislativa" (apertura presidencial) no es sesión de trabajo -> excluir
        if "asamblea legislativa" in txt.lower():
            continue
        rows.append({"fecha": fecha, "titulo": txt, "realizada": not bool(NO_REALIZADA.search(txt))})
    df = pd.DataFrame(rows).drop_duplicates(subset=["fecha", "titulo"])
    log.info("Sesiones (citadas) parseadas: %s | realizadas: %s", len(df), int(df["realizada"].sum()))
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 14 — Sesiones del Congreso")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    try:
        df = scrape(s)
    except Exception as e:  # noqa: BLE001
        log.error("Fallo: %s", e)
        return 1
    if df.empty:
        log.error("Sin sesiones (¿cambió el HTML?)."); return 1

    print("\n=== SESIONES NO REALIZADAS detectadas (auditar) ===")
    nr = df[~df["realizada"]].sort_values("fecha")
    print(nr.assign(fecha=nr["fecha"].dt.date)[["fecha", "titulo"]].tail(15).to_string(index=False))

    df["periodo"] = df["fecha"].dt.to_period("M")
    periods = pd.period_range(args.desde, args.hasta, freq="M")
    g = pd.DataFrame(index=periods)
    g["n_citadas"] = df["periodo"].value_counts().reindex(periods, fill_value=0)
    g["n_realizadas"] = df[df["realizada"]]["periodo"].value_counts().reindex(periods, fill_value=0)
    g["cit_12m"] = g["n_citadas"].rolling(12, min_periods=6).sum()
    g["real_12m"] = g["n_realizadas"].rolling(12, min_periods=6).sum()
    g["cumplimiento_sesiones"] = (g["real_12m"] / g["cit_12m"]).where(g["cit_12m"] > 0).round(4)
    g = g.reset_index(names="periodo"); g["periodo"] = g["periodo"].astype(str)

    print("\n=== RESUMEN ANUAL ===")
    t = df.copy(); t["a"] = t["fecha"].dt.year
    print(t.groupby("a").agg(citadas=("realizada", "size"), realizadas=("realizada", "sum")).to_string())
    print("\n=== SERIE MENSUAL (cola) ===")
    print(g[["periodo", "n_citadas", "n_realizadas", "cumplimiento_sesiones"]].tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"sesiones_mensual_{stamp}.csv"
    g.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
