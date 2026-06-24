# Premortem — Radar de eventos institucionales (ITR) · junio 2026

## Contexto
- **Qué:** Radar de eventos institucionales: capa de EXPLORACIÓN (job mensual en la nube) que barre normativa (BO), FOPEA, CSJN/Consejo de la Magistratura/Senado y noticias por keywords por eje; clasifica con un LLM cada candidato contra la taxonomía de las 18 variables del ITR y produce un watchlist mensual para revisión humana (¿ya cubierto? / variable nueva con dato duro / flag manual datado). La IA y las noticias solo descubren candidatos; NO alimentan el valor publicado (determinístico, sin IA).
- **Para quién:** Departamento de Políticas Públicas de LyP y la credibilidad ante revisión periodística.
- **Éxito:** detectar eventos genuinamente no capturados, manteniendo el índice completo y creíble, sin contaminar el valor determinístico ni generar ruido o sesgo.

## Razones de fallo (premortem en bruto)
1. Contaminación del valor publicado (la capa de exploración se filtra al número).
2. Ruido > señal / fatiga de alertas.
3. Sesgo del clasificador LLM (neutralidad comprometida).
4. Dependencia frágil/sesgada de la fuente de noticias.
5. Gobernanza ausente: hallazgos que no se convierten en acción.
6. Riesgo legal/reputacional por atribución de hechos no verificados.
7. Doble conteo / incoherencia al incorporar eventos.

## Análisis profundo (7 investigadores en paralelo)
**1. Contaminación.** "Flag provisorio" mostrado junto al número → un flag movió el valor sin dato duro → el ITR oscila con el ciclo noticioso → la auditoría no cierra desde las 18 variables. Supuesto: la separación se sostiene por diseño técnico, no por disciplina de proceso. Alerta: valor publicado ≠ reconstruido; flags provisorios vivos > 0 al publicar.

**2. Ruido/fatiga.** 340→500+ candidatos/mes con duplicados; el analista lee 30 filas y archiva el resto; un cambio real en la CSJN queda en la fila 287; el anexo termina sin abrirse. Supuesto: el analista preferiría revisar todo a que el sistema filtre de más. Alerta: >50 candidatos/mes o >30% duplicados; <10-15% accionables; cae el % de anexo leído.

**3. Sesgo LLM.** Prompt en clave "abuso del oficialismo"; 40-50 candidatos con una gestión vs 15 con otra; un periodista muestra 2,3× más eventos "contra" un gobierno; "IA"+"sesgo" contaminan la marca del ITR. Supuesto: un clasificador que "solo descubre" es neutral. Alerta: ratio candidatos/medida divergente entre gestiones; test de simetría nunca corrido.

**4. Fuente frágil.** NewsAPI pasa a pago con 24h de retraso; GDELT sesgado a grandes portales; servicio bueno USD 400+/mes; RSS no determinístico; en un mes clave el eje noticias queda ciego (mismo patrón que Vigía/OpenArg). Supuesto: la API externa mantendría términos/precio/cobertura. Alerta: cae % de candidatos del eje noticias; 2 corridas mismo día difieren >10%; 429/402/403 en logs.

**5. Gobernanza.** 11 puntos ciegos detectados; backlog "para construir" se vuelve cementerio; cero variables nuevas a los 6 meses; el índice no mejora pese a "saber" qué le falta. Supuesto: lo difícil es detectar, no asignar responsable/presupuesto/plazo. Alerta: conversión de backlog = 0 al mes 2; edad del ítem más viejo crece sin egresos.

**6. Legal/reputacional.** El LLM afirma (sin "habría") que un juez "recibió pagos" desde un portal de bajo tráfico; entra a un anexo público; carta documento + "la fundación del bot que inventó la coima". Supuesto: un watchlist "interno" de IA queda interno y el carácter determinístico protege sus capas no verificadas. Alerta: <100% de entradas con fuente primaria verificada; verbos afirmativos donde la fuente decía condicional.

**7. Doble conteo.** Un mega-DNU ya contado en "DNU vs leyes" se carga además como evento; renormalización distorsiona pesos; se suman 3 variables sin recalibrar; la serie deja de ser comparable; 30% de la baja del trimestre es doble conteo. Supuesto: detectar y medir son la misma operación. Alerta: un hecho citado en variable existente y en flag el mismo mes; cambia nº de variables/eje sin acta y la serie histórica se mueve.

## Síntesis
- **Más probable:** Ruido > señal (#2).
- **Más peligroso:** Atribución no verificada — legal/reputacional (#6).
- **Supuesto oculto:** que el firewall exploración↔valor publicado es estructural (de código), cuando en realidad es una disciplina de proceso que se erosiona bajo presión de tiempo.
- **Plan revisado y checklist:** ver informe HTML.
