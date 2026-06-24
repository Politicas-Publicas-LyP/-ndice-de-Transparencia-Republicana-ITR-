"""
ICIA — Módulo 10: Integridad Pública (Poder Judicial, 10%)
===========================================================
La métrica original ("nuevos procesamientos a funcionarios") no tiene dataset
confiable. Sustitución acordada (opción A): ACTIVIDAD DE PERSECUCIÓN del sistema
anticorrupción, medida por la Procuraduría de Investigaciones Administrativas (PIA,
Ministerio Público Fiscal) — órgano oficial que investiga y acusa irregularidades
de funcionarios. Encaja en la categoría Judicial (Ministerio Público).

  integridad = denuncias penales de oficio promovidas por la PIA (por año)

CONVENCIÓN DE SIGNO (a revisar): bajo la mirada de frenos y contrapesos, un sistema
de control activo que persigue penalmente a funcionarios = mayor integridad
institucional (la accountability funciona). Existe la lectura inversa (más denuncias
= más corrupción); queda documentada para afinar en Sprint 6.

Fuente: Informes de Gestión anuales de la PIA (PDF). Cifras en prosa con fraseo
variable entre años -> valores VERIFICADOS como config autoritativo + auto-parse de
cross-check. Variable ESTRUCTURAL/anual -> serie mensual con stale_flag.

NOTA: es la variable más "afinables" del índice (métrica y signo a revisar).

Uso:
    py scraper_10_integridad.py --desde 2023-01 --hasta 2026-05
Requisitos: pip install pandas requests pdfplumber
"""
from __future__ import annotations

import argparse
import io
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
           "Accept": "*/*", "Accept-Language": "es-AR,es;q=0.9"}

PDFS = {
    2023: "https://www.mpf.gob.ar/pia/files/2024/03/Informe-anual-2023.pdf",
    2024: "https://www.mpf.gob.ar/pia/files/2025/04/PIA-informe-de-Gestion-2024.pdf",
    2025: "https://www.mpf.gob.ar/pia/files/2026/03/PIA-informe-de-Gestion-2025-2.pdf",
}
# Cifras verificadas de los informes PIA (config autoritativo).
# denuncias_penales = denuncias penales de oficio; sumarios_acus = sumarios como parte acusadora.
PIA_VERIFICADO = {
    2023: {"denuncias_penales": 24, "sumarios_acus": 89},
    2024: {"denuncias_penales": 41, "sumarios_acus": 70},
    2025: {"denuncias_penales": 18, "sumarios_acus": 73},
}

