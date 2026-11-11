<#
  Instalador de la Oficina YouTube para Windows 10/11.
  Ejecutar en PowerShell COMO ADMINISTRADOR desde la carpeta oficina-local:
    powershell -ExecutionPolicy Bypass -File instalar.ps1
#>
$ErrorActionPreference = 'Stop'
$Oficina = $PSScriptRoot

function Paso($t) { Write-Host "`n==> $t" -ForegroundColor Cyan }

Paso 'Instalando programas (winget)'
foreach ($id in 'Python.Python.3.12', 'Gyan.FFmpeg', 'Git.Git', 'OpenJS.NodeJS.LTS') {
  winget install --id $id -e --accept-source-agreements --accept-package-agreements --silent
}
# recarga el PATH para ver lo recien instalado
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

Paso 'Instalando librerias de Python'
python -m pip install --upgrade pip
python -m pip install -r (Join-Path $Oficina 'requirements.txt')

Paso 'Instalando Claude Code'
npm install -g @anthropic-ai/claude-code

Paso 'Instalando los permisos de los agentes (.claude\settings.json)'
$Repo = Split-Path $Oficina -Parent
New-Item -ItemType Directory -Force -Path (Join-Path $Repo '.claude') | Out-Null
Copy-Item (Join-Path $Oficina 'plantilla-permisos.json') (Join-Path $Repo '.claude\settings.json') -Force
Write-Host '  Revisa .claude\settings.json: es la lista de lo que los agentes pueden hacer sin preguntar.'

Paso 'Evitando que el equipo se suspenda (enchufado a la corriente)'
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 15

Paso 'Programando los agentes (Programador de tareas de Windows)'
$Lanzador = Join-Path $Oficina 'ejecutar_agente.ps1'
$Ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
  -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Usuario = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

function Accion($rol, $canal) {
  $arg = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Lanzador`" -Rol $rol"
  if ($canal) { $arg += " -Canal $canal" }
  New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
}
function Registrar($nombre, $rol, $canal, $disparadores) {
  Register-ScheduledTask -TaskName $nombre -TaskPath '\OficinaYouTube\' `
    -Action (Accion $rol $canal) -Trigger $disparadores -Settings $Ajustes -Principal $Usuario -Force | Out-Null
  Write-Host "  tarea $nombre creada"
}
function Hora($h, $m, $extra) {   # hora del dia + desfase en minutos (para no lanzar todo a la vez)
  (Get-Date).Date.AddHours($h).AddMinutes($m + $extra)
}

# Lee los canales de config.json
$Config = Get-Content (Join-Path $Oficina 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$Canales = @($Config.canales | ForEach-Object { $_.id })
Write-Host "  canales: $($Canales -join ', ')"

for ($i = 0; $i -lt $Canales.Count; $i++) {
  $c = $Canales[$i]
  # Cada canal se desfasa para que no compitan por Higgsfield ni por la GPU
  Registrar "OficinaYouTube-tendencias-$c" 'tendencias' $c @(New-ScheduledTaskTrigger -Daily -At (Hora 7 13 (7 * $i)))
  Registrar "OficinaYouTube-produccion-$c" 'produccion' $c @(
    (New-ScheduledTaskTrigger -Daily -At (Hora 2 37 (25 * $i))),
    (New-ScheduledTaskTrigger -Daily -At (Hora 14 37 (25 * $i))))
  Registrar "OficinaYouTube-retencion-$c" 'retencion' $c @(New-ScheduledTaskTrigger -Daily -At (Hora 23 21 (6 * $i)))
}
# Studio es UNA sola tarea para todos los canales: reparte la cuota compartida
Registrar 'OficinaYouTube-studio' 'studio' '' @(New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
  -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650))

Paso 'Listo'
Write-Host @"
Faltan 3 pasos manuales (ver README.md):
  1. Abrir una terminal en la carpeta del repositorio, ejecutar 'claude' e iniciar sesion
     con tu cuenta de claude.ai (asi Claude Code usa tus conectores).
  2. Copiar client_secret.json de Google Cloud a oficina-local\datos\ (uno solo para
     todos los canales) y autorizar CADA canal, eligiendolo en el navegador:
     python oficina-local\herramientas\youtube.py --canal canal1 auth
     python oficina-local\herramientas\youtube.py --canal canal2 auth   (y asi con cada uno)
  3. Probar un agente a mano:
     powershell -ExecutionPolicy Bypass -File oficina-local\ejecutar_agente.ps1 -Rol tendencias -Canal canal1
"@
