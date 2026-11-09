# Oficina YouTube local (Windows 24/7)

Equipo de agentes que produce y publica YouTube Shorts sin intervención, en una
computadora Windows siempre encendida. La computadora hace el trabajo pesado
(cortar, subtitular, comprobar originalidad, subir) y la hoja de Google
**Oficina YouTube - Centro de control** sigue siendo el panel para ver y pausar
todo desde el móvil.

## Cómo funciona

| Agente | Cuándo | Qué hace |
|---|---|---|
| Tendencias | diario 07:13 | Elige nicho, busca videos con 10× la mediana de su canal (alarma) y deja temas nuevos en la Cola |
| Producción | 01:37, 06:37, 10:37, 16:37, 21:37 | 1 video madre por ejecución → guion por bloques, voz y animación (Higgsfield), corte en Shorts, subtítulos, 10 portadas y elige una |
| Studio | cada hora | Sube y programa en YouTube a las mejores horas, máximo 6 al día |
| Retención | diario 23:21 | Lee la curva real; si se pierde audiencia antes del segundo 3, deja una instrucción para el guionista |

Producción se frena sola cuando hay 30 Shorts listos sin publicar, así que el
gasto se ajusta al ritmo de publicación.

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
- **Cuota**: 10.000 unidades diarias por defecto; cada subida gasta unas 1.600
  (de ahí el máximo de 6 al día). Para más, pide ampliación de cuota a Google.
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
    youtube.py           subir/programar, retención real, outliers 10x
  datos/                 base de originalidad, videos, credenciales (no se sube a git)
  logs/                  registros de cada ejecución (no se sube a git)
```