# --- Oficina Anticorrupción (OA): señal SECUNDARIA del control de la corrupción ---
# La OA depende del Poder Ejecutivo: su actividad tiene riesgo de endogeneidad política
# (p. ej. el pico 2024 incluye denuncias a la gestión anterior). Por eso entra con peso menor.
# Métrica: denuncias presentadas ante la justicia (informes de gestión anuales).
OA_PDFS = {
    2023: "https://www.argentina.gob.ar/sites/default/files/oa_-_informe_de_gestion_anual_-_2023.pdf",
    2024: "https://www.argentina.gob.ar/sites/default/files/informe_anual_2024_1.pdf",
    2025: "https://www.argentina.gob.ar/sites/default/files/informe_de_gestion_anual_2025_-_oa.pdf",
}
OA_VERIFICADO = {2023: 85, 2024: 159, 2025: 116}
OA_PATTERNS = [r"([\d.]+)\s+denuncias?\s+ante\s+la\s+justicia",
               r"([\d.]+)\s+denuncias?\s+por\s+hechos?\s+de\s+corrupci"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("integridad")


def session() -> requests.Session:
    s = requests.Session()
    r = Retry(total=3, backoff_factor=2.0, status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET"]))
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.headers.update(HEADERS)
    return s


def autoparse(anio: int, s: requests.Session) -> int | None:
    """Cross-check: intenta leer 'N denuncias penales de oficio' del PDF."""
    try:
        resp = s.get(PDFS[anio], timeout=90)
        if resp.status_code != 200 or "pdf" not in resp.headers.get("Content-Type", "").lower():
            return None
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            full = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:  # noqa: BLE001
        log.warning("PIA %s: no se pudo abrir el PDF (%s)", anio, e)
        return None
    m = re.search(r"(\d+)\s+denuncias?\s+penales?\s+de\s+oficio", full, re.IGNORECASE)
    return int(m.group(1)) if m else None


def autoparse_oa(anio: int, s: requests.Session) -> int | None:
    """Cross-check: denuncias de la OA presentadas ante la justicia."""
    try:
        resp = s.get(OA_PDFS[anio], timeout=90)
        if resp.status_code != 200 or "pdf" not in resp.headers.get("Content-Type", "").lower():
            return None
        with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
            full = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:  # noqa: BLE001
        log.warning("OA %s: no se pudo abrir el PDF (%s)", anio, e)
        return None
    for pat in OA_PATTERNS:
        m = re.search(pat, full, re.IGNORECASE)
        if m:
            return int(m.group(1).replace(".", ""))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="ICIA Módulo 10 — Integridad Pública (PIA)")
    ap.add_argument("--desde", default="2023-01")
    ap.add_argument("--hasta", default="2026-05")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    s = session()

    datos = {}
    for anio, v in PIA_VERIFICADO.items():
        d = dict(v)
        auto = autoparse(anio, s)
        if auto is not None and auto != v["denuncias_penales"]:
            log.warning("PIA %s: auto=%s vs verificado=%s -> uso verificado", anio, auto, v["denuncias_penales"])
        elif auto is not None:
            log.info("PIA %s: auto-parse OK (%s denuncias penales de oficio)", anio, auto)
        # OA (secundaria)
        oa_auto = autoparse_oa(anio, s)
        oa_verif = OA_VERIFICADO.get(anio)
        if oa_auto is not None and oa_verif is not None and oa_auto != oa_verif:
            log.warning("OA %s: auto=%s vs verificado=%s -> uso verificado", anio, oa_auto, oa_verif)
        elif oa_auto is not None:
            log.info("OA %s: auto-parse OK (%s denuncias ante la justicia)", anio, oa_auto)
        d["oa_denuncias"] = oa_verif if oa_verif is not None else oa_auto
        datos[anio] = d

    print("\n=== CONTROL DE LA CORRUPCIÓN — POR AÑO (auditar) ===")
    for a in sorted(datos):
        print(f"  {a}: [PIA núcleo] denuncias_penales_oficio={datos[a]['denuncias_penales']} | "
              f"sumarios_acusadora={datos[a]['sumarios_acus']}  ||  "
              f"[OA secundaria] denuncias_a_justicia={datos[a].get('oa_denuncias')}")

    # serie mensual estructural con stale_flag
    periods = pd.period_range(args.desde, args.hasta, freq="M")
    rows = []
    for p in periods:
        usable = [a for a in datos if a <= p.year]
        if not usable:
            rows.append({"periodo": str(p), "pia_denuncias_penales": float("nan"),
                         "pia_sumarios_acusadora": float("nan"), "oa_denuncias": float("nan"),
                         "stale_meses": float("nan")})
            continue
        a = max(usable)
        stale = 0 if a == p.year else (p - pd.Period(f"{a}-12", "M")).n
        rows.append({"periodo": str(p),
                     "pia_denuncias_penales": datos[a]["denuncias_penales"],
                     "pia_sumarios_acusadora": datos[a]["sumarios_acus"],
                     "oa_denuncias": datos[a].get("oa_denuncias", float("nan")),
                     "stale_meses": stale})
    serie = pd.DataFrame(rows)

    print("\n=== SERIE MENSUAL (cola) ===")
    print(serie.tail(18).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = OUTPUT_DIR / f"integridad_mensual_{stamp}.csv"
    serie.to_csv(out_csv, index=False, encoding="utf-8")
    log.info("CSV guardado en: %s", out_csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
