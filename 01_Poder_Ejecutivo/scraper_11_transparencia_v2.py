"""
ICIA — Módulo 11: Transparencia v2 — Tasa de respuesta a pedidos de AIP
=======================================================================
Reemplaza el Índice de Transparencia de la AAIP (saturaba en 100) por la TASA DE
RESPUESTA a pedidos de acceso a la información (Ley 27.275): proporción de solicitudes
efectivamente respondidas (idealmente en plazo) sobre las que ya vencieron su término.
Signo: más respuestas en plazo = mejor (menor asimetría de información).

Fuente: microdato AAIP, una fila por solicitud (descarga.aaip.gob.ar/dataset/sip.csv).
Columnas clave: estado, estado_del_tramite, fecha_de_inicio, plazo (días hábiles),
sujeto_obligado. Cobertura: PEN, 2017-2026, trimestral.

DIAGNÓSTICO-PRIMERO: el diccionario oficial no enumera los valores de 'estado', así que
esta corrida vuelca los valores únicos para fijar la clasificación 'respondida' vs.
'en trámite/vencida'. Hace además un primer cálculo de tasa con heurística, a validar.

Uso:
    py scraper_11_transparencia_v2.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://descarga.aaip.gob.ar/dataset/sip.csv"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept": "*/*", "Accept-Language": "es-AR,es;q=0.9"}
PLAZO_LEGAL = 15   # días hábiles (prorrogable a 30)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("transparencia_v2")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=4, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def load() -> pd.DataFrame:
    s = session()
    resp = s.get(URL, timeout=180)
    resp.raise_for_status()
    blob = resp.content
    for enc in ("utf-8", "latin-1"):
        for sep in (",", ";"):
            try:
                df = pd.read_csv(io.BytesIO(blob), sep=sep, encoding=enc, dtype=str,
                                 low_memory=False, on_bad_lines="skip")
                if df.shape[1] > 5:
                    log.info("CSV parseado enc=%s sep='%s' -> %s filas, %s cols", enc, sep, len(df), df.shape[1])
                    return df
            except Exception:  # noqa: BLE001
                continue
    raise RuntimeError("No se pudo parsear sip.csv")


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 11 — Transparencia v2 (tasa de respuesta AIP)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        df = load()
    except Exception as e:  # noqa: BLE001
        log.error("Fallo al descargar/parsear: %s", e)
        return 1

    print("\n=== DIAGNÓSTICO (devolver) ===")
    print("Columnas:", list(df.columns))
    for col in ("estado", "estado_del_tramite"):
        if col in df.columns:
            print(f"\n--- Valores únicos de '{col}' (top 25) ---")
            print(df[col].value_counts(dropna=False).head(25).to_string())
    if "plazo" in df.columns:
        pl = pd.to_numeric(df["plazo"], errors="coerce")
        print(f"\n--- plazo (días hábiles): min={pl.min()} med={pl.median()} max={pl.max()} NaN={pl.isna().sum()}")
    if "fecha_de_inicio" in df.columns:
        f = pd.to_datetime(df["fecha_de_inicio"], errors="coerce", dayfirst=True)
        print(f"--- fecha_de_inicio: min={f.min()} max={f.max()}")

    # Clasificación por la columna 'estado' (valores reales: Resuelto/Vencido/En plazo/En prórroga)
    est = df["estado"].astype(str).str.strip().str.lower()
    df["_resuelto"] = est.eq("resuelto")
    df["_vencido"] = est.eq("vencido")
    df["_concluido"] = df["_resuelto"] | df["_vencido"]          # término ya cumplido
    df["_pendiente"] = est.isin(["en plazo", "en prórroga", "en prorroga"])
    df["_plazo"] = pd.to_numeric(df.get("plazo"), errors="coerce")
    df["_en_plazo"] = df["_resuelto"] & (df["_plazo"] <= PLAZO_LEGAL)
    df["_fecha"] = pd.to_datetime(df.get("fecha_de_inicio"), errors="coerce", format="ISO8601")

    print(f"\n--- Conteos: Resuelto={int(df['_resuelto'].sum())} | Vencido={int(df['_vencido'].sum())} "
          f"| pendiente={int(df['_pendiente'].sum())} | resuelto en plazo (≤{PLAZO_LEGAL}d)={int(df['_en_plazo'].sum())}")

    d = df.dropna(subset=["_fecha"]).copy()
    d["periodo"] = d["_fecha"].dt.to_period("M")
    g = d.groupby("periodo").agg(
        n_total=("_resuelto", "size"),
        n_concluido=("_concluido", "sum"),
        n_resuelto=("_resuelto", "sum"),
        n_vencido=("_vencido", "sum"),
        n_en_plazo=("_en_plazo", "sum"),
    ).reset_index()
    g["tasa_respuesta"] = (g["n_resuelto"] / g["n_concluido"]).round(4)        # respondidas / concluidas
    g["tasa_en_plazo"] = (g["n_en_plazo"] / g["n_concluido"]).round(4)         # respondidas en plazo / concluidas
    g["madurez"] = (g["n_concluido"] / g["n_total"]).round(2)                  # % del cohorte ya concluido (vintage)
    # gate de madurez: meses con <85% concluido son provisorios -> NaN (no inventar señal sesgada)
    prov = g["madurez"] < 0.85
    g.loc[prov, ["tasa_respuesta", "tasa_en_plazo"]] = float("nan")
    g = g[(g["periodo"] >= pd.Period(args.desde, "M")) & (g["periodo"] <= pd.Period(args.hasta, "M"))]
    g["periodo"] = g["periodo"].astype(str)

    print("\n=== SERIE MENSUAL (por mes de inicio de la solicitud) ===")
    print(g[["periodo", "n_total", "n_concluido", "n_resuelto", "n_vencido",
             "tasa_respuesta", "tasa_en_plazo", "madurez"]].tail(18).to_string(index=False))
    print("\nNota: los últimos 1-2 meses son provisorios (madurez < 1: parte del cohorte sigue en plazo).")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"transparencia_v2_mensual_{stamp}.csv"
    g.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado: %s", out_csv)
    print("\n>>> Pegá los valores de 'estado'/'estado_del_tramite' para fijar la clasificación definitiva.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
