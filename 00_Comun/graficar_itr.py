"""
ITR — Gráfico desagregado de los 5 ejes (componente estándar de los informes)
=============================================================================
Genera el gráfico de líneas con los 5 sub-índices (Ejecutivo, Legislativo, Judicial,
Prensa, Banco Central) + la línea del ITR, a partir de cualquier salida del ensamblador.
Sirve para el ITR mensual (itr_mensual.csv, col 'ITR', eje x = periodo) y para el núcleo
histórico anual (itr_nucleo_anual.csv, col 'ITR_nucleo', eje x = anio).

Uso:
    py graficar_itr.py                                  # mensual (output/itr_mensual.csv)
    py graficar_itr.py --csv ../output/itr_nucleo_anual.csv --itr-col ITR_nucleo \
        --salida ../Documentos/ITR_nucleo.png --titulo "ITR — Núcleo histórico"
Requisitos: pip install pandas matplotlib
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
EJES = [("sub_Ejecutivo", "Ejecutivo", "#C8102E"),
        ("sub_Legislativo", "Legislativo", "#1f77b4"),
        ("sub_Judicial", "Judicial", "#7f3f98"),
        ("sub_Prensa", "Prensa", "#2ca02c"),
        ("sub_Banco Central", "Banco Central", "#ff7f0e")]


def graficar(csv, itr_col="ITR", salida=None, titulo="Índice de Transparencia Republicana (ITR)",
             desde=None, hasta=None):
    d = pd.read_csv(csv)
    if "periodo" in d.columns and desde:
        d = d[d["periodo"] >= desde]
    if "periodo" in d.columns and hasta:
        d = d[d["periodo"] <= hasta]
    d = d.reset_index(drop=True)
    if "anio" in d.columns:
        x = d["anio"].astype(int); xlab = None; rot = 0
    else:
        x = pd.PeriodIndex(d["periodo"], freq="M").to_timestamp(); xlab = None; rot = 0
    d = d[d[itr_col].notna()]
    x = x[d.index]
    fig, ax = plt.subplots(figsize=(10, 5.6))
    for col, lab, c in EJES:
        if col in d.columns:
            ax.plot(x, d[col], marker="o", ms=3, linewidth=1.8, label=lab, color=c)
    ax.plot(x, d[itr_col], marker="s", ms=4, linewidth=3.2, color="black", label="ITR", zorder=5)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Score 0-100 (distancia al ideal republicano)", fontsize=9)
    ax.set_title(titulo, fontsize=13, fontweight="bold", color="#C8102E")
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)
    ax.legend(ncol=3, fontsize=8.5, loc="lower center", framealpha=0.9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out = salida or str(OUTPUT_DIR / "itr_grafico.png")
    fig.savefig(out, dpi=160)
    print("Gráfico guardado:", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(OUTPUT_DIR / "itr_mensual.csv"))
    ap.add_argument("--itr-col", default="ITR")
    ap.add_argument("--salida", default=None)
    ap.add_argument("--titulo", default="Índice de Transparencia Republicana (ITR)")
    ap.add_argument("--desde", default=None); ap.add_argument("--hasta", default=None)
    a = ap.parse_args()
    graficar(a.csv, a.itr_col, a.salida, a.titulo, a.desde, a.hasta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
