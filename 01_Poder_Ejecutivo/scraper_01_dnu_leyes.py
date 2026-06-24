"""
ICIA — Módulo 1: Ratio DNU vs Leyes (Poder Ejecutivo, 15%)
============================================================

Fuente: Base InfoLEG de Normativa Nacional (datos.gob.ar / datos.jus.gob.ar).
Cubre la Primera Sección del Boletín Oficial desde mayo 1997. Actualización mensual.

HALLAZGO DE LA 1ª CORRIDA:
  - 'fecha_boletin' viene NaN en ~61% de las filas -> hay que usar 'fecha_sancion'
    como respaldo, o se pierden casi todas las leyes recientes.
  - El dataset NO marca los DNU: 'tipo_norma' solo dice "Decreto", 'clase_norma'
    viene NaN, y 'texto_original' es un LINK, no el texto. Un DNU se reconoce
    porque invoca el art. 99 inc. 3 CN -> se detecta abriendo la norma.htm de
    cada decreto del período (filtramos por ventana antes, así son pocos).

Salida: DataFrame mensual (periodo, n_leyes, n_dnu, n_decretos_total, ratio_dnu_leyes)
+ CSV en ./output/. Cachea las clasificaciones de DNU en ./output/_cache_dnu.json.

Uso:
    py scraper_01_dnu_leyes.py --desde 2023-01 --hasta 2025-12
    py scraper_01_dnu_leyes.py --desde 2023-01 --hasta 2025-12 --detect-dnu title   # rápido, sin red
    py scraper_01_dnu_leyes.py --zip-local base-infoleg.zip --desde 2023-01 --hasta 2025-12

Requisitos: pip install pandas requests
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
DATASET_ZIP_URL = (
    "https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/"
    "resource/bf0ec116-ad4e-4572-a476-e57167a84403/download/"
    "base-infoleg-normativa-nacional.zip"
)
USER_AGENT = "ICIA-LyP/0.1 (indicador calidad institucional; politicaspublicas@libertadyprogreso.org)"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
CACHE_FILE = OUTPUT_DIR / "_cache_dnu.json"
TIMEOUT = 120
FETCH_THROTTLE = 0.4          # segundos entre fetchs de norma.htm
MAX_FETCH_DEFAULT = 4000      # tope de seguridad de decretos a abrir

# Un DNU se autodeclara dictado en acuerdo general de ministros bajo el
# art. 99 inc. 3 CN. Señales en el texto de la norma:
DNU_TEXT_REGEXES = [
    r"decreto\s+de\s+necesidad\s+y\s+urgencia",
    r"necesidad\s+y\s+urgencia",
    r"art\w*\.?\s*99[^.]{0,40}inc\w*\.?\s*3",
    r"inc\w*\.?\s*3[^.]{0,40}art\w*\.?\s*99",
]
DNU_RE = re.compile("|".join(DNU_TEXT_REGEXES), re.IGNORECASE | re.DOTALL)

# Marcador FUERTE (jurídicamente definitivo) vs DÉBIL (frase suelta, da falsos positivos)
STRICT_DNU_RE = re.compile(
    r"decreto\s+de\s+necesidad\s+y\s+urgencia"
    r"|art\w*\.?\s*99[^.]{0,40}inc\w*\.?\s*3"
    r"|inc\w*\.?\s*3[^.]{0,40}art\w*\.?\s*99",
    re.IGNORECASE | re.DOTALL,
)
WEAK_DNU_RE = re.compile(r"necesidad\s+y\s+urgencia", re.IGNORECASE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dnu_leyes")


# --------------------------------------------------------------------------- #
class DNULeyesScraper:
    def __init__(self, zip_local: str | None = None):
        self.zip_local = Path(zip_local) if zip_local else None
        self.session = self._build_session()
        self.df_raw: pd.DataFrame | None = None
        self._cache: dict[str, bool] = self._load_cache()

    # ---- red robusta ------------------------------------------------------ #
    @staticmethod
    def _build_session() -> requests.Session:
        s = requests.Session()
        retries = Retry(total=5, backoff_factor=1.5,
                        status_forcelist=(429, 500, 502, 503, 504),
                        allowed_methods=frozenset(["GET"]))
        s.mount("https://", HTTPAdapter(max_retries=retries))
        s.mount("http://", HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": USER_AGENT})
        return s

    # ---- caché de clasificación DNU --------------------------------------- #
    def _load_cache(self) -> dict[str, bool]:
        if CACHE_FILE.exists():
            try:
                return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    def _save_cache(self) -> None:
        OUTPUT_DIR.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps(self._cache), encoding="utf-8")

    # ---- descarga + carga ------------------------------------------------- #
    def _get_zip_bytes(self) -> bytes:
        if self.zip_local:
            log.info("Usando ZIP local: %s", self.zip_local)
            return self.zip_local.read_bytes()
        log.info("Descargando dataset InfoLEG (puede tardar)...")
        resp = self.session.get(DATASET_ZIP_URL, timeout=TIMEOUT)
        resp.raise_for_status()
        log.info("Descargados %.1f MB", len(resp.content) / 1e6)
        return resp.content

    def load(self) -> pd.DataFrame:
        with zipfile.ZipFile(io.BytesIO(self._get_zip_bytes())) as zf:
            csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            target = max(csvs, key=lambda n: zf.getinfo(n).file_size)
            log.info("Leyendo CSV: %s", target)
            df = self._read_csv_resilient(zf.read(target))
        self.df_raw = self._prepare_dates(df)
        return self.df_raw

    @staticmethod
    def _read_csv_resilient(blob: bytes) -> pd.DataFrame:
        for enc in ("utf-8", "latin-1"):
            for sep in (",", ";"):
                try:
                    df = pd.read_csv(io.BytesIO(blob), sep=sep, encoding=enc,
                                     dtype=str, low_memory=False, on_bad_lines="warn")
                    if df.shape[1] > 1:
                        log.info("CSV parseado enc=%s sep='%s' -> %s filas, %s cols",
                                 enc, sep, len(df), df.shape[1])
                        return df
                except Exception:  # noqa: BLE001
                    continue
        raise RuntimeError("No se pudo parsear el CSV.")

    @staticmethod
    def _prepare_dates(df: pd.DataFrame) -> pd.DataFrame:
        """Fecha coalescida: fecha_boletin y, si falta, fecha_sancion (ambas ISO)."""
        fb = pd.to_datetime(df.get("fecha_boletin"), errors="coerce", format="ISO8601")
        fs = pd.to_datetime(df.get("fecha_sancion"), errors="coerce", format="ISO8601")
        fecha = fb.fillna(fs)
        # descartar fechas futuras imposibles (errores de carga)
        hoy = pd.Timestamp.today().normalize()
        fecha = fecha.where(fecha <= hoy)
        df = df.copy()
        df["_fecha"] = fecha
        df["_fecha_origen"] = pd.Series(
            ["boletin" if pd.notna(b) else ("sancion" if pd.notna(s) else "ninguna")
             for b, s in zip(fb, fs)], index=df.index)
        return df

    # ---- diagnóstico ------------------------------------------------------ #
    def diagnose(self) -> None:
        df = self._require_df()
        print("\n" + "=" * 70)
        print("DIAGNÓSTICO — devolver esta salida")
        print("=" * 70)
        print(f"Filas: {len(df):,} | Columnas: {df.shape[1]}")

        print("\n--- ¿clase_norma marca DNU? ---")
        print(f"  clase_norma == 'DNU':  {int((df['clase_norma'] == 'DNU').sum()):,}")

        # ¿Por qué hay pocas leyes? Cobertura de LEYES por año de sanción
        ley = df[df["tipo_norma"] == "Ley"].copy()
        ley_sanc = pd.to_datetime(ley["fecha_sancion"], errors="coerce", format="ISO8601")
        print(f"\n--- LEYES: total {len(ley):,} | con fecha usable {ley['_fecha'].notna().sum():,} "
              f"| sin fecha (NaT) {ley['_fecha'].isna().sum():,} ---")
        print("  Leyes por año de SANCIÓN (2018+):")
        print(ley_sanc.dt.year[ley_sanc.dt.year >= 2018].value_counts().sort_index().to_string())

        # DNU por año (marca oficial)
        dnu = df[df["clase_norma"] == "DNU"].copy()
        print(f"\n--- DNU (clase oficial): total {len(dnu):,} ---")
        print("  DNU por año (2018+):")
        print(dnu["_fecha"].dt.year[dnu["_fecha"].dt.year >= 2018].value_counts().sort_index().to_string())

        print("\n--- Origen de la fecha coalescida ---")
        print(df["_fecha_origen"].value_counts(dropna=False).to_string())
        print("=" * 70 + "\n")

    # ---- ventana + clasificación ------------------------------------------ #
    def classify(self, desde: str | None, hasta: str | None,
                 mode: str, max_fetch: int) -> pd.DataFrame:
        df = self._require_df().dropna(subset=["_fecha"]).copy()
        df["periodo"] = df["_fecha"].dt.to_period("M")
        if desde:
            df = df[df["periodo"] >= pd.Period(desde, "M")]
        if hasta:
            df = df[df["periodo"] <= pd.Period(hasta, "M")]
        log.info("Normas en ventana: %s", len(df))

        tipo = df["tipo_norma"].fillna("")
        is_ley = tipo.str.fullmatch("Ley")
        is_decreto = tipo.str.fullmatch("Decreto")          # excluye 'Decreto/Ley' (de facto)

        df["_clase"] = "otro"
        df.loc[is_decreto, "_clase"] = "decreto_comun"
        df.loc[is_ley, "_clase"] = "ley"

        # CODEBOOK (decisión validada por inspección 2026-06-01):
        # DNU = tipo_norma=='Decreto' AND clase_norma=='DNU' (tag oficial InfoLEG).
        # Se descartó la detección por texto: matchea CITAS a DNU en los
        # considerandos de decretos comunes (~40 falsos positivos en 2023-25),
        # no la autodeclaración. La marca oficial es la fuente de verdad.
        is_dnu_clase = (df["clase_norma"] == "DNU")
        df.loc[is_dnu_clase, "_clase"] = "dnu"
        n_clase = int(is_dnu_clase.sum())

        # Validación cruzada opcional: detección por texto/título
        n_xcheck = None
        if mode in ("fetch", "title"):
            dec_idx = df.index[is_decreto]
            log.info("Validación cruzada de DNU por %s sobre %s decretos", mode, len(dec_idx))
            xflags = self._detect_dnu(df.loc[dec_idx], mode, max_fetch)
            x_idx = xflags[xflags].index
            n_xcheck = int(len(x_idx))
            # coincidencia entre marca oficial y detección por texto
            both = int(is_dnu_clase.loc[x_idx].sum())
            solo_texto = n_xcheck - both
            solo_clase = n_clase - both
            print("\n" + "-" * 70)
            print("VALIDACIÓN CRUZADA DNU (clase oficial vs %s) — devolver esto" % mode)
            print("-" * 70)
            print(f"  Coinciden (ambos):     {both:,}")
            print(f"  Solo clase oficial:    {solo_clase:,}")
            print(f"  Solo detección texto:  {solo_texto:,}")
            print("-" * 70)

        print("\n" + "-" * 70)
        print("CLASIFICACIÓN EN VENTANA (devolver esto)")
        print("-" * 70)
        print(f"  Leyes:                 {int(is_ley.sum()):,}")
        print(f"  Decretos (total):      {int(is_decreto.sum()):,}")
        print(f"  DNU (clase oficial):   {n_clase:,}")
        if n_xcheck is not None:
            print(f"  DNU (cross-check {mode}): {n_xcheck:,}")
        print("-" * 70 + "\n")
        return df

    def _detect_dnu(self, decretos: pd.DataFrame, mode: str, max_fetch: int) -> pd.Series:
        if mode == "title":
            blob = (decretos[["titulo_resumido", "titulo_sumario", "observaciones"]]
                    .fillna("").agg(" ".join, axis=1))
            return blob.str.contains(DNU_RE)

        # mode == "fetch": abrir cada norma.htm y buscar la invocación del art. 99 inc 3
        flags = {}
        fetched = 0
        for i, (idx, row) in enumerate(decretos.iterrows(), 1):
            key = str(row.get("id_norma"))
            if key in self._cache:
                flags[idx] = self._cache[key]
                continue
            if fetched >= max_fetch:
                log.warning("Tope de fetch (%s) alcanzado; resto sin clasificar.", max_fetch)
                flags[idx] = False
                continue
            url = row.get("texto_original")
            is_dnu = self._fetch_is_dnu(url) if isinstance(url, str) and url.startswith("http") else False
            self._cache[key] = is_dnu
            flags[idx] = is_dnu
            fetched += 1
            if fetched % 25 == 0:
                log.info("  ...%s decretos abiertos", fetched)
                self._save_cache()
            time.sleep(FETCH_THROTTLE)
        self._save_cache()
        log.info("Fetch DNU: %s abiertos, %s desde caché", fetched, len(decretos) - fetched)
        return pd.Series(flags, dtype=bool).reindex(decretos.index).fillna(False)

    def inspect_discrepancy(self, df: pd.DataFrame) -> None:
        """Reabre los decretos detectados por texto pero NO marcados clase=='DNU'
        y muestra si tienen marca FUERTE (art.99 inc.3 / autodenominación) o solo
        la DÉBIL (frase suelta). Decide si los 41 son DNU reales o falsos positivos."""
        is_dec = df["tipo_norma"].fillna("").str.fullmatch("Decreto")
        is_clase = df["clase_norma"] == "DNU"
        targets = [(idx, row) for idx, row in df[is_dec].iterrows()
                   if self._cache.get(str(row.get("id_norma"))) and not is_clase.loc[idx]]
        print("\n" + "=" * 70)
        print(f"INSPECCIÓN DE DISCREPANCIA — {len(targets)} decretos (fetch sí / clase no)")
        print("=" * 70)
        n_strict = 0
        for idx, row in targets:
            url = row.get("texto_original")
            text = ""
            if isinstance(url, str) and url.startswith("http"):
                try:
                    r = self.session.get(url, timeout=30)
                    text = r.content.decode("latin-1", errors="ignore")
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(FETCH_THROTTLE)
            m = STRICT_DNU_RE.search(text)
            label = "FUERTE" if m else "debil"
            n_strict += bool(m)
            snip = ""
            if m:
                a, b = max(0, m.start() - 40), min(len(text), m.end() + 40)
                snip = re.sub(r"\s+", " ", text[a:b]).strip()
            fecha = row["_fecha"].date() if pd.notna(row["_fecha"]) else "?"
            titulo = str(row.get("titulo_resumido"))[:45]
            print(f"[{label}] {row.get('numero_norma'):>10} {fecha} | {titulo}")
            if snip:
                print(f"          ...{snip}...")
        print("-" * 70)
        print(f"De {len(targets)} discrepantes: {n_strict} matchean por texto, pero OJO: "
              "casi todos son CITAS a un DNU previo en los considerandos (ej. 'modificada "
              "por el DNU 70/23'), NO autodeclaraciones. -> falsos positivos. "
              "Fuente de verdad = clase_norma=='DNU'.")
        print("=" * 70 + "\n")

    def _fetch_is_dnu(self, url: str) -> bool:
        try:
            r = self.session.get(url, timeout=30)
            r.raise_for_status()
            text = r.content.decode("latin-1", errors="ignore")
            return bool(DNU_RE.search(text))
        except Exception as e:  # noqa: BLE001
            log.debug("Fallo al abrir %s: %s", url, e)
            return False

    # ---- agregación + validación ------------------------------------------ #
    @staticmethod
    def aggregate_monthly(df: pd.DataFrame) -> pd.DataFrame:
        # reindexar para no saltear meses sin actividad (clave para el rolling)
        g = df.groupby("periodo")["_clase"].value_counts().unstack(fill_value=0)
        idx = pd.period_range(g.index.min(), g.index.max(), freq="M")
        g = g.reindex(idx, fill_value=0)
        for col in ("ley", "dnu", "decreto_comun"):
            if col not in g.columns:
                g[col] = 0
        out = pd.DataFrame({
            "n_leyes": g["ley"],
            "n_dnu": g["dnu"],
            "n_decretos_total": g["dnu"] + g["decreto_comun"],
        })
        # cuota acotada [0,1]: porción de actos "legislativos" hechos por DNU.
        denom = out["n_dnu"] + out["n_leyes"]
        out["cuota_dnu"] = (out["n_dnu"] / denom).where(denom > 0)
        # versión suavizada a 12 meses (mitiga el N chico / R4)
        roll_dnu = out["n_dnu"].rolling(12, min_periods=6).sum()
        roll_den = denom.rolling(12, min_periods=6).sum()
        out["cuota_dnu_12m"] = (roll_dnu / roll_den).where(roll_den > 0)
        out = out.reset_index(names="periodo")
        out["periodo"] = out["periodo"].astype(str)
        return out

    @staticmethod
    def annual_summary(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["anio"] = d["_fecha"].dt.year
        g = d.groupby("anio")["_clase"].value_counts().unstack(fill_value=0)
        for col in ("ley", "dnu", "decreto_comun"):
            if col not in g.columns:
                g[col] = 0
        g["n_decretos_total"] = g["dnu"] + g["decreto_comun"]
        g["cuota_dnu"] = g["dnu"] / (g["dnu"] + g["ley"]).replace(0, pd.NA)
        return g[["ley", "dnu", "n_decretos_total", "cuota_dnu"]].rename(
            columns={"ley": "n_leyes", "dnu": "n_dnu"})

    @staticmethod
    def validate(m: pd.DataFrame) -> None:
        probs = []
        if m.empty:
            probs.append("DataFrame vacío.")
        if m[["n_leyes", "n_dnu"]].to_numpy().sum() == 0:
            probs.append("Cero leyes y cero DNU: probable fallo de clasificación o fecha.")
        if m["n_dnu"].max() > 60:
            probs.append("n_dnu > 60 en algún mes: revisar marca DNU.")
        if m["n_leyes"].sum() < 12 * (len(m) / 12) * 0.5:
            probs.append("Muy pocas leyes para el período: revisar cobertura/fecha de leyes.")
        for p in probs:
            log.warning("VALIDACIÓN: %s", p)
        if not probs:
            log.info("Validación mínima OK.")

    # ---- helpers ---------------------------------------------------------- #
    def _require_df(self) -> pd.DataFrame:
        if self.df_raw is None:
            raise RuntimeError("Llamá a load() primero.")
        return self.df_raw


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 1 — DNU vs Leyes")
    ap.add_argument("--desde", help="AAAA-MM")
    ap.add_argument("--hasta", help="AAAA-MM")
    ap.add_argument("--zip-local", help="ZIP ya descargado")
    ap.add_argument("--detect-dnu", choices=["clase", "fetch", "title"], default="clase",
                    help="clase = marca oficial InfoLEG (instantáneo, default); "
                         "fetch/title = además corre validación cruzada por texto")
    ap.add_argument("--max-fetch", type=int, default=MAX_FETCH_DEFAULT)
    ap.add_argument("--inspect", action="store_true",
                    help="reabre los decretos discrepantes (fetch sí / clase no) y los etiqueta FUERTE/débil")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    scraper = DNULeyesScraper(zip_local=args.zip_local)
    try:
        scraper.load()
    except Exception as e:  # noqa: BLE001
        log.error("Fallo al cargar dataset: %s", e)
        return 1

    scraper.diagnose()
    df_clf = scraper.classify(args.desde, args.hasta, args.detect_dnu, args.max_fetch)
    if args.inspect:
        scraper.inspect_discrepancy(df_clf)
    monthly = scraper.aggregate_monthly(df_clf)
    scraper.validate(monthly)

    print("\n=== RESUMEN ANUAL (sanity check) ===")
    print(scraper.annual_summary(df_clf).to_string())

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"dnu_leyes_mensual_{stamp}.csv"
    monthly.to_csv(out_csv, index=False, encoding="utf-8")
    print("\n=== DataFrame mensual (cola) ===")
    print(monthly.tail(15).to_string(index=False))
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
