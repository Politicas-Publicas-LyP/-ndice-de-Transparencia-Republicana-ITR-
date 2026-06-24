"""
ITR — Radar de Nombramientos Judiciales (Boletín Oficial)
=========================================================
Radar INDEPENDIENTE (no pisa el Radar de Desregulación). Cada día hábil escanea la
Primera Sección del Boletín Oficial y detecta los DECRETOS DE DESIGNACIÓN DE JUECES
TITULARES (designación del Poder Ejecutivo con acuerdo del Senado). Su objetivo es darle
CADENCIA al flujo de nombramientos del eje Judicial del ITR, que de otro modo depende del
dataset de magistrados (que se actualiza ~cada 2 años).

Reutiliza la lectura del BORA del Radar de Desregulación (lista de la Primera Sección +
texto completo de cada norma), pero con detección POSITIVA de designaciones judiciales
(lo que aquel radar justamente descarta como "norma de personal").

SALIDA — puente con el índice: append idempotente a  output/nombramientos_jueces.csv
(columnas: fecha_deteccion, fecha_publicacion, tipo, organo, confianza, motivo, titulo, url).
El scraper de Cobertura Judicial lee ese CSV y toma max(fecha dataset, fecha radar) para
el flujo, manteniéndolo fresco entre snapshots.

GOBERNANZA (línea no-IA del ITR): el radar es ALERTA/insumo. Las filas de confianza ALTA
son candidatas firmes; MEDIA/BAJA quedan para revisión humana. El valor publicado del
flujo se actualiza con confirmación humana (campo 'confianza' / revisión).

Uso:
    py radar_nombramientos.py            # escanea el BORA de hoy y actualiza el CSV
    py radar_nombramientos.py --test     # prueba la detección con títulos de ejemplo (sin red)
Requisitos: pip install requests beautifulsoup4
"""
from __future__ import annotations
import argparse, csv, os, re, sys, time, unicodedata
from datetime import datetime, timedelta
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
DELAY = 1.2
MIN_CUERPO = 200

# Vigía (openarg) — para LISTAR normas de días pasados (el índice del BORA solo muestra hoy).
# Solo se usa en el modo histórico; el texto de cada norma se sigue leyendo del BORA.
VIGIA_API_BASE = (os.environ.get("VIGIA_API_BASE") or "https://vigia-api.openarg.org").rstrip("/")
VIGIA_API_TOKEN = os.environ.get("VIGIA_API_TOKEN", "")
VIGIA_TIMEOUT = 25
VIGIA_MAX_PAGINAS = 60  # 60 x 100 = 6000 normas; sobra para varias semanas

# --- Detección de designaciones de JUECES TITULARES ---
VERBO  = re.compile(r"\b(DESIGNA|DESIGNASE|DESIGNANSE|NOMBRA|NOMBRASE|DESIGNAR|DESIGNACION)\b")
JUEZ   = re.compile(r"\b(JUEZ|JUEZA|JUECES|MAGISTRAD\w*|CAMARISTA)\b")
ORGANO = re.compile(r"(JUZGADO[^,.;]{0,80}|CAMARA (?:FEDERAL|NACIONAL)[^,.;]{0,80}|TRIBUNAL ORAL[^,.;]{0,80})")
SENADO = re.compile(r"\b(SENADO|ACUERDO DEL? (?:HONORABLE )?SENADO|ACUERDO PRESTADO)\b")
SUBROGA = re.compile(r"\bSUBROGA\w*")


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", t).upper().strip()


def get_con_reintentos(url, timeout=20, intentos=3, espera=6):
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


def obtener_lista_bora():
    r = get_con_reintentos(URL_PRIMERA_SECCION, timeout=30, intentos=4, espera=8)
    if r is None or r.status_code != 200:
        print("  no se pudo acceder a la Primera Sección del BORA."); return [], False
    soup = BeautifulSoup(r.text, "html.parser")
    normas, vistas = [], set()
    for link in soup.find_all("a", href=True):
        href = link["href"]; texto = link.get_text(" ", strip=True)
        if "detalleAviso" in href and len(texto) > 10:
            full = URL_BORA_BASE + href if href.startswith("/") else href
            if full in vistas:
                continue
            vistas.add(full)
            normas.append({"titulo": texto, "url": full})
    return normas, True


