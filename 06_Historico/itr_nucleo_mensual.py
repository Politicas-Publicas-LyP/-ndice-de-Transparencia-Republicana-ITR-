"""
ITR — NÚCLEO MENSUAL (serie larga, 2020+ a frecuencia mensual)
==============================================================
Núcleo general del índice: el mismo método anclado al ideal del ITR, pero restringido
al SUBCONJUNTO de variables con serie larga y consistente (las que existen desde mucho
antes de 2023), a FRECUENCIA MENSUAL. Sirve como serie de fondo para actualizar mes a
mes en paralelo al ITR pleno (18 variables, desde 2023).

Reutiliza la maquinaria de 00_Comun/icia_ensamblado.py (anchor, load, suavizado 12m,
NO_SUAVIZAR, renormalización por eje y pesos macro fijos). Calcula con arranque temprano
(warmup) para que el suavizado de 12 meses esté completo, y publica desde --desde.

Variables EXCLUIDAS (series cortas): Discrecionalidad, Transparencia AAIP, Escrutinio,
Causas contra periodistas, Acceso de la prensa. Carta Orgánica entra desde que hay
recaudación+balance (2023 en estos datos; correr scraper_21 --desde 2020 para extenderla).

Uso: py itr_nucleo_mensual.py --desde 2020-01 --hasta 2026-05
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00_Comun"))
from icia_ensamblado import anchor, load, NO_SUAVIZAR, MACRO, OUTPUT_DIR  # noqa

NUCLEO = [
 {"var":"DNU vs Leyes","cat":"Ejecutivo","peso":0.12,"comp":[("dnu_leyes_mensual","cuota_dnu_12m",0.05,0.70,1.0)]},
 {"var":"ATN (federalismo)","cat":"Ejecutivo","peso":0.06,"comp":[("atn_mensual","atn_share",0.001,0.007,1.0)]},
 {"var":"Eficacia de Control","cat":"Legislativo","peso":0.12,"comp":[("eficacia_control_mensual","cumplimiento_art101_12m",0.75,0.10,1.0)]},
 {"var":"Calidad Normativa","cat":"Legislativo","peso":0.10,"comp":[("__derived__","leyes_por_sesion",1.5,0.2,0.6),("sesiones_mensual","cumplimiento_sesiones",0.95,0.40,0.4)]},
 {"var":"Costo del Legislativo","cat":"Legislativo","peso":0.03,"comp":[("costo_legislativo_mensual","costo_legislativo",0.003,0.012,1.0)]},
 {"var":"Desempeño de la Corte","cat":"Judicial","peso":0.15,"comp":[
    ("resolucion_csjn_mensual","tasa_resolucion",0.95,0.30,0.35),("resolucion_csjn_mensual","mediana_dias",120,730,0.25),
    ("resolucion_csjn_mensual","originaria_dias",365,1825,0.20),("resolucion_csjn_mensual","csjn_vacantes",0,3,0.20)]},
 {"var":"Cobertura Judicial","cat":"Judicial","peso":0.10,"comp":[
    ("cobertura_judicial_mensual","tasa_titular",0.90,0.55,0.6),("cobertura_judicial_mensual","tasa_subrogancia",0.05,0.35,0.4)]},
 {"var":"Pauta Publicitaria","cat":"Prensa","peso":0.05,"comp":[("pauta_mensual","intensidad_pauta",0.0,0.004,1.0)]},
 {"var":"Medios estatales","cat":"Prensa","peso":0.04,"comp":[("medios_oficiales_mensual","medios_share",0.0,0.0015,1.0)]},
 {"var":"Financiamiento al Tesoro","cat":"Banco Central","peso":0.06,"comp":[("bcra_financiamiento_mensual","financiamiento",0.02,0.40,1.0)]},
 {"var":"Letras intransferibles","cat":"Banco Central","peso":0.05,"comp":[("bcra_letras_mensual","letras_share",0.0,0.70,1.0)]},
 {"var":"Designación Pdte. BCRA","cat":"Banco Central","peso":0.04,"comp":[("bcra_designacion_mensual","designacion_acuerdo",1,0,1.0)]},
 {"var":"Respeto Carta Orgánica","cat":"Banco Central","peso":0.05,"comp":[("carta_organica_mensual","carta_organica_exceso",0.0,0.5,1.0)]},
]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--desde",default="2020-01"); ap.add_argument("--hasta",default="2026-05")
    ap.add_argument("--suavizado",type=int,default=12); a=ap.parse_args()
    idx=pd.period_range("2003-01",a.hasta,freq="M")  # warmup largo para el suavizado
    var_scores={}
    for v in NUCLEO:
        cs,cw=[],[]
        for arch,col,vb,vw,w in v["comp"]:
            raw=load(arch,col,idx)
            if raw is None or raw.dropna().empty: continue
            cs.append(anchor(raw,vb,vw,a.suavizado,col not in NO_SUAVIZAR)*w)
            cw.append(raw.notna().rolling(a.suavizado,min_periods=3).max().fillna(0)*w)
        if not cs: var_scores[v["var"]]=pd.Series(float("nan"),index=idx); continue
        num=pd.concat(cs,axis=1).sum(axis=1,min_count=1); den=pd.concat(cw,axis=1).sum(axis=1,min_count=1)
        var_scores[v["var"]]=(num/den).clip(0,1)
    vs=pd.DataFrame(var_scores); pesos={v["var"]:v["peso"] for v in NUCLEO}
    out=pd.DataFrame(index=idx)
    for cat in MACRO:
        vc=[v["var"] for v in NUCLEO if v["cat"]==cat]; w=pd.Series({v:pesos[v] for v in vc}); sub=vs[vc]
        wmat=sub.notna().mul(w,axis=1)
        out[f"sub_{cat}"]=(sub.mul(w,axis=1).sum(axis=1,min_count=1)/wmat.sum(axis=1).replace(0,float("nan")))*100
    subm=pd.DataFrame({c:out[f"sub_{c}"] for c in MACRO}); wM=pd.Series(MACRO); wmat=subm.notna().mul(wM,axis=1)
    out["ITR_nucleo"]=(subm.mul(wM,axis=1).sum(axis=1,min_count=1)/wmat.sum(axis=1).replace(0,float("nan")))
    out["ejes_cubiertos"]=subm.notna().sum(axis=1).astype(int)
    out=out[out.index>=pd.Period(a.desde,"M")]
    o=out.reset_index(names="periodo"); o["periodo"]=o["periodo"].astype(str)
    o=o[["periodo","ITR_nucleo","sub_Ejecutivo","sub_Legislativo","sub_Judicial","sub_Prensa","sub_Banco Central","ejes_cubiertos"]]
    o.to_csv(OUTPUT_DIR/"itr_nucleo_mensual.csv",index=False,encoding="utf-8")
    print(o.round(1).to_string(index=False))
    print("\nCSV:",OUTPUT_DIR/"itr_nucleo_mensual.csv")
    return 0
if __name__=="__main__": sys.exit(main())
