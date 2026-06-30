@echo off
REM ============================================================================
REM  ITR - PIPELINE MENSUAL COMPLETO  (todas las variables -> indice)
REM ----------------------------------------------------------------------------
REM  Corre en una maquina con IP ARGENTINA: datos.jus, DGSIAF y BCRA bloquean
REM  IPs del exterior/datacenter. (apis.datos.gob.ar si responde afuera.)
REM
REM  Los RADARES del BORA (jueces altas/bajas + Presidencia BCRA) NO van aca:
REM  corren solos en GitHub Actions y dejan sus CSV puente en el repo. Este
REM  pipeline los lee del repo (variable ITR_RADAR_CSV_URL ya configurada).
REM
REM  Equivalente Linux para el futuro servidor en la nube: correr_mensual.sh
REM  Orden: scrapers -> padron judicial -> cobertura -> ensamblar -> QA -> graficos.
REM ============================================================================
setlocal
cd /d "%~dp0"

REM --- Rango ---
REM  DESDE    = colchon: arranca 1 anio antes para que el suavizado de 12m este
REM             COMPLETO al inicio publicado (ene-2024).  No se publica el tramo 2023.
REM  PUBLICAR = inicio publicado = gestion Milei (enero 2024), ya suavizado.
REM  HASTA    = mes en curso.
set "DESDE=2023-01"
set "PUBLICAR=2024-01"
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM')"') do set "HASTA=%%i"
echo ============================================================
echo  ITR - corrida mensual   rango: %DESDE%  ..  %HASTA%
echo ============================================================

REM (Recomendado) traer codigo y CSV puente al dia antes de correr:
REM   git pull

echo.
echo ====================== EJECUTIVO ======================
py "01_Poder_Ejecutivo\scraper_01_dnu_leyes.py"        --desde %DESDE% --hasta %HASTA%
py "01_Poder_Ejecutivo\scraper_04_discrecionalidad.py" --desde %DESDE% --hasta %HASTA%
py "01_Poder_Ejecutivo\scraper_11_transparencia_v2.py" --desde %DESDE% --hasta %HASTA%
py "01_Poder_Ejecutivo\scraper_16_atn.py"              --desde %DESDE% --hasta %HASTA%

echo.
echo ====================== LEGISLATIVO ======================
py "02_Poder_Legislativo\scraper_02_calidad_normativa.py" --desde %DESDE% --hasta %HASTA%
py "02_Poder_Legislativo\scraper_03_eficacia_control.py"  --desde %DESDE% --hasta %HASTA%
py "02_Poder_Legislativo\scraper_12_costo_legislativo.py" --desde %DESDE% --hasta %HASTA%
py "02_Poder_Legislativo\scraper_14_sesiones.py"          --desde %DESDE% --hasta %HASTA%

echo.
echo ====================== JUDICIAL ======================
py "03_Poder_Judicial\scraper_06_resolucion_csjn.py" --desde %DESDE% --hasta %HASTA%
REM Padron vivo: base oficial -> aplica altas/bajas del BORA (estimado). Va ANTES de cobertura.
py "03_Poder_Judicial\padron_judicial.py" --construir
py "03_Poder_Judicial\padron_judicial.py" --actualizar
REM Cobertura: usa el padron estimado (stock del mes) + flujo del radar.
py "03_Poder_Judicial\scraper_05_cobertura_judicial.py" --desde %DESDE% --hasta %HASTA%

echo.
echo ====================== PRENSA ======================
py "04_Prensa_Institucional\scraper_07_escrutinio.py"       --desde %DESDE% --hasta %HASTA%
py "04_Prensa_Institucional\scraper_08_pauta.py"            --desde %DESDE% --hasta %HASTA%
py "04_Prensa_Institucional\scraper_13_prensa_causas.py"    --desde %DESDE% --hasta %HASTA%
py "04_Prensa_Institucional\scraper_20_medios_oficiales.py" --desde %DESDE% --hasta %HASTA%
py "04_Prensa_Institucional\scraper_22_acceso_prensa.py"    --desde %DESDE% --hasta %HASTA%

echo.
echo ====================== BANCO CENTRAL ======================
py "05_Banco_Central\scraper_18_bcra_financiamiento.py" --desde %DESDE% --hasta %HASTA%
py "05_Banco_Central\scraper_18_bcra_balance.py"
py "05_Banco_Central\scraper_21_carta_organica.py"      --desde %DESDE% --hasta %HASTA%
py "05_Banco_Central\scraper_17_bcra_designacion.py"    --desde %DESDE% --hasta %HASTA%

echo.
echo ====================== ENSAMBLAR + QA + GRAFICOS ======================
py "00_Comun\icia_ensamblado.py" --desde %DESDE% --hasta %HASTA% --publicar-desde %PUBLICAR%
py "00_Comun\validar.py"
py "00_Comun\graficar_itr.py"

echo.
echo ============================================================
echo  LISTO.  Indice: output\itr_mensual.csv
echo          Alertas QA: output\_alertas_validacion.md
echo  Nota: el mes en curso sale PROVISIONAL. Para el titular cerrado,
echo        reensambla con  --hasta  del mes anterior.
echo ============================================================
pause
endlocal
