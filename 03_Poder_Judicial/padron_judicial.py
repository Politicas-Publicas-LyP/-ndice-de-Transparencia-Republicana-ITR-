"""
ITR — Padrón Judicial Vivo (cobertura e independencia, eje Judicial)
===================================================================
Mantiene un PADRÓN de cargos de JUECES (un cargo por fila) que arranca del último snapshot
oficial del dataset de magistrados (datos.jus.gob.ar) y que el bot va actualizando EN VIVO
con los decretos del BORA:
  - ALTAS  (designaciones de juez titular)            → el cargo pasa a Titular   (radar de nombramientos)
  - BAJAS  (renuncias/ceses/jubilaciones/remociones)  → el cargo pasa a Vacante   (detector de bajas, a futuro)

Con el padrón actualizado se RECALCULAN las tasas (titularidad/subrogancia/sin-cobertura/
vacancia) sobre los cargos HABILITADOS — mismo universo que el índice — marcadas «estimado»
mientras el dataset oficial no se actualice. Cada snapshot oficial nuevo RECONCILIA y reinicia
el padrón desde el dato duro.

Gobernanza (línea no-IA del ITR): determinístico y auditable. Cada cargo guarda su
estado_fuente (oficial | estimado-radar | estimado-baja) y la norma/fecha que lo cambió. Los
eventos del BORA que no se puedan mapear con confianza a un cargo van a una COLA DE REVISIÓN.

Subcomandos:
    py padron_judicial.py --construir [--verbose]   # baja el snapshot oficial y crea el padrón base
    py padron_judicial.py --actualizar              # aplica altas (radar) y bajas sobre el padrón
Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import re
import sys
import time
import unicodedata
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
PADRON = OUTPUT_DIR / "padron_judicial.csv"            # padrón vivo
PADRON_BASE = OUTPUT_DIR / "padron_judicial_base.csv"  # ancla = snapshot oficial
REVISION = OUTPUT_DIR / "padron_revision.csv"          # eventos sin cargo asignado
TASAS_EST = OUTPUT_DIR / "padron_tasas_estimadas.csv"  # tasas recalculadas
RADAR_ALTAS = OUTPUT_DIR / "nombramientos_jueces.csv"  # salida del radar (designaciones)
RADAR_ALTAS_URL = os.environ.get("ITR_RADAR_CSV_URL", "")  # mismo puente que la cobertura
RADAR_BAJAS = OUTPUT_DIR / "bajas_jueces.csv"          # salida del detector de bajas (a futuro)
HEADERS = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
           "Accept": "application/json,*/*"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("padron_judicial")

STOP = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "EN", "LO", "Y", "A", "AL", "CON", "SI", "NO"}


# ──────────────────────────────────────────────────────────────────────────────
# Descarga del snapshot oficial (CKAN) — mismo origen que scraper_05
# ──────────────────────────────────────────────────────────────────────────────
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


def _es_jueces(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    ct = cols.get("cargo_tipo") or cols.get("tipo_cargo")
    if ct:
        return df[df[ct].astype(str).str.strip().str.lower().str.startswith("juez")]
    return df


def latest_jueces_snapshot(s: requests.Session):
    resp = s.get(API, timeout=60)
    resp.raise_for_status()
    resources = resp.json()["result"]["resources"]
    log.info("Recursos en el dataset: %s", len(resources))
    mejor = None
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
            cl = {c.lower(): c for c in d.columns}
            if not (cl.get("cargo_cobertura") or cl.get("cobertura")):
                continue
            fecha = _snapshot_date(nm, r.get("last_modified"))
            if fecha is None:
                continue
            if mejor is None or fecha > mejor[0]:
                mejor = (fecha, d, nm)
    if mejor is None:
        raise RuntimeError("No encontré un recurso con cobertura en el dataset.")
    fecha, df, nm = mejor
    log.info("Snapshot elegido: %s (%s) — %s filas", nm, fecha.date(), len(df))
    return _es_jueces(df), fecha


# ──────────────────────────────────────────────────────────────────────────────
# Normalización e identidad del cargo (para el matching con los decretos del BORA)
# ──────────────────────────────────────────────────────────────────────────────
def normaliza(s: str) -> str:
    s = str(s)
    # Unificar el marcador de número ANTES de quitar acentos: el «º» de «Nº» se descompone
    # en «o» (Nº → NO) y se perdería el número del juzgado. Lo pasamos a «N » primero.
    s = re.sub(r"[Nn][º°ªᵒ]\s*", "N ", s)
    s = re.sub(r"\b[Nn]ro\.?\s*", "N ", s)
    s = re.sub(r"\b[Nn][uú]mero\s*", "N ", s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Sinónimos de jurisdicción: el decreto dice «Capital Federal»; el dataset «Ciudad
    # Autónoma de Buenos Aires». Unificamos a CABA para que matcheen.
    s = re.sub(r"\bCAPITAL FEDERAL\b", "CABA", s)
    s = re.sub(r"\bCIUDAD AUTONOMA DE BUENOS AIRES\b", "CABA", s)
    s = re.sub(r"\bCIUDAD DE BUENOS AIRES\b", "CABA", s)
    s = re.sub(r"\bC A B A\b", "CABA", s)
    return s


def tokens(s: str) -> set:
    return {t for t in normaliza(s).split() if t not in STOP and (len(t) > 1 or t.isdigit())}


def numero(s: str):
    m = re.search(r"\bN (\d+)\b", normaliza(s))
    return m.group(1) if m else None


def limpiar_organo(texto: str) -> str:
    """Recorta la coletilla del nombre del juez (… al doctor X / D.N.I. …)."""
    t = normaliza(texto)
    t = re.split(r"\bDOCTORA?\b|\bDOCTORES\b|\bDRA?\b|\bD N I\b", t)[0]
    return t.strip()


def organo_desde_bora(url: str) -> str:
    """Lee el cuerpo del decreto en el BORA y extrae el ÓRGANO al que se designa, cubriendo
    todos los tipos (juzgado, cámara, sala, tribunal oral, tribunal federal de juicio, etc.).
    Es la fuente autoritativa para el matching; el `organo` del radar queda como respaldo."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return ""
        t = re.sub(r"<[^>]+>", " ", r.text)
        t = re.sub(r"\s+", " ", t)
        m = re.search(
            r"\b(?:JUEZ|JUEZA|JUECES|VOCAL|MAGISTRAD\w*)\b\s+DE\s*L?\s+(?:LA\s+)?(.+?)"
            r"(?:,?\s+a\s+l[ao]\s+(?:doctora?|dra?)\b|,?\s+al\s+(?:doctora?|dr)\b|\(?\s*D\.?N\.?I|\.\s|$)",
            t, re.IGNORECASE)
        return m.group(1).strip() if m else ""
    except Exception:  # noqa: BLE001
        return ""