def obtener_texto_norma(url):
    r = get_con_reintentos(url, timeout=20, intentos=2, espera=4)
    if r is None or r.status_code != 200:
        return "", ""
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        resumen = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            resumen = meta["content"]
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        tp = soup.get_text(" ", strip=True)
        ini = tp.find("Ver texto del aviso"); ini = ini + 19 if ini != -1 else 0
        fin = tp.find("Compartir por email", ini)
        if fin == -1:
            m = re.search(r"Fecha de publicaci", tp[ini:]); fin = ini + m.start() if m else len(tp)
        return resumen, tp[ini:fin].strip()
    except Exception as e:  # noqa: BLE001
        print(f"  parseo {url}: {e}"); return "", ""


def detectar(texto_norm: str):
    """Devuelve (confianza, organo, motivo) si parece designación de juez titular; si no, None."""
    tiene_juez = bool(JUEZ.search(texto_norm))
    tiene_verbo = bool(VERBO.search(texto_norm))
    tiene_senado = bool(SENADO.search(texto_norm))
    es_decreto = "DECRETO" in texto_norm
    es_subroga = bool(SUBROGA.search(texto_norm))
    if not (tiene_juez and (tiene_verbo or tiene_senado)):
        return None
    # Subrogancia SIN acuerdo del Senado = reemplazo removible, no nombramiento titular → fuera.
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
        return {row["url"] for row in csv.DictReader(f)}


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


