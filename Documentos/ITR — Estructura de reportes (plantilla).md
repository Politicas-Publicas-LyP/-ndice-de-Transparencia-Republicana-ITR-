# ITR — Estructura de reportes (plantilla institucional)

Tipografía y formato de TODOS los reportes: base en **"Modelos y Administración/Modelo documento LyP.docx"**.
- Fuente: **Open Sans**. Título 20 pt **bold rojo (FF0000)**. Cuerpo 10 pt gris (404040).
- Encabezado: "INFORME DE POLÍTICAS PÚBLICAS" + fecha a la derecha. Pie: número de página a la derecha.
- Logo de LyP arriba a la izquierda. Subtítulo: "Departamento de Políticas Públicas — Fundación Libertad y Progreso · <edición>".
- Voz institucional: usar la habilidad **lyp-pp** (primera persona del plural, asertiva, pedagógica, marco liberal).

## 1) Reporte MENSUAL (gestión / período)
1. **Gráfico de línea consolidado**: el ITR (consolidado de las 18 variables), mensual.
2. **Gráfico de línea desagregado**: los 5 sub-índices (macrocategorías), mensual.
3. **Lectura mes a mes**: tabla (ITR + 5 sub-índices por mes) + explicación de **la variación de cada mes, qué variables desagregadas se movieron y a qué se debe**.
4. **Lectura de LyP**: cierre en voz institucional.
Scripts: `00_Comun/graficar_itr.py` (5 ejes, soporta --desde/--hasta) + gráfico consolidado.

## 2) Reporte HISTÓRICO (NÚCLEO MENSUAL)
1. **Un solo gráfico de línea**: desagregado de las 5 macrocategorías, **mensual** (2020 → último mes), con **división de fondo por gestión**: Alberto Fernández = **celeste**, Milei = **violeta claro**, y la línea del ITR núcleo.
2. **Explicación en voz institucional (lyp-pp)** de las variaciones: **avances y retrocesos**, eje por eje.
Fuente: ITR Núcleo MENSUAL (`output/itr_nucleo_mensual.csv`, ensamblador `06_Historico/itr_nucleo_mensual.py`), serie comparable de fondo del índice (subconjunto de variables de serie larga, distinta del ITR mensual pleno de 18 variables).

## PENDIENTE (futuro cercano) — Reporte mensual TOTALIZADO (núcleo)
Construir un reporte mensual totalizado que vaya desde **enero 2020 al último mes disponible** (serie mensual larga del núcleo, no anual). Será **nuestro núcleo a actualizar mes a mes**, en paralelo al reporte del mes en particular. Requiere extender el ensamblador del núcleo a frecuencia mensual (hoy es anual) usando las variables de serie larga.
