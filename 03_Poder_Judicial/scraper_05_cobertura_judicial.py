"""
ITR — Módulo 5: Cobertura e Independencia Judicial (Poder Judicial)
===================================================================
Mide la cobertura e independencia de la judicatura federal/nacional a partir del
dataset "Magistrados de la Justicia Federal y de la Justicia Nacional" (datos.jus.gob.ar).

Tres señales (columna clave cargo_cobertura: Titular/Subrogante/Sin subrogante designado):
  - tasa_vacancia    = #(cargo_vacante=Sí) / #(habilitados)            [continuidad]
  - tasa_titular     = #(cargo_cobertura=Titular) / #(habilitados)     [ideal alto]
  - tasa_subrogancia = #(cargo_cobertura=Subrogante) / #(habilitados)  [ideal bajo]
  - tasa_concurso_vacantes = #(vacante con concurso en trámite) / #(vacantes)  [ideal alto:
    diligencia del Consejo de la Magistratura en cubrir las vacantes]

Desde la mirada liberal: un cargo con JUEZ TITULAR es independiente (inamovible); uno
cubierto por SUBROGANTE designado a dedo es removible y por ende dependiente; uno SIN
subrogante no funciona. Por eso la calidad republicana exige alta titularidad y baja
subrogancia, no solo baja vacancia.

NATURALEZA: STOCK de baja frecuencia ("Eventual"). Serie mensual por forward-fill con
stale_flag (meses de antigüedad del snapshot).

Uso:
    py scraper_05_cobertura_judicial.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PACKAGE = "magistrados-justicia-federal-y-de-la-justicia-nacional"
API = f"https://datos.jus.gob.ar/api/3/action/package_show?id={PACKAGE}"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
# PUENTE con el Radar de Nombramientos (07_Radar_Nombramientos): da cadencia al flujo entre
# snapshots del dataset (que se actualiza ~cada 2 años). Solo entran al valor publicado las
# designaciones de confianza ALTA (o confirmadas a mano); el radar es alerta, no juez.
RADAR_CSV = OUTPUT_DIR / "nombramientos_jueces.csv"
# El radar corre en GitHub Actions (necesita IP del exterior); este scraper corre en una
# máquina argentina (datos.jus exige IP AR). Para que el flujo no quede congelado, leemos el
# CSV puente DIRECTO del repo (raw de GitHub), accesible desde Argentina, y caemos a la copia
# local si no hay red. Completar con el repo donde vive el radar, p.ej.:
#   https://raw.githubusercontent.com/USUARIO/REPO/main/output/nombramientos_jueces.csv
# Se puede fijar acá o, mejor, por variable de entorno ITR_RADAR_CSV_URL (no toca el código).
RADAR_CSV_URL = os.environ.get("ITR_RADAR_CSV_URL", "")
# PADRÓN VIVO (padron_judicial.py): tasas de cobertura recalculadas en vivo con las altas/bajas
# del BORA. Si existe, se usa para SOBREESCRIBIR el mes corriente (stock) con valor «estimado»,
# de modo que la cobertura no quede congelada en el último snapshot oficial. Se reconcilia solo
# cuando el dataset oficial publica un snapshot nuevo (que vuelve a ser la base del padrón).
PADRON_TASAS = OUTPUT_DIR / "padron_tasas_estimadas.csv"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json,*/*",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("cobertura_judicial")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=4, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def _read_csv_resilient(blob: bytes) -> pd.DataFrame | None:
    for enc in ("utf-8", "latin-1"):
        for sep in (",", ";"):
            try:
                df = pd.read_csv(io.BytesIO(blob), sep=sep, encoding=enc, dtype=str,
                                 low_memory=False, on_bad_lines="skip")
                if df.shape[1] > 3:
                    return df
            except Exception:  # noqa: BLE001
                continue
    return None


def _tasa(df: pd.DataFrame) -> dict:
    cols = {c.lower(): c for c in df.columns}
    cv = cols.get("cargo_vacante") or cols.get("vacante")
    oh = cols.get("organo_habilitado")
    cc = cols.get("cargo_cobertura") or cols.get("cobertura")
    ct = cols.get("cargo_tipo") or cols.get("tipo_cargo")
    if not cv and not cc:
        return {}
    # UNIVERSO CONSISTENTE: medir SOLO JUECES. Desde 2026 la fuente publica un archivo de
    # jueces (1002 cargos); los históricos traen jueces+fiscales+defensores (~1600). Sin
    # filtrar, 2026 no es comparable y la titularidad cae por puro artefacto de universo.
    # Además, la inamovilidad del JUEZ es el indicador de independencia que nos interesa.
    if ct:
        df = df[df[ct].astype(str).str.strip().str.lower().str.startswith("juez")]
    hab = (df[oh].astype(str).str.strip().str.upper().isin(["SI", "SÍ"])) if oh else pd.Series(True, index=df.index)
    base = df[hab]
    nb = max(int(hab.sum()), 1)
    out = {"n_cargos": int(hab.sum())}
    if cv:
        vac = base[cv].astype(str).str.strip().str.upper().isin(["SI", "SÍ"])
        out["n_vacantes"] = int(vac.sum())
        out["tasa_vacancia"] = round(float(vac.sum() / nb), 4)
    if cc:
        cob = base[cc].astype(str).str.strip().str.lower()
        n_tit = int((cob == "titular").sum())
        n_sub = int(cob.str.fullmatch("subrogante").sum())
        n_sinsub = int(cob.str.contains("sin subrogante").sum())
        out["n_titular"] = n_tit
        out["n_subrogante"] = n_sub
        out["n_sin_subrog"] = n_sinsub
        out["tasa_titular"] = round(n_tit / nb, 4)
        out["tasa_subrogancia"] = round(n_sub / nb, 4)
        out["tasa_sin_cobertura"] = round(n_sinsub / nb, 4)  # vacante SIN subrogante = no funciona
        # FLUJO: fecha del último nombramiento de juez titular (norma_fecha entre titulares)
        nf = cols.get("norma_fecha")
        if nf:
            ftit = pd.to_datetime(base.loc[cob == "titular", nf], errors="coerce")
            if ftit.notna().any():
                out["ultimo_nombramiento"] = str(ftit.max().date())
    cet = cols.get("concurso_en_tramite")
    if cv and cet:
        vacm = base[cv].astype(str).str.strip().str.upper().isin(["SI", "SÍ"])
        con = base[cet].astype(str).str.strip().str.lower()
        # "tiene concurso" = no figura como negativo/vacío
        no_concurso = con.isin(["no", "", "nan", "sin concurso", "ninguno", "-"])
        tiene = vacm & (~no_concurso) & (con.str.len() > 0)
        nvac = int(vacm.sum())
        out["n_vac_con_concurso"] = int(tiene.sum())
        out["tasa_concurso_vacantes"] = round(int(tiene.sum()) / max(nvac, 1), 4)
    return out


def _snapshot_date(name: str, last_modified: str | None) -> pd.Timestamp | None:
    m = re.search(r"(20\d{6})", name or "")
    if m:
        try:
            return pd.Timestamp(datetime.strptime(m.group(1), "%Y%m%d"))
        except ValueError:
            pass
    if last_modified:
        try:
            return pd.Timestamp(last_modified)
        except Exception:  # noqa: BLE001
            return None
    return None


def _titular_fechas(df: pd.DataFrame) -> pd.Series | None:
    """norma_fecha de designación de los JUECES TITULARES del snapshot, ordenada. Sirve para
    reconstruir el flujo de nombramientos con la historia más completa disponible."""
    cols = {c.lower(): c for c in df.columns}
    cc = cols.get("cargo_cobertura") or cols.get("cobertura")
    nf = cols.get("norma_fecha"); ct = cols.get("cargo_tipo") or cols.get("tipo_cargo")
    if not cc or not nf:
        return None
    if ct:
        df = df[df[ct].astype(str).str.strip().str.lower().str.startswith("juez")]
    tit = df[df[cc].astype(str).str.strip().str.lower() == "titular"]
    fechas = pd.to_datetime(tit[nf], errors="coerce").dropna()
    return fechas.sort_values() if len(fechas) else None


def fechas_radar() -> pd.Series | None:
    """Lee el CSV puente del Radar de Nombramientos y devuelve las fechas de designación de
    confianza ALTA (o marcadas como confirmadas). Mantiene el flujo fresco entre snapshots."""
    d = None
    # 1) Intentar el raw de GitHub (el radar lo mantiene al día allá; accesible desde AR).
    if RADAR_CSV_URL:
        try:
            r = requests.get(RADAR_CSV_URL, headers=HEADERS, timeout=30)
            if r.status_code == 200 and r.text.strip():
                d = pd.read_csv(io.StringIO(r.text), dtype=str)
                log.info("Puente radar: leído del repo (%s)", RADAR_CSV_URL)
        except Exception as e:  # noqa: BLE001
            log.warning("No pude bajar el CSV del radar (%s): %s; uso copia local.", RADAR_CSV_URL, e)
    # 2) Fallback: copia local del repo.
    if d is None:
        if not RADAR_CSV.exists():
            return None
        try:
            d = pd.read_csv(RADAR_CSV, dtype=str)
            log.info("Puente radar: leído de la copia local (%s).", RADAR_CSV.name)
        except Exception as e:  # noqa: BLE001
            log.warning("No pude leer el puente del radar (%s): %s", RADAR_CSV.name, e)
            return None
    if "confianza" in d.columns:
        conf = d["confianza"].astype(str).str.upper().str.strip()
        mask = conf.eq("ALTA")
        if "confirmado" in d.columns:  # confirmación humana explícita pisa la confianza
            confirmado = d["confirmado"].astype(str).str.lower().str.strip()
            mask = mask | confirmado.isin(["si", "sí", "true", "1"])
            mask = mask & ~confirmado.isin(["no", "false", "0"])
        d = d[mask]
    col = "fecha_publicacion" if "fecha_publicacion" in d.columns else "fecha_deteccion"
    fechas = pd.to_datetime(d.get(col), errors="coerce").dropna()
    if not len(fechas):
        return None
    log.info("Puente radar: %s designación(es) ALTA/confirmadas; última %s",
             len(fechas), fechas.max().date())
    return fechas.sort_values()


def _combinar_fechas(a: pd.Series | None, b: pd.Series | None) -> pd.Series | None:
    partes = [x for x in (a, b) if x is not None and len(x)]
    if not partes:
        return None
    return pd.concat(partes).sort_values().reset_index(drop=True)


def aplicar_padron_estimado(serie: pd.DataFrame) -> pd.DataFrame:
    """Sobreescribe el ÚLTIMO mes (corriente) con las tasas del padrón vivo, marcándolo
    `cobertura_estimada=1`. El STOCK (titular/subrogancia/sin-cobertura) deja de quedar
    congelado en el snapshot oficial mientras el dataset no se actualice."""
    serie = serie.copy()
    serie["cobertura_estimada"] = 0
    if not PADRON_TASAS.exists() or serie.empty:
        return serie
    try:
        t = pd.read_csv(PADRON_TASAS).iloc[-1]
    except Exception as e:  # noqa: BLE001
        log.warning("No pude leer %s: %s", PADRON_TASAS.name, e)
        return serie
    if not str(t.get("etiqueta", "")).lower().startswith("estimado"):
        log.info("Padrón presente pero no es 'estimado' (es base oficial); no se sobreescribe.")
        return serie
    idx = serie.index[-1]
    for col in ["tasa_titular", "tasa_subrogancia", "tasa_sin_cobertura"]:
        if col in t and pd.notna(t[col]):
            serie.at[idx, col] = round(float(t[col]), 4)
    serie.at[idx, "cobertura_estimada"] = 1
    log.info("Cobertura ESTIMADA aplicada a %s desde el padrón vivo (titular=%.4f, subrog=%.4f).",
             serie.at[idx, "periodo"], serie.at[idx, "tasa_titular"], serie.at[idx, "tasa_subrogancia"])
    return serie


def snapshots(s: requests.Session):
    resp = s.get(API, timeout=60)
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]
    log.info("Recursos en el dataset: %s", len(resources))
    rows = []
    fechas_latest, fecha_snap_latest = None, None
    for r in resources:
        url, fmt, name = r.get("url"), (r.get("format") or "").lower(), r.get("name") or ""
        if not url:
            continue
        try:
            blob = s.get(url, timeout=120).content
        except Exception as e:  # noqa: BLE001
            log.warning("No pude bajar %s: %s", name, e)
            continue
        dfs = []
        if "zip" in fmt or url.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    for n in zf.namelist():
                        if n.lower().endswith(".csv"):
                            d = _read_csv_resilient(zf.read(n))
                            if d is not None:
                                dfs.append((n, d))
            except Exception:  # noqa: BLE001
                continue
        else:
            d = _read_csv_resilient(blob)
            if d is not None:
                dfs.append((name, d))
        for nm, d in dfs:
            t = _tasa(d)
            if not t:
                continue
            fecha = _snapshot_date(nm, r.get("last_modified"))
            rows.append({"snapshot": fecha, "archivo": nm, **t})
            if fecha is not None and (fecha_snap_latest is None or fecha > fecha_snap_latest):
                ff = _titular_fechas(d)
                if ff is not None:
                    fecha_snap_latest, fechas_latest = fecha, ff
    out = pd.DataFrame(rows).dropna(subset=["snapshot"]).sort_values("snapshot")
    out = out.drop_duplicates(subset="snapshot", keep="last")
    return out, fechas_latest


CARRY = ["tasa_vacancia", "tasa_titular", "tasa_subrogancia", "tasa_sin_cobertura", "tasa_concurso_vacantes"]


def to_monthly(snap: pd.DataFrame, fechas_nombramientos, desde: str, hasta: str) -> pd.DataFrame:
    periods = pd.period_range(desde, hasta, freq="M")
    rows = []
    for p in periods:
        fin = p.to_timestamp(how="end").normalize()
        prev = snap[snap["snapshot"] <= fin]
        # FLUJO: meses desde el último nombramiento titular con fecha <= mes, usando la
        # historia completa del snapshot más reciente (reconstrucción retrospectiva fiel).
        msn = float("nan")
        if fechas_nombramientos is not None:
            previas = fechas_nombramientos[fechas_nombramientos <= fin]
            if len(previas):
                msn = (p - previas.max().to_period("M")).n
        if prev.empty:
            rows.append({"periodo": str(p), **{c: float("nan") for c in CARRY},
                         "stale_meses": float("nan"), "meses_sin_nombramiento": msn})
            continue
        ult = prev.iloc[-1]
        stale = (p.to_timestamp(how="end").to_period("M") - ult["snapshot"].to_period("M")).n
        rows.append({"periodo": str(p), **{c: ult.get(c, float("nan")) for c in CARRY},
                     "stale_meses": stale, "meses_sin_nombramiento": msn})
    return pd.DataFrame(rows)


def diagnostico(s: requests.Session) -> None:
    """Audita el dataset: por cada recurso vuelca nombre, fecha, columnas y los valores
    distintos de las columnas clave (cargo_cobertura, cargo_vacante, organo_habilitado,
    concurso_en_tramite), para ver qué lee el scraper y con qué etiquetas exactas."""
    resp = s.get(API, timeout=60); resp.raise_for_status()
    resources = resp.json()["result"]["resources"]
    print(f"\n=== {len(resources)} recursos en el dataset ===")
    for r in resources:
        url = r.get("url"); fmt = (r.get("format") or "").lower(); name = r.get("name") or ""
        print(f"\n--- {name} | format={fmt} | last_modified={r.get('last_modified')}")
        print(f"    url: {url}")
        if not url:
            continue
        try:
            blob = s.get(url, timeout=120).content
        except Exception as e:  # noqa: BLE001
            print("    (no se pudo bajar:", e, ")"); continue
        dfs = []
        if "zip" in fmt or url.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                    for n in zf.namelist():
                        if n.lower().endswith(".csv"):
                            d = _read_csv_resilient(zf.read(n))
                            if d is not None:
                                dfs.append((n, d))
            except Exception:  # noqa: BLE001
                print("    (zip ilegible)"); continue
        else:
            d = _read_csv_resilient(blob)
            if d is not None:
                dfs.append((name, d))
        for nm, d in dfs:
            print(f"    archivo: {nm} | filas={len(d)} | columnas={list(d.columns)}")
            low = {c.lower(): c for c in d.columns}
            for key in ("cargo_tipo", "tipo_cargo", "cargo_cobertura", "cargo_vacante", "organo_habilitado", "concurso_en_tramite"):
                if key in low:
                    vc = d[low[key]].astype(str).str.strip().value_counts().head(15)
                    print(f"      {key}: {dict(vc)}")
            # FLUJO de nombramientos: norma_fecha entre los TITULARES (jueces)
            nf = low.get("norma_fecha"); ccc = low.get("cargo_cobertura") or low.get("cobertura")
            cct = low.get("cargo_tipo") or low.get("tipo_cargo")
            if nf and ccc:
                dd = d[d[cct].astype(str).str.strip().str.lower().str.startswith("juez")] if cct else d
                tit = dd[dd[ccc].astype(str).str.strip().str.lower() == "titular"]
                if len(tit):
                    fechas = pd.to_datetime(tit[nf], errors="coerce")
                    yrs = fechas.dt.year.value_counts().sort_index()
                    print(f"      nombramientos titulares por año (norma_fecha): {dict(yrs.tail(10).astype(int))}")
                    print(f"      ÚLTIMO nombramiento titular: {fechas.max()}")


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR Módulo 5 — Cobertura Judicial")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    ap.add_argument("--diagnostico", action="store_true",
                    help="audita recursos/columnas/valores del dataset y sale")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    if args.diagnostico:
        diagnostico(s)
        return 0
    try:
        snap, fechas_nom = snapshots(s)
    except Exception as e:  # noqa: BLE001
        log.error("Fallo al consultar/parsear el dataset: %s", e)
        return 1

    print("\n=== SNAPSHOTS (auditar titularidad/subrogancia) ===")
    show = [c for c in ["snapshot", "n_cargos", "tasa_titular", "tasa_subrogancia",
                        "tasa_sin_cobertura", "ultimo_nombramiento", "archivo"] if c in snap.columns]
    print(snap[show].to_string(index=False))

    # PUENTE: sumar las designaciones detectadas por el Radar de Nombramientos (BORA) a las
    # fechas reconstruidas del dataset, para que el flujo no quede congelado entre snapshots.
    fechas_nom = _combinar_fechas(fechas_nom, fechas_radar())

    serie = to_monthly(snap, fechas_nom, args.desde, args.hasta)
    # STOCK estimado del mes corriente desde el padrón vivo (si está disponible).
    serie = aplicar_padron_estimado(serie)
    mx = serie["stale_meses"].dropna().max()
    if mx and mx > 12:
        log.warning("FRESCURA: el último snapshot tiene >12 meses (estructural desactualizada).")

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"cobertura_judicial_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
