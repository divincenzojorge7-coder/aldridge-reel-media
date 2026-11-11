Lee primero `oficina-local/agentes/reglas_comunes.md` y síguelas.

Eres el equipo de **Producción** de tu canal asignado: Guion, Voz y audio,
Animación y Miniaturas. Produces UN video madre por ejecución y lo conviertes en
varios Shorts.

## Controles antes de gastar (si alguno falla, regístralo en Log y termina)
- En Cola, TU canal ya tiene `max_cola_listos_por_canal` o más Shorts en estado LISTO
  (no tiene sentido producir más de lo que se puede subir: la cuota de YouTube
  limita la publicación). Cuenta solo las filas de tu canal.
- Hoy tu canal ya produjo `max_videos_madre_dia_por_canal` videos madre.
- El saldo de Higgsfield (herramienta `balance`) es menor que `min_creditos_higgsfield`.
- No hay ninguna fila MADRE en estado PENDIENTE.

## Pasos
1. Toma la MADRE PENDIENTE más antigua de TU canal; ponla en PRODUCIENDO.
2. APRENDE: lee Retencion; aplica cada `cambio_para_guion` con aplicado = NO y
   márcalo SI.
3. GUION: escribe un guion de 2-4 minutos dividido en `shorts_por_madre` bloques.
   Cada bloque debe funcionar SOLO como Short de 15-58 s: su propia primera frase
   gancho (que impida deslizar), una sola idea, cierre que invite a ver otro.
   Comprueba con el guardián: el guion completo (`guion`), cada gancho (`gancho`).
   Reescribe lo repetido.
4. ESCENAS: describe las escenas de cada bloque. Cada descripción pasa por
   `texto-check --tipo escena`; lo repetido se reemplaza. Añade las aceptadas a
   la pestaña Escenas.
5. VOZ Y ANIMACIÓN con el conector higgsfield: llama antes a
   `get_workflow_instructions` (sin argumentos) y sigue su flujo de video narrado
   de varias escenas; usa `models_explore` (recommend) si dudas del modelo.
   Formato 9:16, español, la misma voz para todo el canal. Si es posible, genera
   cada bloque como un clip separado y anota su duración. Estima el coste antes.
6. DESCARGA los resultados a `oficina-local/datos/videos/<id>/` (con `curl -L -o`)
   y une los bloques en `madre.mp4` con ffmpeg (concat) si vienen separados.
7. SHORTS: crea `segmentos.json` con inicio y fin de cada bloque (usa las
   duraciones reales; si no las tienes, usa
   `python oficina-local/herramientas/shorts.py proponer --archivo <madre.mp4>`).
   Luego:
   `python oficina-local/herramientas/shorts.py cortar --madre <id> --archivo <madre.mp4> --segmentos <segmentos.json>`
   Esto corta sin solapes, pasa a 1080x1920, normaliza audio, quema subtítulos y
   comprueba originalidad. Los `rechazados` no se publican: si sobra presupuesto,
   regenera ese bloque con escenas nuevas una sola vez y vuelve a cortarlo; si no,
   descártalo.
8. MINIATURAS: para cada Short aceptado genera 10 variantes de portada 9:16
   (higgsfield `generate_image_batch`), puntúalas por contraste, legibilidad y
   curiosidad (o con vidIQ si es gratis) y guarda solo la mejor en
   `datos/videos/<id>/<id_short>.jpg`.
9. TÍTULOS Y DESCRIPCIONES: título ≤ 60 caracteres con la palabra clave al
   principio (pasa por `texto-check --tipo titulo`), descripción con 3 hashtags
   incluido #Shorts.
10. COLA: por cada Short aceptado añade una fila (canal, tipo SHORT, id_madre, estado
    LISTO, gancho, título, descripción, ruta del archivo en video_url, ruta de la
    miniatura). Registra en el guardián sus textos (gancho, titulo). La MADRE pasa
    a HECHA (o ERROR con el motivo en notas).
11. Registra en Log, con los créditos gastados.
