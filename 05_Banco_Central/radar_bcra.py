"""
ITR — Radar de la Presidencia del BCRA (Boletín Oficial) — SOLO ALERTA
=====================================================================
Reusa la estructura del Radar de Nombramientos: escanea la Primera Sección del BORA por fecha
y AVISA cuando aparece un decreto que afecta a la PRESIDENCIA del Banco Central:
  - DESIGNACIÓN del Presidente del BCRA. La ÚNICA designación VÁLIDA es la hecha CON ACUERDO
    DEL SENADO (art. 7 Carta Orgánica, Ley 24.144; arts. 99 inc. 4 y conc. de la Constitución).
    Una designación «en comisión» (sin acuerdo del Senado) NO es el nombramiento que corresponde:
    se marca `valida_constitucional = no` y, en clave republicana, es una señal negativa.
  - RENUNCIA del Presidente del BCRA.
  - FIN DE MANDATO (cese / conclusión / vencimiento del mandato) del Presidente del BCRA.

NO toca el valor publicado: es un insumo/alerta para la variable «Designación Pdte. BCRA».
Cada evento se confirma con revisión humana (línea no-IA del ITR). El registro queda en
output/bcra_presidencia_eventos.csv (append idempotente, dedup por URL).

Trampas que evita: el boilerplate «EL PRESIDENTE DE LA NACIÓN ARGENTINA DECRETA» (que está en
TODOS los decretos) y las designaciones de Director / Vicepresidente / Vicesuperintendente del
BCRA (no son la Presidencia).

Uso:
    py radar_bcra.py                      # escanea el BORA de hoy
    py radar_bcra.py --fecha 2023-12-12   # una fecha puntual
    py radar_bcra.py --desde 2023-12-01 --hasta 2023-12-31   # rango (histórico por fecha)
    py radar_bcra.py --test               # prueba la detección (sin red)
Requisitos: pip install requests
"""
from __future__ import annotations
import argparse, csv, re, sys, time, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

URL_BORA_BASE = "https://www.boletinoficial.gob.ar"
URL_PRIMERA = f"{URL_BORA_BASE}/seccion/primera"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept-Language": "es-AR,es;q=0.9"}
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
CSV_EVENTOS = OUTPUT_DIR / "bcra_presidencia_eventos.csv"
DELAY = 1.0
DELAY_DIA = 0.4

# Rol = Presidente del BCRA, admitiendo «Presidente del Directorio del Banco Central».
# El lookbehind (?<![A-Z]) descarta VICEPRESIDENTE; exige «del Banco Central», así que el
# boilerplate «PRESIDENTE DE LA NACIÓN» no matchea.
ROL_PRESI = re.compile(r"(?<![A-Z])PRESIDENTE(?:\s+DEL\s+DIRECTORIO)?\s+DEL\s+BANCO CENTRAL")
VERBO_DESIG = re.compile(r"\b(DESIGNA|DESIGNASE|DESIGNANSE|NOMBRA|NOMBRASE|DESIGNAR)\b")
RENUNCIA = re.compile(r"\b(ACEPTASE\s+LA\s+RENUNCIA|RENUNCIA)\b")
FIN_MANDATO = re.compile(r"\b(CONCLUI\w*|FINALIZ\w*|VENCIMIENTO|CES[AEO]\w*)\b.{0,40}\bMANDATO\b"
                         r"|\bMANDATO\b.{0,40}\b(CONCLUI\w*|FINALIZ\w*|VENCIMIENTO|CES[AEO]\w*)")
EN_COMISION = re.compile(r"\bEN\s+COMISION\b")
ACUERDO_SENADO = re.compile(r"\bACUERDO\b.{0,30}\bSENADO\b|\bSENADO\b.{0,30}\bACUERDO\b")
# Candidata por título (después decide el cuerpo).
CAND_TITULO = re.compile(r"BANCO CENTRAL|\bBCRA\b")


