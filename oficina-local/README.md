# Oficina YouTube local (Windows 24/7)

Equipo de agentes que produce y publica YouTube Shorts sin intervención, en una
computadora Windows siempre encendida. La computadora hace el trabajo pesado
(cortar, subtitular, comprobar originalidad, subir) y la hoja de Google
**Oficina YouTube - Centro de control** sigue siendo el panel para ver y pausar
todo desde el móvil.

## Cómo se publica (sin solicitar nada a Google)

Los videos subidos con la API de YouTube desde un proyecto sin auditar quedan
**bloqueados en privado**. Para no tener que pedir la auditoría, Studio publica
por **Metricool**, que ya tiene la aprobación de YouTube (`publicacion.metodo:
"metricool"` en `config.json`). Pasos, una sola vez:

1. En Metricool, una **marca por canal** de YouTube, con el canal conectado.
   Apunta el `blogId` de cada marca en la pestaña Canales de la hoja
   (`metricool_blog_id`) y pon `youtube_en_metricool` = SI. Comprueba en tu plan de
   Metricool cuántas marcas y publicaciones al mes admite.
2. Instala **Google Drive para escritorio** en la computadora y vincula tu Google
   Drive en Metricool (Ajustes → cuenta). Apunta la carpeta sincronizada en
   `config.json` → `publicacion.carpeta_drive`, por ejemplo
   `G:\Mi unidad\OficinaYouTube`.
3. El flujo: Producción corta el Short → Studio lo copia a esa carpeta → lo localiza
   en Drive con el conector → Metricool lo programa en YouTube.

No uses automatización del navegador sobre YouTube Studio: las condiciones de
YouTube prohíben el acceso automatizado fuera de la API y puede costar el canal.
Si en el futuro consigues la auditoría, cambia a `"api_youtube"`.

La API de YouTube sigue haciendo falta solo para **leer** (curva de retención real y
búsqueda de outliers), sin ninguna solicitud a Google; la pantalla de
consentimiento se deja publicada pero sin verificar (aparece un aviso que aceptas
tú). Si no quieres tocar Google Cloud, Retención puede usar solo las métricas de
Metricool (sin la curva por segundo).

## Varios canales (4 por defecto)

Los canales están en `config.json` → `canales` y en la pestaña **Canales** de la
hoja (cada uno con su nicho fijo y distinto: Historia y Misterios, Ciencia y
Espacio, Dinero y Finanzas, Mente y Conducta; `originalidad.py nichos-check`
verifica que no se solapen). El proceso es el mismo para
todos: Tendencias, Producción y Retención corren **una vez por canal** (con las
horas desfasadas) y Studio es **una sola tarea** para todos.

**Solo con el método `api_youtube`**: la cuota de YouTube es del proyecto de Google
Cloud, no del canal. Los 4 canales comparten las mismas 10.000 unidades diarias, o
sea unas **5 subidas al día entre todos** (`herramientas/cuota.py estado` lo muestra). Studio las reparte
por turnos y Producción solo fabrica lo que cabe en la cola de cada canal
(`max_cola_listos`), así que no se gastan créditos en videos que no se pueden
subir. Para publicar más hay que pedir ampliación de cuota a Google.

> No crees un proyecto de Google Cloud por canal para conseguir más cuota: las
> políticas de la API de YouTube prohíben usar varios proyectos para el mismo
> fin con el objetivo de esquivar la cuota, y puede costarte el acceso a la API.
> Una sola credencial (`client_secret.json`) para todos; un token por canal.

Autorizar cada canal (una vez), eligiendo el canal correcto en el navegador:
```powershell
python oficina-local\herramientas\youtube.py --canal canal1 auth
python oficina-local\herramientas\youtube.py --canal canal2 auth
```
Para añadir o quitar canales, edita `config.json` y la pestaña Canales, y vuelve
a ejecutar `instalar.ps1`.

## Cómo funciona

| Agente | Cuándo | Qué hace |
|---|---|---|
| Tendencias | diario 07:13 (+7 min por canal) | Elige nicho, busca videos con 10× la mediana de su canal (alarma) y deja temas nuevos en la Cola |
| Producción | 02:37 y 14:37 (+25 min por canal) | 1 video madre por ejecución → guion por bloques, voz y animación (Higgsfield), corte en Shorts, subtítulos, 10 portadas y elige una |
| Studio | cada hora, un solo agente para todos los canales | Programa en YouTube por Metricool a las mejores horas, repartiendo entre canales |
| Retención | diario 23:21 (+6 min por canal) | Lee la curva real; si se pierde audiencia antes del segundo 3, deja una instrucción para el guionista |

Producción se frena sola cuando su canal tiene 8 Shorts listos sin publicar, así
que el gasto se ajusta al ritmo real de publicación.

## Anti-repetición (guardián de originalidad)

`herramientas/originalidad.py` guarda en `datos/originalidad.db` todo lo
producido y bloquea lo que se repita, tanto entre videos como entre Shorts:

- **Textos** (temas, ganchos, guiones, títulos, escenas): compara por
  significado con un modelo de IA multilingüe que corre en local, así que también
  detecta paráfrasis. Sin el modelo usa comparación de letras (solo textos casi
  idénticos).
