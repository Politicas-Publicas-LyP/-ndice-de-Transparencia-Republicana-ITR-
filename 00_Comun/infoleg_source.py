"""
ICIA — Fuente compartida InfoLEG
=================================
Cargador común del dataset "Base InfoLEG de Normativa Nacional" (datos.jus.gob.ar).
Lo usan el Módulo 1 (DNU vs Leyes) y el Módulo 2 (Calidad Normativa). Centraliza
descarga robusta, parseo resiliente y fecha coalescida (fecha_boletin -> fecha_sancion).

Requisitos: pip install pandas requests
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DATASET_ZIP_URL = (
    "https://datos.jus.gob.ar/dataset/d9a963ea-8b1d-4ca3-9dd9-07a4773e8c23/"
    "resource/bf0ec116-ad4e-4572-a476-e57167a84403/download/"
    "base-infoleg-normativa-nacional.zip"
)
USER_AGENT = "ICIA-LyP/0.1 (indicador calidad institucional; politicaspublicas@libertadyprogreso.org)"
TIMEOUT = 120

log = logging.getLogger("infoleg")


def build_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1.5,
                    status_forcelist=(429, 500, 502, 503, 504),
                    allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _get_zip_bytes(session: requests.Session, zip_local: str | None) -> bytes:
    if zip_local:
        log.info("Usando ZIP local: %s", zip_local)
        return Path(zip_local).read_bytes()
    log.info("Descargando dataset InfoLEG (puede tardar)...")
    resp = session.get(DATASET_ZIP_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    log.info("Descargados %.1f MB", len(resp.content) / 1e6)
    return resp.content


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


def _prepare_dates(df: pd.DataFrame) -> pd.DataFrame:
    fb = pd.to_datetime(df.get("fecha_boletin"), errors="coerce", format="ISO8601")
    fs = pd.to_datetime(df.get("fecha_sancion"), errors="coerce", format="ISO8601")
    fecha = fb.fillna(fs)
    fecha = fecha.where(fecha <= pd.Timestamp.today().normalize())   # descarta futuras
    df = df.copy()
    df["_fecha"] = fecha
    return df


def load_infoleg_df(zip_local: str | None = None,
                    session: requests.Session | None = None) -> pd.DataFrame:
    """Descarga (o lee local) y devuelve el DataFrame con columna _fecha lista."""
    session = session or build_session()
    raw = _get_zip_bytes(session, zip_local)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        csvs = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        target = max(csvs, key=lambda n: zf.getinfo(n).file_size)
        log.info("Leyendo CSV: %s", target)
        df = _read_csv_resilient(zf.read(target))
    return _prepare_dates(df)
