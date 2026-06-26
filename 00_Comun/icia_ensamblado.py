"""
ITR — Índice de Transparencia Republicana — Ensamblado y Normalización ANCLADA AL IDEAL
=======================================================================================
Convierte las series mensuales de las 5 macrocategorías a una escala 0-100 ANCLADA A UN
IDEAL ABSOLUTO de transparencia y república liberal (frenos y contrapesos), NO relativa al
pasado ni a cómo gobernaron este u otros gobiernos.

Cada componente define dos anclas principistas:
    v_best  -> 100  (óptimo republicano alcanzable; tolera mínimos razonables, no utopía)
    v_worst ->   0  (colapso institucional en esa dimensión)
con interpolación lineal y recorte: score = clip((v - v_worst)/(v_best - v_worst), 0, 1).

Las TASAS y CONTEOS se suavizan 12m (limpian ruido). Los ESTADOS BINARIOS/puntuales
(NO_SUAVIZAR) NO se suavizan: un flag vale por entero cuando corresponde, no se promedia
con el pasado (ej.: presupuesto aprobado hoy cuenta pleno, no diluido por la prórroga previa).

ITR = promedio ponderado de los 5 sub-índices con PESOS MACRO FIJOS 30/20/20/15/15. Cada
sub-índice se renormaliza sobre las variables disponibles de su categoría, de modo que una
variable ausente (AGN) no altera el peso macro del poder.

Salida: output/itr_mensual.csv  +  output/itr_reporte.md
Uso:    py icia_ensamblado.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas

ANCLAS VIGENTES (v_best -> 100 ; v_worst -> 0):
  Ejecutivo (35%)
    DNU vs Leyes (12%)            cuota DNU 12m      0.05 -> 100 ; 0.70 -> 0
    Discrecionalidad (13%)        presup. aprobado   1 -> 100 ; 0 -> 0   (.6, SIN suavizar)
                                  modif. por decreto 5 -> 100 ; 12 -> 0  (.4)
    Transparencia (5%)            tasa respuesta     0.95 -> 100 ; 0.30 -> 0 (.4)
                                  tasa en plazo      0.90 -> 100 ; 0.20 -> 0 (.6)
    ATN — federalismo (6%)        % del gasto (devengado) 0.001 -> 100 ; 0.007 -> 0
  Legislativo (25%)
    Eficacia de control (12%)     cumpl. art.101 12m 0.75 -> 100 ; 0.10 -> 0
    Calidad normativa (10%)       leyes por sesión   1.5 -> 100 ; 0.2 -> 0   (.6)
                                  cumpl. sesiones    0.95 -> 100 ; 0.40 -> 0 (.4)
    Costo del Legislativo (3%)    % del gasto total  0.003 -> 100 ; 0.012 -> 0
  Judicial (25%)
    Desempeño de la Corte (15%)   tasa resolución    0.95 -> 100 ; 0.30 -> 0 (.35)
                                  mediana días       120 -> 100 ; 730 -> 0   (.25)
                                  originaria días    365 -> 100 ; 1825 -> 0  (.20)
                                  vacantes Corte     0 -> 100 ; 3 -> 0        (.20)
    (Control de la corrupción descartado por falta de dato duro; su 8% se redistribuyó en Corte+Cobertura)
    Cobertura judicial (10%)      titularidad        0.90 -> 100 ; 0.55 -> 0 (.6)
                                  subrogancia        0.05 -> 100 ; 0.35 -> 0 (.4)
  Prensa (15%)
    Escrutinio abierto (6%)       conf./(conf+cad)   0.85 -> 100 ; 0.30 -> 0
    Pauta oficial (5%)            % del gasto total  0.0 -> 100 ; 0.004 -> 0
    Causas contra periodistas (4%) acciones 12m      0 -> 100 ; 20 -> 0
    Medios estatales (4%)         % del gasto (medios)    0.0 -> 100 ; 0.0015 -> 0
    Acceso de la prensa (4%)      acceso estructural 1.0 -> 100 ; 0.0 -> 0 (.5, SIN suavizar)
                                  restricciones 12m  0 -> 100 ; 40 -> 0      (.5)
  Banco Central (15%)
    Financiamiento al Tesoro (6%) adelantos/base mon. 0.02 -> 100 ; 0.40 -> 0
    Letras intransferibles (5%)   letras/activo BCRA  0.0 -> 100 ; 0.70 -> 0
    Designación Pdte. BCRA (4%)   con acuerdo Senado  1 -> 100 ; 0 -> 0  (binaria, SIN suavizar)
    Respeto Carta Orgánica (5%)   exceso s/ tope art.20  0.0 -> 100 ; 0.5 -> 0
"""
from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
EPS = 1e-9


