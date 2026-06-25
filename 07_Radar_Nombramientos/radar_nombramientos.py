"""
ITR — Radar de Nombramientos Judiciales (Boletín Oficial)
=========================================================
Radar INDEPENDIENTE (no pisa el Radar de Desregulación). Escanea la Primera Sección del
Boletín Oficial y detecta los DECRETOS DE DESIGNACIÓN DE JUECES TITULARES (nombramiento del
Poder Ejecutivo con acuerdo del Senado, art. 99 inc. 4 CN). Le da CADENCIA al flujo de
nombramientos del eje Judicial del ITR, que de otro modo depende del dataset de magistrados
(que se actualiza ~cada 2 años).

CÓMO LEE EL BORA
----------------
La Primera Sección se obtiene por fecha exacta:  /seccion/primera/AAAAMMDD  (render del
servidor, sin JS). El título del enlace de cada norma es del tipo
"JUSTICIA Decreto 545/2026 DECTO-2026-545-APN-PTE - Nombramiento." — NO dice "juez". El
asunto real ("Nómbrase JUEZ DEL JUZGADO…", "acuerdo prestado por el H. SENADO…") está en el
CUERPO de la ficha. Por eso el radar toma como candidata toda norma de Justicia/Nombramiento
y DECIDE leyendo el cuerpo, no el título.

SALIDA — puente con el índice: append idempotente a  output/nombramientos_jueces.csv
(fecha_deteccion, fecha_publicacion, tipo, organo, confianza, motivo, titulo, url).
El scraper de Cobertura Judicial lo lee y toma max(fecha dataset, fecha radar) para el flujo.

GOBERNANZA (línea no-IA del ITR): el radar es ALERTA/insumo. Las filas ALTA son designaciones
de juez titular casi seguras (decreto + nómbrase juez + acuerdo del Senado). El valor publicado
se confirma con revisión humana (columna 'confianza' / 'confirmado').

Uso:
    py radar_nombramientos.py                       # escanea el BORA de hoy
    py radar_nombramientos.py --fecha 2026-06-25     # escanea una fecha puntual
    py radar_nombramientos.py --desde 2026-06-01     # corrida histórica (hasta = hoy)
    py radar_nombramientos.py --desde 2026-06-01 --hasta 2026-06-25
    py radar_nombramientos.py --test                 # prueba la detección (sin red)
Requisitos: pip install requests beautifulsoup4
"""
from __future__ import annotations
import argparse, csv, re, sys, time, unicodedata
from datetime import datetime, timedelta, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL_BORA_BASE = "https://www.boletinoficial.gob.ar"
URL_PRIMERA_SECCION = f"{URL_BORA_BASE}/seccion/primera"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept-Language": "es-AR,es;q=0.9"}
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
CSV_PUENTE = OUTPUT_DIR / "nombramientos_jueces.csv"
DELAY = 1.0          # pausa entre lecturas de fichas
DELAY_DIA = 0.4      # pausa entre días en el modo histórico

# --- Detección de designaciones de JUECES TITULARES (sobre el cuerpo de la norma) ---
VERBO  = re.compile(r"\b(DESIGNA|DESIGNASE|DESIGNANSE|NOMBRA|NOMBRASE|NOMBRANSE|DESIGNAR|DESIGNACION)\b")
JUEZ   = re.compile(r"\b(JUEZ|JUEZA|JUECES|MAGISTRAD\w*|CAMARISTA|VOCAL DE LA CAMARA)\b")
ORGANO = re.compile(r"(JUZGADO[^,.;]{0,90}|CAMARA (?:FEDERAL|NACIONAL)[^,.;]{0,90}|TRIBUNAL ORAL[^,.;]{0,90})")
SENADO = re.compile(r"\b(SENADO|ACUERDO PRESTADO|ACUERDO DEL? (?:HONORABLE )?SENADO)\b")
SUBROGA = re.compile(r"\bSUBROGA\w*")
# Pre-filtro de candidatas por TÍTULO del enlace (el cuerpo decide después).
CAND = re.compile(r"NOMBRAMIENTO|DESIGNA|\bJUEZ|\bJUEZA|MAGISTRAD|PODER JUDICIAL")


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).upper().strip()


