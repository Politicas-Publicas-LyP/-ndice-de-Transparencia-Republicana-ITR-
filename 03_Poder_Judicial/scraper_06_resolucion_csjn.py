"""
ICIA — Módulo 6: Resolución de Conflictos por la CSJN (Poder Judicial, 8%)
===========================================================================
Mide si la Corte Suprema efectivamente resuelve las causas que ingresan o acumula
atraso. Métrica: tasa_resolucion = casos_resueltos / casos_ingresados por año.
Más alto = la Corte sigue el ritmo; bajo = se atasca (stock pendiente creciente).

Fuente: Anuarios Estadísticos oficiales de la CSJN (PDF), que publican casos
ingresados y resueltos por año. Cifras en prosa, auto-extraíbles. (El conteo mensual
del buscador de fallos se descartó: SPA/JSF con CAPTCHA + noindex, y mezcla
inadmisibles/280 → proxy frágil y ruidoso, contra el premortem.)

NATURALEZA: estructural/anual (frecuencia del anuario). Se lleva a serie mensual por
forward-fill con stale_flag. Normalización/peso en Sprint 6.

Uso:
    py scraper_06_resolucion_csjn.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests pdfplumber
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://www.csjn.gov.ar/archivos/estadisticas/informe_anuario_CSJN_{anio}.pdf"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept": "*/*", "Accept-Language": "es-AR,es;q=0.9"}

# Cifras oficiales verificadas (anuarios CSJN) como fallback/validación del auto-parse.
CSJN_VERIFICADO = {2024: (45678, 19056), 2025: (58428, 26524)}
# Mediana de duración de los casos resueltos (días corridos) — celeridad general. Verificado.
MEDIANA_VERIFICADA = {2024: 385, 2025: 364}
MEDIANA_PATTERNS = [r"mediana\d*,?\s*que dio como\s+resultado\s+([\d.]+)\s*d[ií]as",
                    r"resultado\s+([\d.]+)\s*d[ií]as"]
# Duración de los JUICIOS ORIGINARIOS (días corridos) — atención a la competencia principal
# (art. 117 CN) en plazo prudencial. Es la categoría más lenta de la Corte. Verificado.
ORIGINARIA_VERIFICADA = {2024: 2689, 2025: 2082}
ORIGINARIA_PATTERNS = [r"([\d.]{3,5})\s*d[ií]as[^0-9]{0,60}?juicios originarios",
                       r"juicios originarios[^0-9]{0,40}?([\d.]{3,5})\s*d[ií]as"]

# Composición de la CSJN: miembros en ejercicio (de 5). VERIFICAR/EDITAR (hecho institucional):
#   2021-11 → 2024-12: 4 miembros (vacante por renuncia de Highton)
#   desde 2025-01 (cese de Maqueda, 29/12/2024): 3 miembros — pliegos Lijo/García-Mansilla no prosperaron.
TOTAL_MIEMBROS_CSJN = 5
CSJN_MIEMBROS_REGLAS = [("2025-01", 3), ("1900-01", 4)]   # (desde_periodo, miembros), de más reciente a viejo


def csjn_miembros(p: pd.Period) -> int:
    for desde, m in CSJN_MIEMBROS_REGLAS:
        if p >= pd.Period(desde, "M"):
            return m
    return 4

RES_PATTERNS = [
    r"se resolvieron\s+([\d.]+)\s+casos",
    r"total de casos resueltos en el [úu]ltimo a[ñn]o fue de\s+([\d.]+)",
    r"para los\s+([\d.]+)\s+casos resueltos",
]
ING_PATTERNS = [
    r"([\d.]+)\s+casos ingresados en el [úu]ltimo a[ñn]o",
    r"promedio de\s+([\d.]+)\s+casos ingresados por mes",  # ×12
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("resolucion_csjn")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def _num(s: str) -> int:
    return int(s.replace(".", ""))


def parse_anuario(anio: int, s: requests.Session) -> tuple[int, int] | None:
    """Devuelve (ingresados, resueltos) del anuario del año, o None si no existe."""
    try:
        resp = s.get(BASE.format(anio=anio), timeout=90)
    except Exception as e:  # noqa: BLE001
        log.warning("CSJN %s: fallo %s", anio, e)
        return None
    if resp.status_code != 200 or "pdf" not in resp.headers.get("Content-Type", "").lower():
        log.info("CSJN %s: sin anuario PDF (HTTP %s)", anio, resp.status_code)
        return None
    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
        full = "\n".join((p.extract_text() or "") for p in pdf.pages)

    res = ing = mediana = None
    for pat in RES_PATTERNS:
        m = re.search(pat, full, re.IGNORECASE)
        if m:
            res = _num(m.group(1))
            break
    for i, pat in enumerate(ING_PATTERNS):
        m = re.search(pat, full, re.IGNORECASE)
        if m:
            ing = _num(m.group(1)) * (12 if i == 1 else 1)  # 2º patrón es promedio mensual
            break
    for pat in MEDIANA_PATTERNS:
        m = re.search(pat, full, re.IGNORECASE | re.DOTALL)
        if m:
            v = _num(m.group(1))
            if 30 <= v <= 1500:   # rango plausible de días
                mediana = v
                break
    orig_dias = None
    for pat in ORIGINARIA_PATTERNS:
        m = re.search(pat, full, re.IGNORECASE | re.DOTALL)
        if m:
            v = _num(m.group(1))
            if 500 <= v <= 5000:
                orig_dias = v
                break

    # validación contra cifras verificadas
    if anio in CSJN_VERIFICADO:
        v_ing, v_res = CSJN_VERIFICADO[anio]
        if res is None or abs(res - v_res) > max(50, 0.02 * v_res):
            log.warning("CSJN %s: resueltos auto=%s vs verificado=%s -> uso verificado", anio, res, v_res)
            res = v_res
        if ing is None or abs(ing - v_ing) > max(100, 0.03 * v_ing):
            log.warning("CSJN %s: ingresados auto=%s vs verificado=%s -> uso verificado", anio, ing, v_ing)
            ing = v_ing
    if anio in MEDIANA_VERIFICADA:
        v_med = MEDIANA_VERIFICADA[anio]
        if mediana is None or abs(mediana - v_med) > 40:
            log.warning("CSJN %s: mediana auto=%s vs verificada=%s -> uso verificada", anio, mediana, v_med)
            mediana = v_med
    if anio in ORIGINARIA_VERIFICADA:
        v_o = ORIGINARIA_VERIFICADA[anio]
        if orig_dias is None or abs(orig_dias - v_o) > 200:
            log.warning("CSJN %s: orig_dias auto=%s vs verificada=%s -> uso verificada", anio, orig_dias, v_o)
            orig_dias = v_o
    if res is None or ing is None:
        log.warning("CSJN %s: no se pudo extraer (ing=%s, res=%s)", anio, ing, res)
        return None
    log.info("CSJN %s: ingresados=%s resueltos=%s tasa=%.3f | mediana=%s | originaria_dias=%s",
             anio, ing, res, res / ing, mediana, orig_dias)
    return ing, res, mediana, orig_dias


def to_monthly(anuarios: dict[int, tuple], desde: str, hasta: str) -> pd.DataFrame:
    periods = pd.period_range(desde, hasta, freq="M")
    rows = []
    for p in periods:
        usable = [y for y in anuarios if y <= p.year]
        if not usable:
            rows.append({"periodo": str(p), "casos_ingresados": float("nan"),
                         "casos_resueltos": float("nan"), "tasa_resolucion": float("nan"),
                         "mediana_dias": float("nan"), "stale_meses": float("nan")})
            continue
        y = max(usable)
        ing, res, med, orig = anuarios[y]
        stale = 0 if y == p.year else (p - pd.Period(f"{y}-12", "M")).n
        miembros = csjn_miembros(p)
        rows.append({"periodo": str(p), "casos_ingresados": ing, "casos_resueltos": res,
                     "tasa_resolucion": round(res / ing, 4),
                     "mediana_dias": (float(med) if med else float("nan")),
                     "originaria_dias": (float(orig) if orig else float("nan")),
                     "csjn_miembros": miembros, "csjn_vacantes": TOTAL_MIEMBROS_CSJN - miembros,
                     "stale_meses": stale})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 6 — Resolución CSJN")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    anios = list(range(int(args.desde[:4]), int(args.hasta[:4]) + 1))
    anuarios = {}
    for anio in anios:
        r = parse_anuario(anio, s)
        if r:
            anuarios[anio] = r
    if not anuarios:
        log.error("No se obtuvo ningún anuario.")
        return 1

    print("\n=== ANUARIOS (auditar) ===")
    for y in sorted(anuarios):
        ing, res, med, orig = anuarios[y]
        print(f"  {y}: ingresados={ing:,} | resueltos={res:,} | tasa={res/ing:.3f} | "
              f"mediana_dias={med} | originaria_dias={orig}")

    serie = to_monthly(anuarios, args.desde, args.hasta)
    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"resolucion_csjn_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
