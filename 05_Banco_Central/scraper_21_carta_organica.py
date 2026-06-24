"""
ITR — Módulo 21: Respeto de la Carta Orgánica del BCRA [Banco Central]
=====================================================================
Mide la LEGALIDAD del financiamiento monetario del Tesoro, no su magnitud (eso ya lo
mide el módulo 18). El art. 20 de la Carta Orgánica (Ley 24.144) fija un TOPE a los
adelantos transitorios del BCRA al Gobierno:

    límite_legal = 0.12 * base_monetaria  +  0.10 * recursos_en_efectivo_12m

Desde la mirada liberal: respetar el límite legal es un freno republicano clave a la
emisión para financiar al fisco. Operacionalización:

    ratio  = adelantos_transitorios / límite_legal
    exceso = max(ratio - 1, 0)        # 0 = dentro de la ley ; >0 = excede el tope

En el ensamblador, 'carta_organica_exceso' se ancla 0.0 -> 100 (dentro de la ley) ;
0.5 -> 0 (excede el tope en 50% = colapso). Estar DENTRO del tope vale 100 sin importar
cuán grande sea el adelanto (la magnitud la penaliza el módulo 18).

FUENTES:
  - adelantos_transitorios y base_monetaria: del balance del BCRA, ya extraídos por el
    módulo 18 (bcra_financiamiento_mensual_*.csv: columnas 'adelantos' y 'base_monetaria').
  - recursos_en_efectivo_12m  (≈ recaudación nacional, suma móvil 12m). Definición
    operativa: recaudación tributaria nacional. Origen sugerido: Series de Tiempo de
    datos.gob.ar (apis.datos.gob.ar/series). Como el ID exacto debe CONFIRMARSE y este
    entorno no siempre alcanza datos.gob.ar, el módulo acepta tres modos, en orden:
       (a) CSV local  output/_recaudacion.csv  con columnas: periodo (AAAA-MM), recaudacion
       (b) Series de Tiempo, si se setea SERIE_RECAUDACION (no inventar; confirmar el ID)
       (c) MODO SIMPLE: si no hay recaudación, usa solo el componente 0.12*base
           (subestima el tope) y marca modo='simple' para auditar.

  >>> UNIDADES <<< adelantos, base_monetaria y recaudacion deben estar en la MISMA unidad
  nominal (p. ej. millones de $). Ajustar ESCALA_RECAUDACION si la serie viene en otra escala.

Uso:  py scraper_21_carta_organica.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import glob
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
RECA_CSV = OUTPUT_DIR / "_recaudacion.csv"

# Coeficientes del art. 20 (CONFIRMADO en InfoLEG, texto vigente sust. por Ley 26.739, B.O. 28/3/2012).
# Tope ordinario: 12% de la base monetaria + 10% de los recursos en efectivo de los últimos 12 meses.
# (Existe un 10% adicional EXCEPCIONAL por hasta 18 meses; NO se cuenta: medimos contra el tope ordinario.)
COEF_BASE = 0.12      # 12% de la base monetaria (circulación + depósitos a la vista en el BCRA)
COEF_RECURSOS = 0.10  # 10% de los recursos en efectivo de los últimos 12 meses

# Serie de recaudación (datos.gob.ar / Series de Tiempo). CONFIRMADO:
#   "172.3_TL_RECAION_M_0_0_17" = "Total recaudación", mensual, MILLONES de pesos
#   (Secretaría de Hacienda, Min. de Economía; 1997-01 en adelante).
# Es el proxy de "recursos en efectivo del Gobierno nacional" del art. 20.
SERIE_RECAUDACION = "172.3_TL_RECAION_M_0_0_17"
SERIES_API = "https://apis.datos.gob.ar/series/api/series/"
# El balance del BCRA está en MILES de pesos y la recaudación en MILLONES -> x1000 para igualar.
ESCALA_RECAUDACION = 1000.0

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("carta_organica")


def _latest(pattern: str) -> str | None:
    files = sorted(glob.glob(str(OUTPUT_DIR / f"{pattern}_*.csv")))
    return files[-1] if files else None


def cargar_balance() -> pd.DataFrame | None:
    f = _latest("bcra_financiamiento_mensual")
    if f is None:
        log.error("Falta bcra_financiamiento_mensual_*.csv. Corré antes el módulo 18.")
        return None
    df = pd.read_csv(f)
    need = {"periodo", "adelantos", "base_monetaria"}
    if not need.issubset(df.columns):
        log.error("El CSV del balance no tiene %s. Columnas: %s", need, list(df.columns))
        return None
    df = df[["periodo", "adelantos", "base_monetaria"]].copy()
    df["periodo"] = df["periodo"].astype(str)
    return df


def cargar_recaudacion(periods: pd.PeriodIndex) -> pd.Series | None:
    """Devuelve recaudacion_12m (suma móvil 12m) indexada por período, o None."""
    reca = None
    if RECA_CSV.exists():
        r = pd.read_csv(RECA_CSV)
        if {"periodo", "recaudacion"}.issubset(r.columns) and len(r.dropna()) > 0:
            reca = r.dropna().set_index(pd.PeriodIndex(r.dropna()["periodo"].astype(str), freq="M"))["recaudacion"]
            log.info("Recaudación: usando CSV local %s (%s meses).", RECA_CSV.name, len(reca))
        else:
            log.info("CSV local vacío/sin datos -> usando la API de Series de Tiempo.")
    if reca is not None and reca.index.min() > periods.min():
        log.info("CSV no cubre desde %s (empieza %s) -> uso la API para historia completa.",
                 periods.min(), reca.index.min()); reca = None
    if reca is None and SERIE_RECAUDACION:
        try:
            resp = requests.get(SERIES_API, params={"ids": SERIE_RECAUDACION, "format": "json",
                                                     "limit": 5000}, timeout=60)
            data = resp.json().get("data", [])
            reca = pd.Series({pd.Period(d[0][:7], "M"): float(d[1]) for d in data if d[1] is not None})
            log.info("Recaudación: Series de Tiempo %s (%s puntos).", SERIE_RECAUDACION, len(reca))
        except Exception as e:  # noqa: BLE001
            log.warning("Recaudación: fallo Series de Tiempo (%s).", e)
    if reca is None:
        return None
    reca = (reca * ESCALA_RECAUDACION).sort_index()
    reca12 = reca.rolling(12, min_periods=6).sum()
    return reca12.reindex(periods)


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 21 — Respeto de la Carta Orgánica (BCRA)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    bal = cargar_balance()
    if bal is None:
        return 1
    periods = pd.period_range(args.desde, args.hasta, freq="M")
    bal = bal.set_index(pd.PeriodIndex(bal["periodo"], freq="M")).reindex(periods)
    adel = pd.to_numeric(bal["adelantos"], errors="coerce")
    base = pd.to_numeric(bal["base_monetaria"], errors="coerce")

    reca12 = cargar_recaudacion(periods)
    if reca12 is not None and reca12.notna().any():
        limite = COEF_BASE * base + COEF_RECURSOS * reca12
        modo = "completo"
    else:
        limite = COEF_BASE * base
        modo = "simple"
        log.warning("Sin recaudación disponible -> MODO SIMPLE (solo %.0f%% de la base; subestima el tope). "
                    "Cargá output/_recaudacion.csv o seteá SERIE_RECAUDACION.", COEF_BASE * 100)

    ratio = (adel / limite).where(limite > 0)
    exceso = (ratio - 1).clip(lower=0)

    out = pd.DataFrame({
        "periodo": periods.astype(str),
        "carta_organica_ratio": ratio.round(4).values,
        "carta_organica_exceso": exceso.round(4).values,
        "adelantos": adel.values,
        "base_monetaria": base.values,
        "recaudacion_12m": (reca12.values if reca12 is not None else pd.NA),
        "modo": modo,
    })

    print(f"\n=== RESPETO DE LA CARTA ORGÁNICA (modo={modo}) — cola ===")
    print(out[["periodo", "carta_organica_ratio", "carta_organica_exceso"]].tail(12).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"carta_organica_mensual_{stamp}.csv"
    out.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado: %s", out_csv)
    if modo == "simple":
        log.warning("Modo SIMPLE: confirmá la serie de recaudación para el cálculo completo del art. 20.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
