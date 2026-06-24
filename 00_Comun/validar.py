"""
ITR — Validación / QA (NOTIFICA, no bloquea)
============================================
Chequea, contra variables.yaml (fuente única de verdad), que cada fuente esté presente,
con sus columnas, numérica, no vacía y FRESCA. Calcula la frescura (meses desde el último
dato real, usando la columna 'stale_meses' del scraper si existe).

POLÍTICA (por decisión del equipo): NO bloquea la publicación. Si hay hallazgos, escribe
un reporte de alertas (output/_alertas_validacion.md), notifica por consola y devuelve
exit code 2 (= publicar + notificar para evaluar). Exit 0 si todo OK.

Uso: py validar.py
Requisitos: pip install pandas pyyaml
"""
from __future__ import annotations
import sys, glob
from pathlib import Path
from datetime import datetime
import pandas as pd, yaml

BASE = Path(__file__).resolve().parent
OUTPUT_DIR = BASE.parent / "output"

def latest(pat):
    f = sorted(glob.glob(str(OUTPUT_DIR / f"{pat}_*.csv")))
    return f[-1] if f else None

def main():
    cfg = yaml.safe_load((BASE / "variables.yaml").read_text(encoding="utf-8"))
    con = yaml.safe_load((BASE / "contracts.yaml").read_text(encoding="utf-8")) if (BASE/"contracts.yaml").exists() else {}
    fmax = int(con.get("frescura_max_meses", 3)); ovr = con.get("frescura_overrides", {}) or {}
    errores, warns, frescura = [], [], []

    # mapear archivo -> columnas usadas
    archivos = {}
    for v in cfg["variables"]:
        for c in v["comp"]:
            if c["archivo"] != "__derived__":
                archivos.setdefault(c["archivo"], {}).setdefault("cols", set()).add(c["col"])
                archivos[c["archivo"]].setdefault("var", v["var"])
    # cargar y referencia de frescura global
    datos, ult_global = {}, None
    for arch in archivos:
        f = latest(arch)
        if not f: errores.append(f"FALTA archivo: {arch}_*.csv"); continue
        df = pd.read_csv(f); datos[arch] = df
        if "periodo" in df.columns:
            p = pd.PeriodIndex(df["periodo"].astype(str), freq="M").max()
            ult_global = p if ult_global is None else max(ult_global, p)

    for arch, meta in archivos.items():
        df = datos.get(arch)
        if df is None: continue
        if "periodo" not in df.columns: errores.append(f"{arch}: sin columna 'periodo'"); continue
        for col in meta["cols"]:
            if col not in df.columns: errores.append(f"{arch}: falta columna '{col}'"); continue
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() == 0: errores.append(f"{arch}.{col}: columna vacía (todo NaN)"); continue
            if (s.dropna() < 0).any(): warns.append(f"{arch}.{col}: valores negativos")
        # frescura: usar 'stale_meses' del scraper si existe; si no, último no-NaN vs global
        lim = int(ovr.get(arch, fmax))
        if "stale_meses" in df.columns and pd.to_numeric(df["stale_meses"], errors="coerce").notna().any():
            antig = int(pd.to_numeric(df["stale_meses"], errors="coerce").dropna().iloc[-1])
            ult = "(stale_meses)"
        else:
            per = pd.PeriodIndex(df["periodo"].astype(str), freq="M")
            anycol = next(iter(meta["cols"]))
            mask = pd.to_numeric(df[anycol], errors="coerce").notna().values
            ult_p = per[mask].max() if mask.any() else None
            antig = (ult_global - ult_p).n if (ult_global is not None and ult_p is not None) else 0
            ult = str(ult_p)
        frescura.append((meta["var"], arch, ult, antig, lim))
        if antig > lim: warns.append(f"{arch}: dato viejo ({antig} meses; tolerancia {lim})")

    estado = "OK" if not errores and not warns else ("ERRORES" if errores else "ADVERTENCIAS")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    rep = OUTPUT_DIR / "_alertas_validacion.md"
    L = [f"# ITR — Validación QA · {stamp}", "", f"**Estado:** {estado}",
         "**Política:** NOTIFICAR, no bloquear la publicación. (exit 2 = publicar + avisar)", ""]
    if errores: L += ["## Errores"] + [f"- {e}" for e in errores] + [""]
    if warns:   L += ["## Advertencias"] + [f"- {w}" for w in warns] + [""]
    L += ["## Frescura por variable", "", "| Variable | Archivo | Último | Meses | Tol. |",
          "|---|---|---|---|---|"] + [f"| {v} | {a} | {u} | {m} | {l} |" for v,a,u,m,l in frescura]
    rep.write_text("\n".join(L), encoding="utf-8")

    print(f"[VALIDACIÓN ITR] estado={estado} | errores={len(errores)} | advertencias={len(warns)}")
    if errores or warns:
        print(f"  -> NOTIFICAR: ver {rep.name} (la publicacion NO se bloquea)")
        for e in errores[:12]: print("   ERROR:", e)
        for w in warns[:12]:  print("   WARN :", w)
    else:
        print("  Todo OK.")
    return 0 if estado == "OK" else 2

if __name__ == "__main__": sys.exit(main())
