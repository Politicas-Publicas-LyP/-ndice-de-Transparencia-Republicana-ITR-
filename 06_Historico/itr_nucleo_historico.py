"""
ITR — NÚCLEO HISTÓRICO (anual, 2003+)
=====================================
Versión histórica y ANUAL del ITR para mostrar la evolución entre gobiernos. Usa SOLO
las variables con serie larga y consistente, balanceadas entre los 5 ejes, y aplica la
MISMA escala anclada al ideal que el ITR completo. Etiquetar como subconjunto histórico,
separado del ITR mensual (16 variables, desde 2023).

Lee los CSV de output/ (los mismos scrapers, corridos con --desde 2003-01), los lleva a
frecuencia ANUAL (promedio del año) y ensambla. Reporta, por año, cuántos ejes y variables
están cubiertos: el núcleo "balanceado" empieza el año en que hay >=1 variable por eje.

Variables EXCLUIDAS del núcleo (series cortas): Transparencia AAIP (2017+), Causas FOPEA,
Escrutinio, Acceso de la prensa (FOPEA solo 2023+, rompería la comparabilidad larga).
Cobertura judicial entra desde 2017 (snapshots). INCLUIDA: Respeto Carta Orgánica (BCRA),
con historia larga (balance BCRA 1990+ y recaudación 1997+).

Uso: py itr_nucleo_historico.py --desde 2003 --hasta 2026
Requisitos: pip install pandas
"""
from __future__ import annotations
import argparse, glob, sys
from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
MACRO = {"Ejecutivo": 0.30, "Legislativo": 0.20, "Judicial": 0.20, "Prensa": 0.15, "Banco Central": 0.15}
EPS = 1e-9

# (archivo|__derived__, columna, v_best, v_worst, peso_intra)
NUCLEO = [
    {"var": "DNU vs Leyes", "cat": "Ejecutivo", "peso": 0.12, "comp": [("dnu_leyes_mensual","cuota_dnu_12m",0.05,0.70,1.0)]},
    {"var": "ATN (federalismo)", "cat": "Ejecutivo", "peso": 0.06, "comp": [("atn_mensual","atn_share",0.001,0.007,1.0)]},
    {"var": "Eficacia de Control", "cat": "Legislativo", "peso": 0.12, "comp": [("eficacia_control_mensual","cumplimiento_art101_12m",0.75,0.10,1.0)]},
    {"var": "Calidad Normativa", "cat": "Legislativo", "peso": 0.10, "comp": [
        ("__derived__","leyes_por_sesion",1.5,0.2,0.6),
        ("sesiones_mensual","cumplimiento_sesiones",0.95,0.40,0.4)]},
    {"var": "Costo del Legislativo", "cat": "Legislativo", "peso": 0.03, "comp": [("costo_legislativo_mensual","costo_legislativo",0.003,0.012,1.0)]},
    {"var": "Desempeño de la Corte", "cat": "Judicial", "peso": 0.15, "comp": [
        ("resolucion_csjn_mensual","tasa_resolucion",0.95,0.30,0.35),
        ("resolucion_csjn_mensual","mediana_dias",120,730,0.25),
        ("resolucion_csjn_mensual","originaria_dias",365,1825,0.20),
        ("resolucion_csjn_mensual","csjn_vacantes",0,3,0.20)]},
    {"var": "Cobertura Judicial", "cat": "Judicial", "peso": 0.10, "comp": [
        ("cobertura_judicial_mensual","tasa_titular",0.90,0.55,0.6),
        ("cobertura_judicial_mensual","tasa_subrogancia",0.05,0.35,0.4)]},
    {"var": "Pauta Publicitaria", "cat": "Prensa", "peso": 0.05, "comp": [("pauta_mensual","intensidad_pauta",0.0,0.004,1.0)]},
    {"var": "Medios estatales", "cat": "Prensa", "peso": 0.04, "comp": [("medios_oficiales_mensual","medios_share",0.0,0.0015,1.0)]},
    {"var": "Financiamiento al Tesoro", "cat": "Banco Central", "peso": 0.06, "comp": [("bcra_financiamiento_mensual","financiamiento",0.02,0.40,1.0)]},
    {"var": "Letras intransferibles", "cat": "Banco Central", "peso": 0.05, "comp": [("bcra_letras_mensual","letras_share",0.0,0.70,1.0)]},
    {"var": "Designación Pdte. BCRA", "cat": "Banco Central", "peso": 0.04, "comp": [("bcra_designacion_mensual","designacion_acuerdo",1,0,1.0)]},
    {"var": "Respeto Carta Orgánica", "cat": "Banco Central", "peso": 0.05, "comp": [("carta_organica_mensual","carta_organica_exceso",0.0,0.5,1.0)]},
]


