"""
ITR — Módulo 18: Financiamiento monetario del déficit (Banco Central)
=====================================================================
Dominancia fiscal: asistencia del BCRA al Tesoro (transferencias de utilidades +
adelantos transitorios), que aparece como el factor "Sector Público" en la
explicación de la base monetaria. Desde la mirada liberal/austríaca: financiar el
déficit con emisión es un impuesto inflacionario encubierto y la violación más
profunda de la independencia monetaria. Ideal: 0 (sin dominancia fiscal).

  financiamiento = asistencia neta al Tesoro / base monetaria   (mensual)  [a fijar]

Fuente: BCRA, serie mensual "panhis.xls" (panorama histórico monetario), que
contiene la base monetaria y sus factores de explicación, incluido "Sector Público".

ESTE SCRIPT ES DE DESCUBRIMIENTO + EXTRACCIÓN BEST-EFFORT: baja el archivo, vuelca su
estructura (hojas, primeras filas, filas que matchean palabras clave) y, si ubica los
conceptos, calcula la serie. Con tu log local fijamos las celdas/filas exactas.

Uso:
    py scraper_18_bcra_financiamiento.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas xlrd openpyxl requests
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

URL = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/panhis.xls"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "ITR-LyP/0.1 (politicaspublicas@libertadyprogreso.org)"}
CLAVES = ["sector p", "base monet", "adelanto", "utilidad", "transitori", "tesoro", "letras intransf"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("bcra_fin")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=2.5, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 18 — Financiamiento BCRA al Tesoro (descubrimiento)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()
    OUTPUT_DIR.mkdir(exist_ok=True)

    log.info("Descargando %s ...", URL)
    try:
        resp = session().get(URL, timeout=180)
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        log.error("Fallo la descarga (%s). ¿Bloqueo de IP? Probar desde IP argentina.", e)
        return 1
    raw = resp.content
    (OUTPUT_DIR / "_panhis.xls").write_bytes(raw)
    log.info("Descargado: %.1f KB", len(raw) / 1024)

    # intentar abrir con xlrd (.xls) o engine por defecto
    try:
        xls = pd.ExcelFile(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        log.error("No se pudo abrir el .xls (%s). Instalar: pip install xlrd", e)
        return 1

    print("\n=== HOJAS ===")
    for sh in xls.sheet_names:
        try:
            df = xls.parse(sh, header=None, nrows=40)
            print(f"\n--- HOJA '{sh}'  (shape vista {df.shape}) ---")
            # filas con palabras clave
            for i, row in df.iterrows():
                txt = " ".join(str(x) for x in row.tolist() if pd.notna(x)).lower()
                if any(k in txt for k in CLAVES):
                    cells = [str(x) for x in row.tolist() if pd.notna(x)]
                    print(f"  fila {i}: {cells[:8]}")
        except Exception as e:  # noqa: BLE001
            print(f"  (no se pudo parsear hoja {sh}: {e})")

    print("\n=== SIGUIENTE PASO ===")
    print("Pegá esta salida: con la ubicación de 'Sector Público' y 'Base monetaria'")
    print("fijo la extracción y el cálculo financiamiento/base monetaria.")
    print(f"(copia local del archivo: {OUTPUT_DIR / '_panhis.xls'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
