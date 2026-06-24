"""
ICIA — Módulo 3: Eficacia de Control parlamentario (Poder Legislativo, 15%)
============================================================================
La métrica original ("pedidos de informe respondidos / presentados") NO tiene
fuente confiable (el "respondido" no se registra). Sustitución acordada:

  CUMPLIMIENTO DEL ART. 101 CN: el Jefe de Gabinete debe concurrir al Congreso
  al menos una vez por mes, alternando cámaras, a informar sobre la marcha del
  gobierno. Medimos cuántas veces concurre efectivamente vs. el mínimo exigido.
  Es un indicador directo de rendición de cuentas del Ejecutivo ante el Legislativo.

Fuente: tabla del Senado de Informes JGM (HTML server-side, estable).
  https://www.senado.gob.ar/parlamentario/InformesJgm/

Salida (series crudas; normalización y pesos en Sprint 6):
  n_informes_jgm        : concurrencias del JGM por mes
  informes_12m          : suma móvil de 12 meses
  cumplimiento_art101_12m : informes_12m / 12 (mínimo constitucional), cap 1.0

Uso:
    py scraper_03_eficacia_control.py --desde 2023-01 --hasta 2025-12
Requisitos: pip install pandas requests beautifulsoup4 lxml
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL = "https://www.senado.gob.ar/parlamentario/InformesJgm/"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

# La tabla del Senado se actualiza con LAG y a veces omite informes que fueron a
# Diputados. Suplemento editable para informes recientes no listados aún.
# Formato: (nro, "DD/MM/AAAA", "camara"). Verificado vía PDF oficial de HCDN.
INFORMES_EXTRA = [
    ("145", "28/04/2026", "Cámara de Diputados"),   # JGM Manuel Adorni
]
EXTRA_CSV = OUTPUT_DIR / "informes_jgm_extra.csv"   # opcional: columnas nro,fecha,camara
FRESCURA_DIAS = 90   # alerta si el último informe conocido es más viejo que esto
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("eficacia_control")


def fetch_table() -> pd.DataFrame:
    s = requests.Session()
    r = Retry(total=4, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    resp = s.get(URL, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # elegir la tabla cuyo encabezado tenga Informe + Fecha + Cámara
    tabla = None
    for t in soup.find_all("table"):
        head = t.get_text(" ", strip=True).lower()
        if "informe" in head and "fecha" in head and "cámara" in head or "camara" in head:
            tabla = t
            break
    if tabla is None:
        raise RuntimeError("No se encontró la tabla de Informes JGM (¿cambió el HTML?).")

    filas = []
    for tr in tabla.find_all("tr"):
        celdas = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(celdas) < 3:
            continue
        informe, fecha, camara = celdas[0], celdas[1], celdas[2]
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", fecha)
        if not m:
            continue
        filas.append({"informe": informe, "fecha_raw": fecha, "camara": camara,
                      "fecha": pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1)))})
    df = pd.DataFrame(filas)
    log.info("Filas con fecha válida parseadas (tabla Senado): %s", len(df))
    return df


def add_supplement(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega informes recientes no listados en la tabla del Senado (lista interna
    + CSV opcional), evitando duplicar (fecha, cámara)."""
    extra = list(INFORMES_EXTRA)
    if EXTRA_CSV.exists():
        sup = pd.read_csv(EXTRA_CSV, dtype=str)
        extra += [(r["nro"], r["fecha"], r["camara"]) for _, r in sup.iterrows()]
    rows = []
    for nro, fecha, camara in extra:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", fecha)
        if not m:
            continue
        rows.append({"informe": str(nro), "fecha_raw": fecha, "camara": camara,
                     "fecha": pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1)))})
    if not rows:
        return df
    add = pd.DataFrame(rows)
    base_keys = set(zip(df["fecha"], df["camara"])) if len(df) else set()
    add = add[~add.apply(lambda r: (r["fecha"], r["camara"]) in base_keys, axis=1)]
    if len(add):
        log.info("Suplemento agrega %s informe(s) no listados en Senado: %s",
                 len(add), ", ".join(f"N°{r.informe} {r.fecha.date()}" for r in add.itertuples()))
    return pd.concat([df, add], ignore_index=True)


def report_freshness(df: pd.DataFrame) -> None:
    """Alerta si el informe más reciente conocido es viejo (posible fuente desactualizada)."""
    valido = df[df["fecha"] <= pd.Timestamp.today().normalize()]
    if valido.empty:
        log.warning("FRESCURA: sin informes válidos.")
        return
    ult = valido.loc[valido["fecha"].idxmax()]
    dias = (pd.Timestamp.today().normalize() - ult["fecha"]).days
    msg = f"último informe conocido: N°{ult['informe']} del {ult['fecha'].date()} ({ult['camara']}), hace {dias} días"
    if dias > FRESCURA_DIAS:
        log.warning("FRESCURA: %s. Verificá si hubo una concurrencia más nueva y agregala al suplemento.", msg)
    else:
        log.info("FRESCURA OK: %s", msg)


def build(df: pd.DataFrame, desde: str, hasta: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    # descartar fechas futuras imposibles (errores de carga del sitio)
    df = df[df["fecha"] <= pd.Timestamp.today().normalize()].copy()
    # Una concurrencia = un NÚMERO de informe. Deduplicar por nro_base resuelve
    # partes/tomos/anexos ("137 (parte 2)", "107 TOMO I", "ANEXO INFORME 33") y
    # también el mismo informe con fechas distintas entre fuentes (Senado vs suplemento).
    df["nro_base"] = df["informe"].str.extract(r"(\d+)")[0]
    df["_key"] = df["nro_base"].fillna(
        df["fecha"].dt.strftime("%Y%m%d") + "|" + df["camara"])
    conc = (df.sort_values("fecha")
              .drop_duplicates(subset="_key", keep="first").copy())
    conc["periodo"] = conc["fecha"].dt.to_period("M")

    periods = pd.period_range(desde, hasta, freq="M")
    cnt = conc["periodo"].value_counts()
    serie = pd.DataFrame(index=periods)
    serie["n_informes_jgm"] = [int(cnt.get(p, 0)) for p in periods]
    serie["informes_12m"] = serie["n_informes_jgm"].rolling(12, min_periods=6).sum()
    serie["cumplimiento_art101_12m"] = (serie["informes_12m"] / 12).clip(upper=1.0)
    serie = serie.reset_index(names="periodo")
    serie["periodo"] = serie["periodo"].astype(str)

    # tabla de concurrencias dentro de ventana (para auditar)
    en_ventana = conc[(conc["periodo"] >= pd.Period(desde, "M")) &
                      (conc["periodo"] <= pd.Period(hasta, "M"))].sort_values("fecha")
    return serie, en_ventana[["fecha", "camara", "informe"]]


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 3 — Eficacia de Control (art.101)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2025-12")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    try:
        df = fetch_table()
    except Exception as e:  # noqa: BLE001
        log.error("Fallo al obtener/parsear la tabla: %s", e)
        return 1

    df = add_supplement(df)
    report_freshness(df)
    serie, conc = build(df, args.desde, args.hasta)

    print("\n=== CONCURRENCIAS DEL JGM EN VENTANA (auditar) ===")
    print(conc.to_string(index=False) if len(conc) else "  (ninguna)")
    print(f"\nTotal concurrencias en ventana: {len(conc)}")

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"eficacia_control_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