def es_candidata(titulo_norm: str) -> bool:
    if CAND.search(titulo_norm):
        return True
    return "JUSTICIA" in titulo_norm and "DECRETO" in titulo_norm


def _fecha_de_url(url: str):
    """La fecha de publicación va en la URL: /detalleAviso/primera/<id>/AAAAMMDD."""
    m = re.search(r"/(\d{8})(?:\?|$)", url)
    if m:
        s = m.group(1)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def get_con_reintentos(url, timeout=30, intentos=4, espera=8):
    for i in range(1, intentos + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code < 500:
                return r
        except requests.exceptions.RequestException as e:
            print(f"  red {i}/{intentos}: {e}")
        if i < intentos:
            time.sleep(espera)
    return None


def obtener_lista_bora(fecha_compacta: str | None = None):
    """Lista de normas de la Primera Sección de una fecha (AAAAMMDD) o de hoy si None.
    Devuelve (normas, ok); cada norma = {titulo, url, fecha}."""
    url = f"{URL_PRIMERA_SECCION}/{fecha_compacta}" if fecha_compacta else URL_PRIMERA_SECCION
    r = get_con_reintentos(url)
    if r is None or r.status_code != 200:
        return [], False
    soup = BeautifulSoup(r.text, "html.parser")
    normas, vistas = [], set()
    for link in soup.find_all("a", href=True):
        href = link["href"]
        texto = link.get_text(" ", strip=True)
        if "detalleAviso" in href and len(texto) > 8:
            full = URL_BORA_BASE + href if href.startswith("/") else href
            full = full.split("?")[0]  # normalizar (sacar ?anexos=1)
            if full in vistas:
                continue
            vistas.add(full)
            normas.append({"titulo": texto, "url": full, "fecha": _fecha_de_url(full)})
    return normas, True


def obtener_texto_norma(url):
    """Cuerpo del aviso (entre 'Ver texto del aviso' y 'Compartir por email')."""
    r = get_con_reintentos(url, timeout=20, intentos=2, espera=4)
    if r is None or r.status_code != 200:
        return ""
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        tp = soup.get_text(" ", strip=True)
        ini = tp.find("Ver texto del aviso")
        ini = ini + len("Ver texto del aviso") if ini != -1 else 0
        fin = tp.find("Compartir por email", ini)
        if fin == -1:
            m = re.search(r"Fecha de publicaci", tp[ini:])
            fin = ini + m.start() if m else len(tp)
        return tp[ini:fin].strip()
    except Exception as e:  # noqa: BLE001
        print(f"  parseo {url}: {e}")
        return ""


def detectar(texto_norm: str):
    """(confianza, organo, motivo) si parece designación de juez titular; si no, None."""
    tiene_juez = bool(JUEZ.search(texto_norm))
    tiene_verbo = bool(VERBO.search(texto_norm))
    tiene_senado = bool(SENADO.search(texto_norm))
    es_decreto = "DECRETO" in texto_norm
    es_subroga = bool(SUBROGA.search(texto_norm))
    if not (tiene_juez and (tiene_verbo or tiene_senado)):
        return None
    # Subrogancia SIN acuerdo del Senado = reemplazo removible, no titular → fuera.
    if es_subroga and not tiene_senado:
        return None
    if es_decreto and tiene_verbo and tiene_juez and tiene_senado:
        conf = "ALTA"
    elif tiene_juez and tiene_verbo and (es_decreto or tiene_senado):
        conf = "MEDIA"
    else:
        conf = "BAJA"
    mo = ORGANO.search(texto_norm)
    organo = mo.group(0).strip()[:90] if mo else ""
    motivo = "+".join([s for s, ok in [("decreto", es_decreto), ("designa", tiene_verbo),
                                        ("juez", tiene_juez), ("senado", tiene_senado)] if ok])
    return conf, organo, motivo


def cargar_existentes():
    if not CSV_PUENTE.exists():
        return set()
    with CSV_PUENTE.open(encoding="utf-8") as f:
        return {row["url"].split("?")[0] for row in csv.DictReader(f)}


def append_filas(filas):
    nuevo = not CSV_PUENTE.exists()
    OUTPUT_DIR.mkdir(exist_ok=True)
    cols = ["fecha_deteccion", "fecha_publicacion", "tipo", "organo", "confianza", "motivo", "titulo", "url"]
    with CSV_PUENTE.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if nuevo:
            w.writeheader()
        for fila in filas:
            w.writerow(fila)


def procesar(normas, hoy, fecha_filtrar: str | None = None):
    """Lee el cuerpo de las candidatas, corre la detección y devuelve filas nuevas."""
    vistas = cargar_existentes()
    cand = [n for n in normas if es_candidata(normalizar(n["titulo"]))]
    if fecha_filtrar:
        cand = [n for n in cand if (n.get("fecha") or fecha_filtrar) == fecha_filtrar]
    filas = []
    for n in cand:
        if n["url"] in vistas:
            continue
        cuerpo = obtener_texto_norma(n["url"])
        tn = normalizar(f"{n['titulo']} {cuerpo}")
        det = detectar(tn)
        if det:
            conf, organo, motivo = det
            tipo = "Decreto" if "DECRETO" in normalizar(n["titulo"]) else "Otro"
            fpub = n.get("fecha") or fecha_filtrar or hoy
            filas.append({"fecha_deteccion": hoy, "fecha_publicacion": fpub, "tipo": tipo,
                          "organo": organo, "confianza": conf, "motivo": motivo,
                          "titulo": n["titulo"][:300], "url": n["url"]})
        vistas.add(n["url"])
        time.sleep(DELAY)
    return filas


def _hoy_ar():
    return (datetime.utcnow() - timedelta(hours=3))


def escanear(fecha: str | None = None):
    """Escaneo de un día (hoy por defecto, o --fecha YYYY-MM-DD)."""
    d = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else _hoy_ar().date()
    hoy = _hoy_ar().strftime("%Y-%m-%d")
    iso = d.strftime("%Y-%m-%d"); compact = d.strftime("%Y%m%d")
    print(f"BORA Primera Sección — edición {iso}")
    normas, ok = obtener_lista_bora(compact)
    if not ok:
        print("FALLO: no se pudo leer el BORA (no se concluye 'sin novedades')."); return 1
    print(f"  {len(normas)} normas en la edición.")
    if len(normas) == 0:
        print("  Aviso: 0 normas — puede que la edición de hoy aún no esté publicada."); return 0
    filas = procesar(normas, hoy, fecha_filtrar=iso)
    _reportar(filas)
    return 0


def escanear_historico(desde: str, hasta: str):
    """Corrida ÚNICA de recuperación: capta designaciones publicadas en [desde, hasta],
    leyendo el BORA por fecha exacta (sin Vigía). Idempotente (dedup por URL)."""
    d0 = datetime.strptime(desde, "%Y-%m-%d").date()
    d1 = datetime.strptime(hasta, "%Y-%m-%d").date()
    hoy = _hoy_ar().strftime("%Y-%m-%d")
    print(f"HISTÓRICO — BORA Primera Sección de {desde} a {hasta} (lectura directa por fecha)")
    todas = []
    d = d0
    while d <= d1:
        iso = d.strftime("%Y-%m-%d"); compact = d.strftime("%Y%m%d")
        if d.weekday() >= 5:   # sáb/dom: el BORA no publica
            d += timedelta(days=1); continue
        normas, ok = obtener_lista_bora(compact)
        if not ok:
            print(f"  {iso}: no se pudo leer (se omite, revisar manual)."); d += timedelta(days=1); continue
        filas = procesar(normas, hoy, fecha_filtrar=iso)
        if filas:
            print(f"  {iso}: {len(filas)} designación(es).")
            todas.extend(filas)
        time.sleep(DELAY_DIA)
        d += timedelta(days=1)
    _reportar(todas)
    return 0


def _reportar(filas):
    if not filas:
        print("  Sin designaciones judiciales nuevas."); return
    append_filas(filas)
    n_alta = sum(1 for f in filas if f["confianza"] == "ALTA")
    print(f"  ✅ {len(filas)} designación(es) agregadas a {CSV_PUENTE.name} ({n_alta} ALTA):")
    for d in sorted(filas, key=lambda x: (x["fecha_publicacion"], x["confianza"])):
        print(f"     {d['fecha_publicacion']} [{d['confianza']}] {d['organo'] or d['titulo'][:70]}")


def test():
    cuerpo_real = ("VISTO el acuerdo prestado por el H. SENADO DE LA NACION y en uso de las "
                   "facultades del articulo 99 inciso 4 de la CONSTITUCION NACIONAL. EL PRESIDENTE "
                   "DECRETA: Nombrase JUEZ DEL JUZGADO NACIONAL DE PRIMERA INSTANCIA EN LO CIVIL "
                   "N 25 DE LA CAPITAL FEDERAL al doctor Santos Enrique CIFUENTES. MILEI")
    casos = [
        ("JUSTICIA Decreto 545/2026 DECTO-2026-545-APN-PTE - Nombramiento.", cuerpo_real, "ALTA", True),
        ("JUSTICIA Decreto 200/2026 - Nombramiento.",
         "Nombrase JUEZA de la CAMARA FEDERAL DE APELACIONES DE CORDOBA, en acuerdo prestado por el Senado.", "ALTA", True),
        ("MINISTERIO PUBLICO Decreto 525/2026 - Nombramiento.",
         "Nombrase DEFENSOR PUBLICO OFICIAL ante los tribunales federales de Salta.", None, True),
        ("MINISTERIO DE SALUD Resolución 699/2026", "Apruebase el listado de medicamentos.", None, False),
        ("JUSTICIA Resolución 50/2026 - Subrogancia",
         "Designase subrogante en el Juzgado Federal de Tartagal al doctor Perez.", None, False),
        ("JUSTICIA Decreto 542/2026 - Nombramientos.",
         "Nombranse JUECES de los TRIBUNALES ORALES EN LO CRIMINAL FEDERAL, con acuerdo del Senado.", "ALTA", True),
    ]
    print("=== TEST de detección (título + cuerpo) ===")
    ok = 0
    for titulo, cuerpo, esperado, esp_cand in casos:
        cand = es_candidata(normalizar(titulo))
        det = detectar(normalizar(f"{titulo} {cuerpo}"))
        got = det[0] if det else None
        bien = (got == esperado) and (cand == esp_cand)
        ok += bien
        print(f"  [{'OK' if bien else '✗'}] cand={cand!s:5} det={got!s:5} (esp {esperado!s:5}) | {titulo[:55]}")
    print(f"{ok}/{len(casos)} casos correctos.")
    return 0 if ok == len(casos) else 1


def main():
    ap = argparse.ArgumentParser(description="ITR — Radar de nombramientos judiciales (BORA)")
    ap.add_argument("--test", action="store_true", help="prueba la detección con ejemplos, sin red")
    ap.add_argument("--fecha", help="escanea una fecha puntual YYYY-MM-DD")
    ap.add_argument("--desde", help="corrida histórica: fecha inicial YYYY-MM-DD")
    ap.add_argument("--hasta", help="corrida histórica: fecha final YYYY-MM-DD (def.: hoy)")
    args = ap.parse_args()
    if args.test:
        return test()
    if args.desde:
        hasta = args.hasta or _hoy_ar().strftime("%Y-%m-%d")
        return escanear_historico(args.desde, hasta)
    return escanear(args.fecha)


if __name__ == "__main__":
    sys.exit(main())
