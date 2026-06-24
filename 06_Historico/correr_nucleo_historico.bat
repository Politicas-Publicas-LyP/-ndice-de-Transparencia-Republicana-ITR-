@echo off
REM ============================================================
REM  ITR - Nucleo Historico (2003-2026, anual)
REM  Corre las variables de serie larga con --desde 2003-01 y ensambla.
REM  Requiere IP argentina. Cada corrida tambien sirve de TEST de cobertura:
REM  si una fuente no llega a 2003 o cambio de esquema, se vera en el log.
REM  Doble click o ejecutar desde la raiz del proyecto.
REM ============================================================
cd /d "%~dp0\.."
echo ====================== EJECUTIVO ======================
echo --- DNU vs Leyes ---
py "01_Poder_Ejecutivo\scraper_01_dnu_leyes.py" --desde 2003-01 --hasta 2026-05
echo --- Discrecionalidad presupuestaria ---
py "01_Poder_Ejecutivo\scraper_04_discrecionalidad.py" --desde 2003-01 --hasta 2026-05
echo --- ATN (federalismo) ---
py "01_Poder_Ejecutivo\scraper_16_atn.py" --desde 2003-01 --hasta 2026-05

echo ====================== LEGISLATIVO ======================
echo --- Eficacia de control (art.101) ---
py "02_Poder_Legislativo\scraper_03_eficacia_control.py" --desde 2003-01 --hasta 2026-05
echo --- Calidad normativa ---
py "02_Poder_Legislativo\scraper_02_calidad_normativa.py" --desde 2003-01 --hasta 2026-05
echo --- Sesiones ---
py "02_Poder_Legislativo\scraper_14_sesiones.py" --desde 2003-01 --hasta 2026-05
echo --- Costo del Legislativo ---
py "02_Poder_Legislativo\scraper_12_costo_legislativo.py" --desde 2003-01 --hasta 2026-05

echo ====================== JUDICIAL ======================
echo --- Desempeno de la Corte (CSJN) ---
py "03_Poder_Judicial\scraper_06_resolucion_csjn.py" --desde 2003-01 --hasta 2026-05
echo --- Cobertura judicial (snapshots 2017+) ---
py "03_Poder_Judicial\scraper_05_cobertura_judicial.py" --desde 2003-01 --hasta 2026-05

echo ====================== PRENSA ======================
echo --- Pauta oficial ---
py "04_Prensa_Institucional\scraper_08_pauta.py" --desde 2003-01 --hasta 2026-05
echo --- Medios estatales ---
py "04_Prensa_Institucional\scraper_20_medios_oficiales.py" --desde 2003-01 --hasta 2026-05

echo ====================== BANCO CENTRAL ======================
echo --- Balance BCRA (financiamiento + letras) ---
py "05_Banco_Central\scraper_18_bcra_balance.py"
echo --- Respeto Carta Organica (art. 20; recaudacion via API) ---
py "05_Banco_Central\scraper_21_carta_organica.py" --desde 2003-01 --hasta 2026-05
echo --- Designacion Presidente BCRA ---
py "05_Banco_Central\scraper_17_bcra_designacion.py" --desde 2003-01 --hasta 2026-05

echo ====================== ENSAMBLAR NUCLEO ======================
py "06_Historico\itr_nucleo_historico.py" --desde 2003 --hasta 2026
echo.
echo ====== LISTO. Revisar la columna 'ejes_cubiertos' por anio. ======
pause