# ──────────────────────────────────────────────────────────────────────────────
# CONSTRUIR el padrón base desde el snapshot oficial
# ──────────────────────────────────────────────────────────────────────────────
def _estado(cobertura: str, vacante: str) -> str:
    c = (cobertura or "").strip().lower()
    v = (vacante or "").strip().upper() in ("SI", "SÍ")
    if c == "titular":
        return "Titular"
    if "sin subrogante" in c:
        return "Sin cobertura"
    if c == "subrogante":
        return "Subrogante"
    if v:
        return "Vacante"
    return (cobertura or "").strip() or "Otro"


def _g(cols, *names):
    for n in names:
        if n in cols:
            return cols[n]
    return None


def construir(verbose: bool = False) -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()
    df, fecha = latest_jueces_snapshot(s)
    cols = {c.lower(): c for c in df.columns}
    CAM = _g(cols, "camara"); TIP = _g(cols, "organo_tipo"); NOM = _g(cols, "organo_nombre")
    PRO = _g(cols, "organo_provincia"); JUR = _g(cols, "justicia_federal_o_nacional")
    HAB = _g(cols, "organo_habilitado"); MAG = _g(cols, "magistrado_nombre"); DNI = _g(cols, "magistrado_dni")
    CC = _g(cols, "cargo_cobertura", "cobertura"); CV = _g(cols, "cargo_vacante", "vacante")
    NT = _g(cols, "norma_tipo"); NN = _g(cols, "norma_numero", "norma"); NF = _g(cols, "norma_fecha")
    CO = _g(cols, "concurso_numero", "concurso")

    if verbose:
        print("\n=== COLUMNAS DEL DATASET (jueces) ===")
        print(list(df.columns))
        muestra = [c for c in [CAM, TIP, NOM, PRO, MAG, CC] if c]
        print("\n=== EJEMPLOS (8 cargos) ===")
        print(df[muestra].head(8).to_string(index=False))

    rows = []
    for _, r in df.iterrows():
        cam = str(r.get(CAM, "") or ""); nom = str(r.get(NOM, "") or ""); pro = str(r.get(PRO, "") or "")
        clave = normaliza(f"{cam} {nom} {pro}")
        rows.append({
            "jurisdiccion": str(r.get(JUR, "") or "").strip(),
            "camara": cam.strip(),
            "organo_tipo": str(r.get(TIP, "") or "").strip(),
            "organo_nombre": nom.strip(),
            "provincia": pro.strip(),
            "habilitado": str(r.get(HAB, "") or "").strip(),
            "estado": _estado(r.get(CC, ""), r.get(CV, "")),
            "cobertura_oficial": str(r.get(CC, "") or "").strip(),
            "magistrado": str(r.get(MAG, "") or "").strip(),
            "magistrado_dni": str(r.get(DNI, "") or "").strip(),
            "norma": (str(r.get(NT, "") or "").strip() + " " + str(r.get(NN, "") or "").strip()).strip(),
            "norma_fecha": str(r.get(NF, "") or "").strip(),
            "concurso": str(r.get(CO, "") or "").strip(),
            "estado_fuente": "oficial",
            "snapshot_fecha": str(fecha.date()),
            "evento_norma": "",
            "evento_fecha": "",
            "clave": clave,
        })
    pad = pd.DataFrame(rows)
    pad.insert(0, "cargo_id", (pad["clave"] + "#" + pad.groupby("clave").cumcount().astype(str)))
    pad.to_csv(PADRON_BASE, index=False, encoding="utf-8")
    pad.to_csv(PADRON, index=False, encoding="utf-8")
    log.info("Padrón base creado: %s cargos. Archivos: %s y %s", len(pad), PADRON_BASE.name, PADRON.name)
    print("\n=== ESTADOS (todos los cargos) ===")
    print(pad["estado"].value_counts().to_string())
    _imprimir_tasas(pad, etiqueta="oficial (base)")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# ACTUALIZAR el padrón con altas (radar) y bajas — matching por tokens + número
