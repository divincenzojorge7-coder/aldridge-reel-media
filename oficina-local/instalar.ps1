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

function Accion($rol) {
  New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Lanzador`" -Rol $rol"
}

$Tareas = @{
  'tendencias' = @(New-ScheduledTaskTrigger -Daily -At '07:13')
  'produccion' = @('01:37', '06:37', '10:37', '16:37', '21:37' | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
  'studio'     = @(New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) `
                    -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650))
  'retencion'  = @(New-ScheduledTaskTrigger -Daily -At '23:21')
}
foreach ($rol in $Tareas.Keys) {
  Register-ScheduledTask -TaskName "OficinaYouTube-$rol" -TaskPath '\OficinaYouTube\' `
    -Action (Accion $rol) -Trigger $Tareas[$rol] -Settings $Ajustes -Principal $Usuario -Force | Out-Null
  Write-Host "  tarea OficinaYouTube-$rol creada"
}

Paso 'Listo'
Write-Host @"
Faltan 3 pasos manuales (ver README.md):
  1. Abrir una terminal en la carpeta del repositorio, ejecutar 'claude' e iniciar sesion
     con tu cuenta de claude.ai (asi Claude Code usa tus conectores).
  2. Copiar client_secret.json de Google Cloud a oficina-local\datos\ y ejecutar:
     python oficina-local\herramientas\youtube.py auth
  3. Probar un agente a mano:
     powershell -ExecutionPolicy Bypass -File oficina-local\ejecutar_agente.ps1 -Rol tendencias
"@