def _vigia_get_json(path, params=None):
    h = {"Accept": "application/json", "User-Agent": HEADERS["User-Agent"]}
    if VIGIA_API_TOKEN:
        h["Authorization"] = f"Bearer {VIGIA_API_TOKEN}"
    r = requests.get(f"{VIGIA_API_BASE}{path}", headers=h, params=params, timeout=VIGIA_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    return r.json()


def listar_vigia_rango(desde: str, hasta: str):
    """Normas de la Primera Sección publicadas entre desde y hasta (YYYY-MM-DD), vía Vigía.
    Devuelve lista de {titulo, url, fecha, resumen}. Vigía ordena de más nuevo a más viejo:
    paginamos hasta cruzar 'desde'. Requiere acceso a vigia-api (IP del exterior/Actions)."""
    normas, vistas = [], set()
    for pagina in range(VIGIA_MAX_PAGINAS):
        data = _vigia_get_json("/normas", params={"limit": 100, "offset": pagina * 100})
        page = data.get("items", [])
        if not page:
            break
        seguir = True
        for it in page:
            f = it.get("fecha_publicacion") or ""
            if f and f < desde:
                seguir = False  # ya pasamos el rango (orden descendente)
                continue
            if desde <= f <= hasta and it.get("bora_seccion") == "Primera Sección" \
                    and it.get("url") and it["url"] not in vistas:
                vistas.add(it["url"])
                titulo = f"{it.get('organismo','')} {it.get('numero','')} {it.get('titulo','')}".strip()
                normas.append({"titulo": titulo, "url": it["url"], "fecha": f,
                               "resumen": it.get("resumen") or ""})
        if not seguir:
            break
    return normas


def _detectar_en(normas, fecha_por_norma=True):
    """Lee el texto de las candidatas (por título/resumen), corre la detección y devuelve filas."""
    hoy = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")
    vistas = cargar_existentes()
    cand = [n for n in normas if JUEZ.search(normalizar(f"{n['titulo']} {n.get('resumen','')}"))]
    print(f"  {len(cand)} candidatas (mencionan juez/magistrado en título/resumen). Leyendo texto...")
    filas = []
    for n in cand:
        if n["url"] in vistas:
            continue
        resumen, cuerpo = obtener_texto_norma(n["url"])
        tn = normalizar(f"{n['titulo']} {n.get('resumen','')} {resumen} {cuerpo}")
        det = detectar(tn)
        if det:
            conf, organo, motivo = det
            tipo = "Decreto" if "DECRETO" in normalizar(n["titulo"]) else "Otro"
            fpub = n.get("fecha") if fecha_por_norma and n.get("fecha") else hoy
            filas.append({"fecha_deteccion": hoy, "fecha_publicacion": fpub, "tipo": tipo,
                          "organo": organo, "confianza": conf, "motivo": motivo,
                          "titulo": n["titulo"][:300], "url": n["url"]})
        time.sleep(DELAY)
    return filas


def escanear_historico(desde: str, hasta: str):
    """Corrida ÚNICA de recuperación: capta designaciones publicadas en [desde, hasta]."""
    print(f"HISTÓRICO — BORA Primera Sección de {desde} a {hasta} (listado vía Vigía)")
    try:
        normas = listar_vigia_rango(desde, hasta)
    except Exception as e:  # noqa: BLE001
        print(f"FALLO: no se pudo listar el rango vía Vigía: {e}")
        print("  (El listado por fecha exige Vigía; el índice del BORA solo muestra el día de hoy.)")
        return 1
    print(f"  {len(normas)} normas de la Primera Sección en el rango.")
    filas = _detectar_en(normas, fecha_por_norma=True)
    if filas:
        append_filas(filas)
        print(f"  ✅ {len(filas)} designación(es) de juez detectadas y agregadas a {CSV_PUENTE.name}:")
        for d in sorted(filas, key=lambda x: x["fecha_publicacion"]):
            print(f"     {d['fecha_publicacion']} [{d['confianza']}] {d['organo'] or d['titulo'][:60]}")
    else:
        print("  Sin designaciones judiciales en el rango.")
    return 0


def escanear():
    hoy = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")  # fecha AR
    print(f"BORA Primera Sección — {hoy}")
    normas, ok = obtener_lista_bora()
    if not ok:
        print("FALLO: no se pudo leer el BORA (no se concluye 'sin novedades')."); return 1
    print(f"  {len(normas)} normas en la lista.")
    vistas = cargar_existentes()
    detectadas = []
    # pre-filtro por título; solo leemos el texto completo de las candidatas
    cand = [n for n in normas if JUEZ.search(normalizar(n["titulo"]))]
    print(f"  {len(cand)} candidatas por título (mencionan juez/magistrado). Leyendo texto...")
    for n in cand:
        if n["url"] in vistas:
            continue
        resumen, cuerpo = obtener_texto_norma(n["url"])
        tn = normalizar(f"{n['titulo']} {resumen} {cuerpo}")
        det = detectar(tn)
        if det:
            conf, organo, motivo = det
            tipo = "Decreto" if "DECRETO" in normalizar(n["titulo"]) else "Otro"
            detectadas.append({"fecha_deteccion": hoy, "fecha_publicacion": hoy, "tipo": tipo,
                               "organo": organo, "confianza": conf, "motivo": motivo,
                               "titulo": n["titulo"][:300], "url": n["url"]})
        time.sleep(DELAY)
    if detectadas:
        append_filas(detectadas)
        print(f"  ✅ {len(detectadas)} designación(es) de juez detectadas y agregadas a {CSV_PUENTE.name}:")
        for d in detectadas:
            print(f"     [{d['confianza']}] {d['organo'] or d['titulo'][:60]} — {d['url']}")
    else:
        print("  Sin designaciones judiciales nuevas hoy.")
    return 0


def test():
    casos = [
        ("JUSTICIA - Decreto 123/2026 - Desígnase Juez del Juzgado Federal de Primera Instancia N° 2 de Salta, con acuerdo del Honorable Senado.", "ALTA"),
        ("PODER JUDICIAL - Decreto 200/2026 - Nómbrase Jueza de la Cámara Federal de Apelaciones de Córdoba en acuerdo con el Senado.", "ALTA"),
        ("MINISTERIO DE JUSTICIA - Resolución 50/2026 - Desígnase subrogante en el Juzgado Federal de Tartagal.", None),
        ("BANCO CENTRAL - Comunicación A 8000 - Encajes.", None),
        ("EDUCACION - Decreto 70/2026 - Desígnase Director Nacional de Gestión.", None),
        ("JUSTICIA - Decreto - Desígnase Juez del Tribunal Oral en lo Criminal Federal de Mendoza.", "MEDIA"),
    ]
    print("=== TEST de detección ===")
    ok = 0
    for titulo, esperado in casos:
        det = detectar(normalizar(titulo))
        got = det[0] if det else None
        estado = "OK" if got == esperado else "✗"
        if got == esperado: ok += 1
        print(f"  [{estado}] esperado={esperado!s:5} obtenido={got!s:5} | {titulo[:70]}")
    print(f"{ok}/{len(casos)} casos correctos.")
    return 0 if ok == len(casos) else 1


def main():
    ap = argparse.ArgumentParser(description="ITR — Radar de nombramientos judiciales (BORA)")
    ap.add_argument("--test", action="store_true", help="prueba la detección con ejemplos, sin red")
    ap.add_argument("--desde", help="corrida histórica: fecha inicial YYYY-MM-DD (lista vía Vigía)")
    ap.add_argument("--hasta", help="corrida histórica: fecha final YYYY-MM-DD (def.: hoy)")
    args = ap.parse_args()
    if args.test:
        return test()
    if args.desde:
        hasta = args.hasta or (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d")
        return escanear_historico(args.desde, hasta)
    return escanear()


if __name__ == "__main__":
    sys.exit(main())