def _cargar_config():
    """Carga la definición declarativa desde variables.yaml (FUENTE ÚNICA DE VERDAD).
    Devuelve: MACRO, REG, NO_SUAVIZAR, CARRYOVER, CARRY_MESES.
    modo por componente: suavizado | sin_suavizar | arrastre."""
    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parent / "variables.yaml").read_text(encoding="utf-8"))
    macro = {k: float(v) for k, v in cfg["macro"].items()}
    carry = int(cfg.get("carry_meses", 3))
    reg, no_suav, carry_set = [], set(), set()
    for v in cfg["variables"]:
        comp = []
        for c in v["comp"]:
            comp.append((c["archivo"], c["col"], c["mejor"], c["peor"], c["peso_intra"]))
            modo = c.get("modo", "suavizado")
            if modo in ("sin_suavizar", "arrastre"):
                no_suav.add(c["col"])
            if modo == "arrastre":
                carry_set.add(c["col"])
        reg.append({"var": v["var"], "cat": v["eje"], "peso": float(v["peso"]),
                    "nucleo": bool(v.get("nucleo", False)), "comp": comp})
    return macro, reg, no_suav, carry_set, carry


MACRO, REG, NO_SUAVIZAR, CARRYOVER, CARRY_MESES = _cargar_config()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("ensamblado")


def _latest(pattern: str) -> str | None:
    files = sorted(glob.glob(str(OUTPUT_DIR / f"{pattern}_*.csv")))
    return files[-1] if files else None


def _col(archivo: str, col: str) -> pd.Series | None:
    f = _latest(archivo)
    if f is None:
        log.warning("Falta archivo: %s_*.csv", archivo)
        return None
    df = pd.read_csv(f)
    if "periodo" not in df.columns or col not in df.columns:
        log.warning("%s: falta columna %s", Path(f).name, col)
        return None
    s = df.set_index(pd.PeriodIndex(df["periodo"], freq="M"))[col]
    return pd.to_numeric(s, errors="coerce")


def _derived(name: str, idx: pd.PeriodIndex) -> pd.Series | None:
    """Series calculadas a partir de >1 fuente."""
    if name == "leyes_por_sesion":  # leyes sustantivas por sesión realizada (12m), stale -> ffill
        leyes = _col("calidad_normativa_mensual", "n_leyes_sancionadas")
        real = _col("sesiones_mensual", "real_12m")
        if leyes is None or real is None:
            return None
        leyes12 = leyes.rolling(12, min_periods=3).sum()
        return (leyes12.reindex(idx) / real.reindex(idx)).ffill()
    return None


def load(archivo: str, col: str, idx: pd.PeriodIndex) -> pd.Series | None:
    if archivo == "__derived__":
        return _derived(col, idx)
    s = _col(archivo, col)
    return None if s is None else s.reindex(idx)


def anchor(s: pd.Series, v_best: float, v_worst: float, window: int, suavizar: bool = True) -> pd.Series:
    """Mapea al ideal absoluto: v_best->1, v_worst->0, lineal con recorte."""
    if suavizar:
        s = s.rolling(window, min_periods=3).mean()  # suaviza ruido/frecuencias
    return ((s - v_worst) / (v_best - v_worst + (EPS if v_best == v_worst else 0))).clip(0, 1)


