"""
ITR — Módulos 18 y 19: Balance del BCRA (Banco Central)
=======================================================
Una sola fuente (balance del BCRA, saldos a fin de mes -> balbcrhis.xls) alimenta las
dos variables monetarias de dato:
  (18) Financiamiento monetario del déficit = Adelantos transitorios / Base monetaria. Ideal 0.
  (19) Letras intransferibles por reservas   = Sector oficial en moneda extranjera
       (incluye Letra Intransferible del Tesoro, nota 15) / Total del activo. Ideal 0.
Ambos son SHARES (invariantes a la inflación). Cols (hoja 'B.C.R.A.'): 15=Adelantos,
20=Sector oficial m/extranjera (letras), 24=Total del activo, 37=Base monetaria.
Período en col 0 = AAAA.MM. Usa la copia cacheada output/_balbcrhis.xls si existe.

Uso: py scraper_18_bcra_balance.py
Requisitos: py -m pip install pandas xlrd openpyxl requests
"""
from __future__ import annotations
import logging, sys
from datetime import datetime
from pathlib import Path
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/balbcrhis.xls"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
CACHE = OUTPUT_DIR / "_balbcrhis.xls"
HEADERS = {"User-Agent": "ITR-LyP/0.1 (politicaspublicas@libertadyprogreso.org)"}
C_PER, C_ADEL, C_LETRAS, C_ACTIVO, C_BASE = 0, 15, 20, 24, 37

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bcra_bal")


def _descargar():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2.5,
            status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset(["GET"]))))
    s.headers.update(HEADERS)
    try:
        r = s.get(URL, timeout=180); r.raise_for_status()
        CACHE.write_bytes(r.content)
        return True
    except Exception as e:
        log.error("Fallo la descarga (%s). Probar desde IP argentina.", e)
        return False


def _periodo(v):
    if not isinstance(v, (int, float)) or pd.isna(v):
        return None
    y = int(v); m = round((v - y) * 100)
    if not (1 <= m <= 12) or not (1990 <= y <= 2035):
        return None
    return f"{y}-{m:02d}"


def _f(x):
    return x if isinstance(x, (int, float)) and not pd.isna(x) else None


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    if not CACHE.exists():
        log.info("Descargando %s ...", URL)
        if not _descargar():
            return 1
    else:
        log.info("Usando copia cacheada: %s", CACHE.name)

    df = pd.ExcelFile(CACHE).parse("B.C.R.A.", header=None)
    head15 = " ".join(str(df.iat[r, C_ADEL]) for r in range(17, 25)).lower()
    if "adelanto" not in head15:
        log.warning("La col %d no parece 'Adelantos transit.' Revisar estructura.", C_ADEL)

    fin_rows, let_rows = [], []
    for r in range(27, df.shape[0]):
        per = _periodo(df.iat[r, C_PER])
        if per is None:
            continue
        adel, letras, activo, base = _f(df.iat[r, C_ADEL]), _f(df.iat[r, C_LETRAS]), _f(df.iat[r, C_ACTIVO]), _f(df.iat[r, C_BASE])
        if base and adel is not None:
            fin_rows.append({"periodo": per, "financiamiento": round(adel / base, 6), "adelantos": adel, "base_monetaria": base})
        if activo and letras is not None:
            let_rows.append({"periodo": per, "letras_share": round(letras / activo, 6), "letras": letras, "activo_total": activo})

    if not fin_rows or not let_rows:
        log.error("No se extrajeron filas (estructura cambiada?).")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fin = pd.DataFrame(fin_rows); let = pd.DataFrame(let_rows)
    fin_csv = OUTPUT_DIR / f"bcra_financiamiento_mensual_{stamp}.csv"
    let_csv = OUTPUT_DIR / f"bcra_letras_mensual_{stamp}.csv"
    fin.to_csv(fin_csv, index=False, encoding="utf-8")
    let.to_csv(let_csv, index=False, encoding="utf-8")
    print("\n=== FINANCIAMIENTO AL TESORO (Adelantos/Base) — cola ===")
    print(fin.tail(8).to_string(index=False))
    print("\n=== LETRAS INTRANSFERIBLES (/Activo) — cola ===")
    print(let.tail(8).to_string(index=False))
    log.info("CSV: %s | %s", fin_csv.name, let_csv.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