# ──────────────────────────────────────────────────────────────────────────────
def _filtrar_conf(d: pd.DataFrame, tipo: str) -> pd.DataFrame:
    d = d.fillna("")
    if "confianza" in d.columns:  # solo ALTA o confirmadas entran al valor
        conf = d["confianza"].str.upper().str.strip()
        m = conf.eq("ALTA")
        if "confirmado" in d.columns:
            cf = d["confirmado"].str.lower().str.strip()
            m = (m | cf.isin(["si", "sí", "true", "1"])) & ~cf.isin(["no", "false", "0"])
        d = d[m]
    d = d.copy()
    d["_tipo"] = tipo
    return d


def _cargar_eventos(path: Path, tipo: str, url: str = "") -> pd.DataFrame:
    """Lee eventos de la URL del repo (si está) o del archivo local; si ninguno, vacío."""
    if url:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200 and r.text.strip():
                log.info("%s: leído del repo (%s)", tipo, url)
                return _filtrar_conf(pd.read_csv(io.StringIO(r.text), dtype=str), tipo)
        except Exception as e:  # noqa: BLE001
            log.warning("No pude bajar %s del repo (%s); uso local. %s", tipo, url, e)
    if path.exists():
        return _filtrar_conf(pd.read_csv(path, dtype=str), tipo)
    return pd.DataFrame()


def _match(ev_org: str, pad: pd.DataFrame, umbral: float = 0.6):
    """Devuelve índices candidatos (ordenados por score desc) que superan el umbral y son
    compatibles en número de juzgado. Determinístico: containment de tokens del decreto."""
    D = tokens(ev_org); dn = numero(ev_org)
    if not D:
        return []
    puntajes = []
    for i, rt, rn in zip(pad.index, pad["_tok"], pad["_num"]):
        if dn and rn and dn != rn:
            continue
        sc = len(D & rt) / len(D)
        if sc >= umbral:
            puntajes.append((sc, i))
    puntajes.sort(reverse=True)
    return [i for _, i in puntajes]


