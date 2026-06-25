# Índice de Transparencia Republicana (ITR)

Fundación Libertad y Progreso — Departamento de Políticas Públicas.

El ITR es un índice mensual de calidad republicana (escala 0–100) construido con **dato duro,
determinístico y auditable**: cada valor publicado sale de conteos, SQL o campos estructurados
reproducibles, **nunca de juicios de una IA**. La IA y las noticias se usan solo para explorar y
alertar, no para fijar el valor. La normalización es por **anclaje a un ideal absoluto** (por
variable: el mejor valor posible → 100, el peor → 0).

## Repositorio y régimen de trabajo

- **Fuente única de verdad:** este repositorio en GitHub —
  https://github.com/Politicas-Publicas-LyP/-ndice-de-Transparencia-Republicana-ITR-
- El índice se trabaja **en paralelo con varias cuentas/máquinas**. La sincronización es por
  **GitHub Desktop**:
  1. **Pull** antes de empezar (traer lo último).
  2. Trabajar y registrar los cambios en la `BITACORA.md` del eje correspondiente.
  3. **Commit + push** al terminar, para que el repo quede siempre actualizado.
- Ante la duda, **pull primero** para no pisar trabajo de otra cuenta.

## Estructura

| Carpeta | Contenido |
|---|---|
| `00_Comun/` | Ensamblador (`icia_ensamblado.py`), `variables.yaml` (fuente única de variables/pesos), `contracts.yaml` + `validar.py` (QA y frescura), gráficos. |
| `01_Poder_Ejecutivo/` | DNU vs Leyes, Discrecionalidad presupuestaria, Transparencia (AIP), ATN. |
| `02_Poder_Legislativo/` | Calidad normativa, Eficacia de control, Costo del Legislativo, Sesiones. |
| `03_Poder_Judicial/` | Cobertura e independencia judicial, **padrón judicial vivo**, Desempeño de la Corte. |
| `04_Prensa_Institucional/` | Escrutinio abierto, Pauta, Causas contra periodistas, Medios estatales, Acceso de la prensa. |
| `05_Banco_Central/` | Financiamiento al Tesoro, Letras intransferibles, Designación del Presidente, Carta Orgánica. |
| `06_Historico/` | Núcleo histórico anual (2003+) y mensual (2020+). |
| `07_Radar_Nombramientos/` | Radar del BORA que detecta designaciones de jueces (corre en GitHub Actions). |
| `Documentos/`, `Modelos y Administración/` | Reportes, nota metodológica, modelo LyP, mejoras. |
| `output/` | Series calculadas (`*_mensual.csv`), índice (`itr_*.csv`), puente del radar y padrón. |

## Bitácoras

Cada carpeta de eje tiene una `BITACORA.md` con el **estado, la fuente, la última actualización y
los pendientes de cada variable**. Es el lugar para leer y registrar novedades sin abrir el código.
Mantenerla al día es parte del trabajo en cada cambio.

## Cómo correr

Requisitos: `pip install -r 00_Comun/requirements.txt` (pandas, requests, matplotlib, python-docx,
pyyaml, beautifulsoup4). Varias fuentes oficiales (datos.jus, DGSIAF, BCRA) exigen **IP argentina**;
el BORA es accesible también desde el exterior (por eso el radar corre en GitHub Actions).

```
# 1) Correr los scrapers del mes (ejemplo, cobertura judicial)
py "03_Poder_Judicial/scraper_05_cobertura_judicial.py" --desde 2023-01 --hasta 2026-06
# 2) Ensamblar el índice
py "00_Comun/icia_ensamblado.py" --desde 2023-01 --hasta 2026-05
# 3) (Opcional) Validar frescura y contratos
py "00_Comun/validar.py"
```

## Gobernanza del dato

- **Sin IA en el valor publicado.** El radar y el padrón vivo son insumos/alertas; lo que entra al
  índice se confirma con reglas determinísticas o revisión humana.
- **Estimado vs oficial.** Cuando una fuente se actualiza lento (p. ej. el dataset de magistrados,
  ~cada 2 años), el padrón vivo recalcula la cobertura como **«estimado»** y se reconcilia con el
  próximo dato oficial.
- Detalle de arquitectura y mañas de las fuentes: ver `AGENTS.md`.
