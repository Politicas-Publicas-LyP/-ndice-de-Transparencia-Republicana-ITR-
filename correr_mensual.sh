#!/usr/bin/env bash
# ============================================================================
#  ITR - PIPELINE MENSUAL COMPLETO  (Linux / futuro servidor en la nube)
# ----------------------------------------------------------------------------
#  Equivalente de correr_mensual.bat. Requiere EGRESS con IP ARGENTINA:
#  datos.jus, DGSIAF y BCRA bloquean IPs del exterior/datacenter. (Esa es la
#  incognita abierta del deploy cloud; ver AGENTS.md y Documento de Mejoras.)
#
#  Los RADARES del BORA (jueces altas/bajas + Presidencia BCRA) corren en
#  GitHub Actions y dejan sus CSV puente en el repo; este pipeline los lee de
#  ahi (variable de entorno ITR_RADAR_CSV_URL).
#
#  Pensado para cron/CI: DESDE, HASTA y PY se pueden pasar por entorno.
#  Uso:   ./correr_mensual.sh        (HASTA = mes en curso)
#         HASTA=2026-05 ./correr_mensual.sh
# ============================================================================
set -uo pipefail
cd "$(dirname "$0")"

DESDE="${DESDE:-2023-01}"        # colchon: 1 anio antes para suavizado 12m completo (no se publica)
PUBLICAR="${PUBLICAR:-2024-01}"  # inicio publicado = gestion Milei, ya suavizado
HASTA="${HASTA:-$(date +%Y-%m)}"
PY="${PY:-python3}"
mkdir -p output
LOG="output/_corrida_mensual_$(date +%Y%m%d_%H%M%S).log"
echo "ITR - corrida mensual | rango: $DESDE .. $HASTA | log: $LOG" | tee "$LOG"

run() { echo -e "\n### $*" | tee -a "$LOG"; "$@" >>"$LOG" 2>&1 || echo "  (FALLO: $* — sigue)" | tee -a "$LOG"; }

echo "== EJECUTIVO ==" | tee -a "$LOG"
run "$PY" 01_Poder_Ejecutivo/scraper_01_dnu_leyes.py        --desde "$DESDE" --hasta "$HASTA"
run "$PY" 01_Poder_Ejecutivo/scraper_04_discrecionalidad.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 01_Poder_Ejecutivo/scraper_11_transparencia_v2.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 01_Poder_Ejecutivo/scraper_16_atn.py              --desde "$DESDE" --hasta "$HASTA"

echo "== LEGISLATIVO ==" | tee -a "$LOG"
run "$PY" 02_Poder_Legislativo/scraper_02_calidad_normativa.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 02_Poder_Legislativo/scraper_03_eficacia_control.py  --desde "$DESDE" --hasta "$HASTA"
run "$PY" 02_Poder_Legislativo/scraper_12_costo_legislativo.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 02_Poder_Legislativo/scraper_14_sesiones.py          --desde "$DESDE" --hasta "$HASTA"

echo "== JUDICIAL ==" | tee -a "$LOG"
run "$PY" 03_Poder_Judicial/scraper_06_resolucion_csjn.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 03_Poder_Judicial/padron_judicial.py --construir     # base oficial de jueces
run "$PY" 03_Poder_Judicial/padron_judicial.py --actualizar    # altas/bajas del BORA (estimado)
run "$PY" 03_Poder_Judicial/scraper_05_cobertura_judicial.py --desde "$DESDE" --hasta "$HASTA"

echo "== PRENSA ==" | tee -a "$LOG"
run "$PY" 04_Prensa_Institucional/scraper_07_escrutinio.py       --desde "$DESDE" --hasta "$HASTA"
run "$PY" 04_Prensa_Institucional/scraper_08_pauta.py            --desde "$DESDE" --hasta "$HASTA"
run "$PY" 04_Prensa_Institucional/scraper_13_prensa_causas.py    --desde "$DESDE" --hasta "$HASTA"
run "$PY" 04_Prensa_Institucional/scraper_20_medios_oficiales.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 04_Prensa_Institucional/scraper_22_acceso_prensa.py    --desde "$DESDE" --hasta "$HASTA"

echo "== BANCO CENTRAL ==" | tee -a "$LOG"
run "$PY" 05_Banco_Central/scraper_18_bcra_financiamiento.py --desde "$DESDE" --hasta "$HASTA"
run "$PY" 05_Banco_Central/scraper_18_bcra_balance.py
run "$PY" 05_Banco_Central/scraper_21_carta_organica.py      --desde "$DESDE" --hasta "$HASTA"
run "$PY" 05_Banco_Central/scraper_17_bcra_designacion.py    --desde "$DESDE" --hasta "$HASTA"

echo "== ENSAMBLAR + QA + GRAFICOS ==" | tee -a "$LOG"
run "$PY" 00_Comun/icia_ensamblado.py --desde "$DESDE" --hasta "$HASTA" --publicar-desde "$PUBLICAR"
run "$PY" 00_Comun/validar.py
run "$PY" 00_Comun/graficar_itr.py

echo "LISTO. Indice: output/itr_mensual.csv | Alertas QA: output/_alertas_validacion.md" | tee -a "$LOG"
echo "(El mes en curso sale PROVISIONAL; para el titular cerrado, reensamblar con HASTA del mes anterior.)" | tee -a "$LOG"