def actualizar() -> int:
    if not PADRON_BASE.exists():
        log.error("No existe %s. Corré primero: padron_judicial.py --construir", PADRON_BASE.name)
        return 1
    pad = pd.read_csv(PADRON_BASE, dtype=str).fillna("")
    pad["_tok"] = (pad["camara"] + " " + pad["organo_nombre"] + " " + pad["provincia"]).map(tokens)
    pad["_num"] = pad["organo_nombre"].map(numero)

    altas = _cargar_eventos(RADAR_ALTAS, "alta", url=RADAR_ALTAS_URL)
    bajas = _cargar_eventos(RADAR_BAJAS, "baja")
    eventos = pd.concat([x for x in [altas, bajas] if len(x)], ignore_index=True) \
        if (len(altas) or len(bajas)) else pd.DataFrame()
    log.info("Eventos a aplicar: %s altas, %s bajas", len(altas), len(bajas))

    revision, aplicados = [], 0
    for _, ev in eventos.iterrows():
        # Autoritativo: leer el órgano del cuerpo del decreto; respaldo: el `organo` del radar.
        org_raw = organo_desde_bora(ev.get("url", "")) or ev.get("organo", "") or ev.get("titulo", "")
        org = limpiar_organo(org_raw)
        time.sleep(0.8)
        cand = _match(org, pad)
        if not cand:
            revision.append({**ev.to_dict(), "_motivo": "sin cargo coincidente", "_organo": org})
            continue
        objetivo = None
        for i in cand:                       # alta → un cargo NO titular; baja → uno Titular
            est = pad.at[i, "estado"]
            if ev["_tipo"] == "alta" and est != "Titular":
                objetivo = i; break
            if ev["_tipo"] == "baja" and est == "Titular":
                objetivo = i; break
        if objetivo is None:
            revision.append({**ev.to_dict(), "_motivo": f"match sin cargo en estado esperado ({ev['_tipo']})", "_organo": org})
            continue
        pad.at[objetivo, "estado"] = "Titular" if ev["_tipo"] == "alta" else "Vacante"
        pad.at[objetivo, "estado_fuente"] = "estimado-radar" if ev["_tipo"] == "alta" else "estimado-baja"
        pad.at[objetivo, "evento_norma"] = str(ev.get("titulo", ""))[:120]
        pad.at[objetivo, "evento_fecha"] = ev.get("fecha_publicacion", "") or ev.get("fecha_deteccion", "")
        aplicados += 1

    pad = pad.drop(columns=["_tok", "_num"])
    pad.to_csv(PADRON, index=False, encoding="utf-8")
    pd.DataFrame(revision).to_csv(REVISION, index=False, encoding="utf-8")
    log.info("Aplicados: %s | a revisión: %s", aplicados, len(revision))
    if revision:
        log.warning("%s evento(s) sin asignar → %s (revisión humana).", len(revision), REVISION.name)
    _imprimir_tasas(pad, etiqueta="estimado (vivo)")
    return 0


def _imprimir_tasas(pad: pd.DataFrame, etiqueta: str) -> None:
    base = pad[pad["habilitado"].astype(str).str.upper().isin(["SI", "SÍ"])] if "habilitado" in pad else pad
    n = max(len(base), 1)
    est = base["estado"].str.lower()
    fila = {"etiqueta": etiqueta, "n_cargos_habilitados": len(base),
            "tasa_titular": round((est == "titular").sum() / n, 4),
            "tasa_subrogancia": round((est == "subrogante").sum() / n, 4),
            "tasa_sin_cobertura": round((est == "sin cobertura").sum() / n, 4),
            "tasa_vacancia": round((est == "vacante").sum() / n, 4)}
    pd.DataFrame([fila]).to_csv(TASAS_EST, index=False, encoding="utf-8")
    print(f"\n=== TASAS [{etiqueta}] (sobre habilitados) ===")
    for k, v in fila.items():
        if k != "etiqueta":
            print(f"  {k}: {v}")


def main() -> int:
    ap = argparse.ArgumentParser(description="ITR — Padrón judicial vivo")
    ap.add_argument("--construir", action="store_true", help="crea el padrón base desde el snapshot oficial")
    ap.add_argument("--actualizar", action="store_true", help="aplica altas/bajas del BORA sobre el padrón")
    ap.add_argument("--verbose", action="store_true", help="vuelca columnas y ejemplos del dataset")
    args = ap.parse_args()
    if args.construir:
        return construir(verbose=args.verbose)
    if args.actualizar:
        return actualizar()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