def normaliza(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode("ascii").upper()
    return re.sub(r"\s+", " ", t).strip()


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


def _fecha_de_url(url: str):
    m = re.search(r"/(\d{8})(?:\?|$)", url)
    if m:
        s = m.group(1)
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return None


def obtener_lista_bora(fecha_compacta: str | None = None):
    url = f"{URL_PRIMERA}/{fecha_compacta}" if fecha_compacta else URL_PRIMERA
    r = get_con_reintentos(url)
    if r is None or r.status_code != 200:
        return [], False
    normas, vistas = [], set()
    for m in re.finditer(r'href="(/detalleAviso/primera/[^"]+)"[^>]*>(.*?)</a>', r.text, re.S):
        href = m.group(1).split("?")[0]
        texto = re.sub(r"<[^>]+>", " ", m.group(2))
        texto = re.sub(r"\s+", " ", texto).strip()
        full = URL_BORA_BASE + href
        if len(texto) > 8 and full not in vistas:
            vistas.add(full)
            normas.append({"titulo": texto, "url": full, "fecha": _fecha_de_url(full)})
    return normas, True


def cuerpo_norma(url: str) -> str:
    r = get_con_reintentos(url, timeout=20, intentos=2, espera=4)
    if r is None or r.status_code != 200:
        return ""
    t = re.sub(r"<[^>]+>", " ", r.text)
    t = re.sub(r"\s+", " ", t)
    ini = t.find("Ver texto del aviso")
    ini = ini + len("Ver texto del aviso") if ini != -1 else 0
    fin = t.find("Compartir por email", ini)
    if fin == -1:
        mm = re.search(r"Fecha de publicaci", t[ini:])
        fin = ini + mm.start() if mm else len(t)
    return t[ini:fin]


def _acuerdo(tn: str) -> str:
    if EN_COMISION.search(tn):
        return "en comisión (sin acuerdo del Senado)"
    if ACUERDO_SENADO.search(tn):
        return "con acuerdo del Senado"
    return "no especificado"


def _persona(tn: str):
    """Best-effort: nombre de la persona designada (no es crítico; el link tiene el texto)."""
    m = re.search(r"BANCO CENTRAL[^()]*?\b(?:A LA|AL|A)\s+(.+?)(?:\(|\bD\s?N\s?I\b|$)", tn)
    if not m:
        return ""
    s = re.sub(r"^(?:LA\s+)?(?:LICENCIAD[OA](?:\s+EN\s+\w+)?|DOCTORA?|CONTADOR[A]?|"
               r"SE[NÑ]OR[A]?|DON|DO[NÑ]A|ECONOMISTA|MAGISTER)\s+", "", m.group(1))
    return s.strip()[:80]


def detectar(texto_norm: str):
    """(evento, acuerdo, valida_constitucional, persona) si afecta a la Presidencia del BCRA.

    La ÚNICA designación válida es la hecha CON ACUERDO DEL SENADO (art. 7 Carta Orgánica,
    Ley 24.144; arts. 99 inc. 4 y concordantes de la Constitución). Una designación «en
    comisión» (sin acuerdo del Senado) NO es el nombramiento que corresponde y se marca como
    no válida (es, además, una señal negativa de calidad republicana)."""
    if not ROL_PRESI.search(texto_norm):
        return None
    persona = _persona(texto_norm)
    if VERBO_DESIG.search(texto_norm):
        if EN_COMISION.search(texto_norm):
            return "designacion_en_comision", "en comisión (sin acuerdo del Senado)", "no", persona
        if ACUERDO_SENADO.search(texto_norm):
            return "designacion_senado", "con acuerdo del Senado", "si", persona
        return "designacion_sin_especificar", "no especificado", "revisar", persona
    if RENUNCIA.search(texto_norm):
        return "renuncia", "", "", persona
    if FIN_MANDATO.search(texto_norm):
        return "fin_mandato", "", "", persona
    return None


def cargar_existentes():
    if not CSV_EVENTOS.exists():
        return set()
    with CSV_EVENTOS.open(encoding="utf-8") as f:
        return {row["url"] for row in csv.DictReader(f)}


def append_filas(filas):
    nuevo = not CSV_EVENTOS.exists()
    OUTPUT_DIR.mkdir(exist_ok=True)
    cols = ["fecha_deteccion", "fecha_publicacion", "evento", "valida_constitucional",
            "acuerdo_senado", "persona", "titulo", "url"]
    with CSV_EVENTOS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if nuevo:
            w.writeheader()
        for fila in filas:
            w.writerow(fila)


def _procesar(normas, hoy, fecha_filtrar=None):
    vistas = cargar_existentes()
    cand = [n for n in normas if CAND_TITULO.search(normaliza(n["titulo"]))]
    if fecha_filtrar:
        cand = [n for n in cand if (n.get("fecha") or fecha_filtrar) == fecha_filtrar]
    filas = []
    for n in cand:
        if n["url"] in vistas:
            continue
        tn = normaliza(f"{n['titulo']} {cuerpo_norma(n['url'])}")
        det = detectar(tn)
        if det:
            evento, acuerdo, valida, persona = det
            filas.append({"fecha_deteccion": hoy, "fecha_publicacion": n.get("fecha") or fecha_filtrar or hoy,
                          "evento": evento, "valida_constitucional": valida, "acuerdo_senado": acuerdo,
                          "persona": persona, "titulo": n["titulo"][:200], "url": n["url"]})
        time.sleep(DELAY)
    return filas


def _reportar(filas):
    if not filas:
        print("  Sin eventos de la Presidencia del BCRA."); return
    append_filas(filas)
    sello = {"si": "✅ VÁLIDA (acuerdo del Senado)", "no": "⛔ NO válida (en comisión, sin Senado)",
             "revisar": "❓ revisar acuerdo", "": ""}
    print(f"  🔔 {len(filas)} evento(s) de la Presidencia del BCRA → {CSV_EVENTOS.name}:")
    for d in filas:
        marca = sello.get(d.get("valida_constitucional", ""), "")
        print(f"     {d['fecha_publicacion']} · {d['evento'].upper()} {marca} · {d['persona']} — {d['url']}")


def _hoy_ar():
    return datetime.now(timezone.utc) - timedelta(hours=3)


def escanear(fecha=None):
    d = datetime.strptime(fecha, "%Y-%m-%d").date() if fecha else _hoy_ar().date()
    hoy = _hoy_ar().strftime("%Y-%m-%d")
    print(f"BORA Primera Sección — edición {d.isoformat()} (radar Presidencia BCRA)")
    normas, ok = obtener_lista_bora(d.strftime("%Y%m%d"))
    if not ok:
        print("FALLO: no se pudo leer el BORA (no se concluye 'sin novedades')."); return 1
    print(f"  {len(normas)} normas; {sum(1 for n in normas if CAND_TITULO.search(normaliza(n['titulo'])))} mencionan al BCRA.")
    _reportar(_procesar(normas, hoy, fecha_filtrar=d.isoformat()))
    return 0


def escanear_historico(desde, hasta):
    d0 = datetime.strptime(desde, "%Y-%m-%d").date()
    d1 = datetime.strptime(hasta, "%Y-%m-%d").date()
    hoy = _hoy_ar().strftime("%Y-%m-%d")
    print(f"HISTÓRICO BCRA — {desde} a {hasta}")
    todas, d = [], d0
    while d <= d1:
        if d.weekday() < 5:  # L-V
            normas, ok = obtener_lista_bora(d.strftime("%Y%m%d"))
            if ok:
                fs = _procesar(normas, hoy, fecha_filtrar=d.isoformat())
                if fs:
                    print(f"  {d.isoformat()}: {len(fs)} evento(s).")
                    todas.extend(fs)
            time.sleep(DELAY_DIA)
        d += timedelta(days=1)
    _reportar(todas)
    return 0


def test():
    casos = [
        ("BANCO CENTRAL", "Desígnase, en comisión, Presidente del BANCO CENTRAL DE LA REPÚBLICA ARGENTINA al Licenciado Santiago BAUSILI (D.N.I. 11.111).", ("designacion_en_comision", "no")),
        ("BANCO CENTRAL", "Desígnase Presidente del BANCO CENTRAL DE LA REPÚBLICA ARGENTINA, con acuerdo del H. SENADO DE LA NACIÓN, al doctor Juan PEREZ.", ("designacion_senado", "si")),
        ("BANCO CENTRAL", "Acéptase la renuncia presentada al cargo de Presidente del BANCO CENTRAL DE LA REPÚBLICA ARGENTINA por el licenciado X.", ("renuncia", "")),
        ("BANCO CENTRAL", "Dáse por concluido el mandato del Presidente del BANCO CENTRAL DE LA REPÚBLICA ARGENTINA.", ("fin_mandato", "")),
        ("BANCO CENTRAL", "Desígnase en comisión Director del BANCO CENTRAL DE LA REPÚBLICA ARGENTINA al licenciado Z.", None),
        ("BANCO CENTRAL", "Desígnase Vicepresidente del BANCO CENTRAL DE LA REPÚBLICA ARGENTINA al licenciado W.", None),
        ("JUSTICIA", "EL PRESIDENTE DE LA NACIÓN ARGENTINA DECRETA: Desígnase Juez del Juzgado Federal N° 2.", None),
    ]
    print("=== TEST radar Presidencia BCRA ===")
    ok = 0
    for titulo, cuerpo, esp in casos:
        det = detectar(normaliza(f"{titulo} {cuerpo}"))
        got = (det[0], det[2]) if det else None
        bien = got == esp
        ok += bien
        print(f"  [{'OK' if bien else '✗'}] {str(got):42} | {cuerpo[:52]}")
    print(f"{ok}/{len(casos)} correctos.")
    return 0 if ok == len(casos) else 1


def main():
    ap = argparse.ArgumentParser(description="ITR — Radar de la Presidencia del BCRA (BORA)")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--fecha", help="fecha puntual YYYY-MM-DD")
    ap.add_argument("--desde", help="histórico: fecha inicial YYYY-MM-DD")
    ap.add_argument("--hasta", help="histórico: fecha final YYYY-MM-DD (def.: hoy)")
    args = ap.parse_args()
    if args.test:
        return test()
    if args.desde:
        return escanear_historico(args.desde, args.hasta or _hoy_ar().strftime("%Y-%m-%d"))
    return escanear(args.fecha)


if __name__ == "__main__":
    sys.exit(main())
