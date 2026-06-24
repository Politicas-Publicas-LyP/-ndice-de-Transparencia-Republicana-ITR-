"""
ITR — Módulo 17: Designación del Presidente del BCRA (Banco Central)
====================================================================
Variable ESTRUCTURAL y BINARIA de independencia institucional del Banco Central.
La Carta Orgánica (Ley 24.144) y la CN exigen que el Presidente y el Directorio del
BCRA se designen CON ACUERDO DEL SENADO. Una designación "en comisión" (por decreto,
sin acuerdo) debilita la independencia y la legitimidad republicana de la autoridad
monetaria.

  designacion_acuerdo = 1  -> Presidente con acuerdo del Senado (pleno)
  designacion_acuerdo = 0  -> en comisión / sin acuerdo del Senado (penalizado)

Es un ESTADO PUNTUAL: en el ensamblador va en NO_SUAVIZAR (vale por entero el mes que
corresponde, no se promedia con el pasado). No requiere scraping: se mantiene con la
CONFIG editable de abajo. ACTUALIZAR/CONFIRMAR los tramos con el dato oficial
(decretos de designación en el Boletín Oficial y acuerdos del Senado).

Uso:
    py scraper_17_bcra_designacion.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

# ----------------------------------------------------------------------------
# TABLA MANTENIDA — valores verificados. Para actualizar ante una NUEVA designación,
# revisar los Acuerdos del Senado (pliegos): si hubo acuerdo -> 1, si fue por decreto
# / en comisión -> 0. Como la designación cambia cada varios años, se mantiene a mano
# (más robusto que scrapear el Senado en cada corrida).
# Cada tramo: (desde 'AAAA-MM', hasta 'AAAA-MM' o None=en curso, con_acuerdo 1/0, nombre, nota)
# ----------------------------------------------------------------------------
# Tramos históricos. acuerdo: 1=con acuerdo del Senado / 0=por decreto o en comisión.
# IMPORTANTE: las marcas de acuerdo previas a 2019 son SCAFFOLD y deben CONFIRMARSE con
# los pliegos del Senado antes de publicar el núcleo histórico.
CONFIG = [
    ("2002-12", "2004-09", 0, "Alfonso Prat-Gay", "CONFIRMAR acuerdo Senado"),
    ("2004-09", "2010-01", 0, "Martín Redrado", "CONFIRMAR acuerdo Senado"),
    ("2010-02", "2013-11", 0, "Mercedes Marcó del Pont", "CONFIRMAR acuerdo Senado"),
    ("2013-11", "2014-10", 0, "Juan Carlos Fábrega", "CONFIRMAR acuerdo Senado"),
    ("2014-10", "2015-12", 0, "Alejandro Vanoli", "CONFIRMAR acuerdo Senado"),
    ("2015-12", "2018-06", 0, "Federico Sturzenegger", "CONFIRMAR acuerdo Senado"),
    ("2018-06", "2018-09", 0, "Luis Caputo", "CONFIRMAR acuerdo Senado"),
    ("2018-09", "2019-12", 0, "Guido Sandleris", "CONFIRMAR acuerdo Senado"),
    ("2019-12", "2023-12", 0, "Miguel Pesce", "Designado por decreto, sin acuerdo del Senado"),
    ("2023-12", None,      0, "Santiago Bausili", "Designado por decreto / en comisión, sin acuerdo del Senado"),
]


def serie_mensual(desde: str, hasta: str) -> pd.DataFrame:
    idx = pd.period_range(desde, hasta, freq="M")
    val = pd.Series(pd.NA, index=idx, dtype="Int64")
    nombre = pd.Series("", index=idx)
    for d, h, flag, nom, _ in CONFIG:
        p0 = pd.Period(d, "M")
        p1 = idx.max() if h is None else pd.Period(h, "M")
        m = (idx >= p0) & (idx <= p1)
        val[m] = flag
        nombre[m] = nom
    return pd.DataFrame({"periodo": idx.astype(str),
                         "designacion_acuerdo": val.values,
                         "presidente": nombre.values})


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 17 — Designación Presidente BCRA")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    serie = serie_mensual(args.desde, args.hasta)

    print("\n=== DESIGNACIÓN PRESIDENTE BCRA ===")
    print(serie.drop_duplicates(subset=["designacion_acuerdo", "presidente"]).to_string(index=False))
    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(12).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"bcra_designacion_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\nCSV guardado en: {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