- **Video**: huella perceptual (pHash) de un fotograma por segundo. Rechaza un
  Short si más del 15 % de sus fotogramas ya aparecen en otro video o Short, o si
  su gancho visual (primeros 3 s) ya se usó. Detecta copias aunque cambie la
  resolución o la compresión.
- **Cortes**: los Shorts de un mismo video madre nunca se solapan.
- **Video madre**: no se publica entero (`publicar_madre: false`) porque sus
  Shorts ya lo cubren.

Los umbrales están en `config.json` → `originalidad`.

## Requisitos

- Windows 10/11, gama media-alta. Con GPU NVIDIA, los subtítulos y el modelo de
  textos van mucho más rápido; sin GPU funcionan en CPU.
- Cuenta de claude.ai con los conectores Google Sheets, higgsfield, vidIQ y
  Metricool conectados.
- Un canal de YouTube y una cuenta de Google Cloud (gratis).

## Instalación

1. **Clona el repositorio** (rama `claude/prompt-skills-analysis-0adb62`) en, por
   ejemplo, `C:\OficinaYouTube`.
2. **Abre PowerShell como administrador** en `oficina-local` y ejecuta:
   ```powershell
   powershell -ExecutionPolicy Bypass -File instalar.ps1
   ```
   Instala Python, FFmpeg, Git, Node.js, las librerías y Claude Code, copia
   `plantilla-permisos.json` a `.claude\settings.json` (lo que los agentes pueden
   hacer sin preguntar: revísalo), desactiva la suspensión y crea las 4 tareas
   programadas (carpeta `OficinaYouTube` del
   Programador de tareas).
3. **Inicia sesión en Claude Code**: abre una terminal en la raíz del repositorio,
   ejecuta `claude` e inicia sesión con tu cuenta de claude.ai. Escribe `/mcp`
   para confirmar que aparecen tus conectores.
4. **Acceso a YouTube** (una sola vez):
   1. En https://console.cloud.google.com crea un proyecto.
   2. Activa **YouTube Data API v3** y **YouTube Analytics API**.
   3. En *Pantalla de consentimiento OAuth*, elige **Externo**, añade tu correo
      como usuario de prueba y luego **publica la app** (si se queda en "Prueba",
      el acceso caduca cada 7 días).
   4. En *Credenciales*, crea un **ID de cliente OAuth** de tipo **App de
      escritorio**, descarga el JSON y guárdalo como
      `oficina-local\datos\client_secret.json`.
   5. Ejecuta `python oficina-local\herramientas\youtube.py auth` y acepta en el
      navegador con la cuenta del canal.
5. **Prueba cada agente a mano** antes de dejarlo solo:
   ```powershell
   powershell -ExecutionPolicy Bypass -File oficina-local\ejecutar_agente.ps1 -Rol tendencias
   ```
   El resultado queda en `oficina-local\logs\`. Si ves herramientas denegadas,
   revisa los nombres con `/permissions` dentro de `claude` y ajusta
   `.claude\settings.json`.
6. **Para que arranque solo tras un corte de luz**: activa en la BIOS
   "Restore on AC power loss = On" y el inicio de sesión automático de Windows
   (las tareas corren en tu sesión de usuario). Un SAI evita cortes cortos.

## Avisos importantes

- **Verificación de Google para publicar en público**: YouTube deja en
  **privado** los videos subidos por la API desde proyectos de Google Cloud no
  auditados. Para publicar en público de forma automática hay que pedir la
  auditoría de cumplimiento de la API de YouTube (formulario gratuito, puede
  tardar semanas). Mientras tanto, los Shorts se suben y programan pero quedan
  privados.
- **Cuota**: 10.000 unidades diarias por defecto para TODOS los canales; cada
  subida gasta unas 1.650 y cada búsqueda 100. Si se agota, las subidas fallan
  con `quotaExceeded`, sin penalización, y se retoman a las 05:00 (Argentina).
  Para más, pide ampliación de cuota a Google.
- **Uso de tu plan de Claude**: son unas 16 ejecuciones diarias de agentes más Studio
  cada hora (si hay cuota). Vigila el consumo la primera semana.
- **Contenido con IA**: la subida marca el video como contenido sintético, como
  exige YouTube. Publicar mucho contenido automático y parecido puede costar la
  monetización; el guardián ayuda, pero revisa el Log y el canal con frecuencia.
- **Pausa de emergencia**: pon `estado = PAUSADO` en la pestaña Config de la hoja.

## Archivos

```
oficina-local/
  instalar.ps1           instalador y tareas programadas
  ejecutar_agente.ps1    lanza un agente (candado, registro, avisos de Windows)
  plantilla-permisos.json  permisos de los agentes (el instalador la copia a .claude\settings.json)
  config.json            límites, umbrales de originalidad, horarios
  agentes/               instrucciones de cada agente + reglas comunes
  herramientas/
    originalidad.py      guardián anti-repetición
    shorts.py            corte en Shorts sin solapes, 9:16, audio, subtítulos
    publicar_prep.py     copia los Shorts a la carpeta de Drive que lee Metricool
    youtube.py           subir/programar (solo api_youtube), retención real, outliers 10x (--canal)
    cuota.py             libro de cuota diaria compartida por todos los canales
  datos/                 base de originalidad, videos, credenciales (no se sube a git)
  logs/                  registros de cada ejecución (no se sube a git)
```