def carryover(s: pd.Series, meses: int) -> pd.Series:
    """Arrastre ASIMÉTRICO para eventos puntuales: el valor cae de golpe cuando ocurre el
    evento (el mes lo refleja por entero) pero solo puede recuperarse 1/meses por mes, de
    modo que el daño institucional no desaparece al mes siguiente. Recuperación total al
    cabo de 'meses'. Trabaja sobre el flag 0-1 en orden cronológico."""
    step = 1.0 / meses
    out, prev = s.copy().astype(float), None
    for i in s.index:
        v = s.get(i)
        if pd.isna(v):
            out[i] = prev if prev is not None else float("nan")
            continue
        out[i] = float(v) if prev is None else min(float(v), prev + step)
        prev = out[i]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR — Ensamblado anclado al ideal")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--suavizado", type=int, default=12, help="ventana de suavizado (meses)")
    args = ap.parse_args()

    idx = pd.period_range(args.desde, args.hasta, freq="M")

    var_scores, faltantes = {}, []
    for v in REG:
        comp_scores, comp_w = [], []
        for archivo, col, vb, vw, w in v["comp"]:
            raw = load(archivo, col, idx)
            if raw is None or raw.dropna().empty:
                faltantes.append(f"{v['var']} [{col}]")
                continue
            # Los ESTADOS (sin_suavizar, no arrastre) persisten hasta que cambian: ffill para
            # que no desaparezcan en meses sin fila nueva. Si no, se caen de la renormalización
            # del eje e inflan/distorsionan el valor en análisis parciales del mes en curso
            # (p. ej. "Designación Pdte. BCRA" o "presupuesto aprobado").
            if col in NO_SUAVIZAR and col not in CARRYOVER:
                raw = raw.ffill()
            base = carryover(raw, CARRY_MESES) if col in CARRYOVER else raw
            comp_scores.append(anchor(base, vb, vw, args.suavizado,
                                      col not in NO_SUAVIZAR and col not in CARRYOVER) * w)
            comp_w.append(raw.notna().rolling(args.suavizado, min_periods=3).max().fillna(0) * w)
        if not comp_scores:
            var_scores[v["var"]] = pd.Series(float("nan"), index=idx)
            continue
        num = pd.concat(comp_scores, axis=1).sum(axis=1, min_count=1)
        den = pd.concat(comp_w, axis=1).sum(axis=1, min_count=1)
        var_scores[v["var"]] = (num / den).clip(0, 1)

    vs = pd.DataFrame(var_scores)
    pesos = {v["var"]: v["peso"] for v in REG}

    # sub-índices: renormalizan sobre variables disponibles de la categoría
    out = pd.DataFrame(index=idx)
    for cat in MACRO:
        vars_cat = [v["var"] for v in REG if v["cat"] == cat]
        w = pd.Series({v: pesos[v] for v in vars_cat})
        sub = vs[vars_cat]
        wmat = sub.notna().mul(w, axis=1)
        out[f"sub_{cat}"] = (sub.mul(w, axis=1).sum(axis=1, min_count=1) /
                             wmat.sum(axis=1).replace(0, float("nan"))) * 100

    # ITR = promedio de sub-índices con pesos macro FIJOS (35/25/25/15)
    subm = pd.DataFrame({c: out[f"sub_{c}"] for c in MACRO})
    wM = pd.Series(MACRO)
    wmat = subm.notna().mul(wM, axis=1)
    out["ITR"] = (subm.mul(wM, axis=1).sum(axis=1, min_count=1) /
                  wmat.sum(axis=1).replace(0, float("nan")))
    out["cobertura_vars"] = vs.notna().sum(axis=1).astype(int)
    for v in REG:
        out[v["var"]] = (vs[v["var"]] * 100).round(1)

    out_idx = out.reset_index(names="periodo")
    out_idx["periodo"] = out_idx["periodo"].astype(str)
    out_csv = OUTPUT_DIR / "itr_mensual.csv"
    out_idx.to_csv(out_csv, index=False, encoding="utf-8")

    # ---- reporte markdown ----
    val = out.dropna(subset=["ITR"])
    ult, prim = val.iloc[-1], val.iloc[0]
    rep = OUTPUT_DIR / "itr_reporte.md"
    with rep.open("w", encoding="utf-8") as fh:
        fh.write("# Indice de Transparencia Republicana (ITR)\n\n")
        fh.write("*Escala 0-100 ANCLADA AL IDEAL liberal de transparencia y frenos y contrapesos "
                 "(no relativa al pasado) - suavizado {} meses*\n\n".format(args.suavizado))
        fh.write("## ITR actual: **{:.1f}** ({})\n\n".format(ult['ITR'], val.index[-1]))
        fh.write("Al inicio del periodo ({}) era {:.1f}; variacion de **{:+.1f}** puntos.\n\n".format(
            val.index[0], prim['ITR'], ult['ITR'] - prim['ITR']))
        fh.write("## Sub-indices por poder (ultimo mes)\n\n| Poder | Peso | Sub-indice |\n|---|---|---|\n")
        for cat in MACRO:
            fh.write("| {} | {:.0f}% | {:.1f} |\n".format(cat, MACRO[cat] * 100, ult['sub_' + cat]))
        fh.write("\n## Variables (score 0-100 vs ideal, ultimo mes)\n\n")
        fh.write("| Variable | Poder | Peso | Score |\n|---|---|---|---|\n")
        for v in REG:
            fh.write("| {} | {} | {:.0f}% | {:.1f} |\n".format(v['var'], v['cat'], v['peso'] * 100, ult[v['var']]))
        fh.write("\n## Serie ITR (trimestral)\n\n| Periodo | ITR |\n|---|---|\n")
        for p in val.index:
            if p.month in (3, 6, 9, 12):
                fh.write("| {} | {:.1f} |\n".format(p, val.loc[p, 'ITR']))
        fh.write("\n> Nota: los scores miden distancia al ideal absoluto, no posicion relativa al "
                 "pasado. Control de la corrupcion fue descartado por falta de dato duro (su 8% se "
                 "redistribuyo en Corte y Cobertura); AGN pendiente. Estados binarios (presupuesto) "
                 "sin suavizar; estructurales con ffill/stale.\n")

    print("\n=== ITR (anclado al ideal) — SERIE (cola) ===")
    print(out_idx[["periodo", "ITR", "sub_Ejecutivo", "sub_Legislativo",
                   "sub_Judicial", "sub_Prensa", "cobertura_vars"]].tail(18).to_string(index=False))
    if faltantes:
        log.warning("Componentes faltantes/diferidos: %s", faltantes)
    log.info("CSV: %s", out_csv)
    log.info("Reporte: %s", rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