def _latest(p):
    f = sorted(glob.glob(str(OUTPUT_DIR / f"{p}_*.csv")))
    return f[-1] if f else None


def _annual(archivo, col, years):
    """Serie anual (promedio del año) de una columna mensual."""
    f = _latest(archivo)
    if not f: return None
    df = pd.read_csv(f)
    if "periodo" not in df.columns or col not in df.columns: return None
    df["anio"] = df["periodo"].astype(str).str[:4].astype(int)
    s = df.groupby("anio")[col].apply(lambda x: pd.to_numeric(x, errors="coerce").mean())
    return s.reindex(years)


def _annual_derived(name, years):
    if name == "leyes_por_sesion":
        ley = _latest("calidad_normativa_mensual"); ses = _latest("sesiones_mensual")
        if not ley or not ses: return None
        dl = pd.read_csv(ley); ds = pd.read_csv(ses)
        dl["anio"] = dl["periodo"].astype(str).str[:4].astype(int)
        ds["anio"] = ds["periodo"].astype(str).str[:4].astype(int)
        leyes = dl.groupby("anio")["n_leyes_sancionadas"].sum()
        real = ds.groupby("anio")["real_12m"].mean()  # sesiones realizadas (12m) prom.
        return (leyes / real).reindex(years)
    return None


def anchor(v, vb, vw):
    return None if v is None or pd.isna(v) else min(max((v - vw) / (vb - vw + (EPS if vb == vw else 0)), 0), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2003)
    ap.add_argument("--hasta", type=int, default=2026)
    a = ap.parse_args()
    years = list(range(a.desde, a.hasta + 1))

    var_year = {}  # var -> {year: score 0-1}
    for v in NUCLEO:
        comps = []
        for arch, col, vb, vw, w in v["comp"]:
            s = _annual_derived(col, years) if arch == "__derived__" else _annual(arch, col, years)
            if s is None: continue
            comps.append((s, vb, vw, w))
        if not comps: 
            var_year[v["var"]] = {y: None for y in years}; continue
        scores = {}
        for y in years:
            num = den = 0.0; ok = False
            for s, vb, vw, w in comps:
                sc = anchor(s.get(y), vb, vw)
                if sc is not None: num += sc * w; den += w; ok = True
            scores[y] = (num / den) if ok and den > 0 else None
        var_year[v["var"]] = scores

    cats = {v["var"]: v["cat"] for v in NUCLEO}
    pesos = {v["var"]: v["peso"] for v in NUCLEO}
    rows = []
    for y in years:
        sub = {}
        for c in MACRO:
            vs = [v for v in NUCLEO if v["cat"] == c]
            num = den = 0.0
            for v in vs:
                sc = var_year[v["var"]][y]
                if sc is not None: num += sc * pesos[v["var"]]; den += pesos[v["var"]]
            sub[c] = (num / den * 100) if den > 0 else None
        cats_ok = [c for c in MACRO if sub[c] is not None]
        if cats_ok:
            num = sum(MACRO[c] * sub[c] for c in cats_ok); den = sum(MACRO[c] for c in cats_ok)
            itr = num / den
        else:
            itr = None
        nvar = sum(1 for v in NUCLEO if var_year[v["var"]][y] is not None)
        rows.append({"anio": y, "ITR_nucleo": None if itr is None else round(itr, 1),
                     **{f"sub_{c}": (None if sub[c] is None else round(sub[c], 1)) for c in MACRO},
                     "ejes_cubiertos": len(cats_ok), "n_variables": nvar})
    out = pd.DataFrame(rows)
    out.to_csv(OUTPUT_DIR / "itr_nucleo_anual.csv", index=False, encoding="utf-8")
    print(out.to_string(index=False))
    print("\nNúcleo balanceado (5 ejes) desde el primer año con ejes_cubiertos=5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
