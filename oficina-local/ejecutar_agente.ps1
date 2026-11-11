<#
  Lanza un agente de la Oficina YouTube con Claude Code en modo no interactivo.
  Uso:  powershell -ExecutionPolicy Bypass -File ejecutar_agente.ps1 -Rol produccion -Canal canal2
  Roles: tendencias, produccion, retencion (necesitan -Canal) y studio (sin -Canal: atiende a todos)
#>
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('tendencias', 'produccion', 'studio', 'retencion')]
  [string]$Rol,
  [string]$Canal = ''
)

$ErrorActionPreference = 'Stop'
if ($Rol -ne 'studio' -and -not $Canal) { throw "El rol $Rol necesita -Canal (por ejemplo canal1)" }
if ($Rol -eq 'studio') { $Canal = 'TODOS' }
$Etiqueta = "$Rol-$Canal"
$Oficina = $PSScriptRoot
$Repo = Split-Path $Oficina -Parent
$Logs = Join-Path $Oficina 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# Studio con la API de YouTube: si la cuota de hoy ya no da para ninguna subida,
# ni siquiera arrancamos Claude. Con Metricool no hay cuota local que consultar.
$Metodo = (Get-Content (Join-Path $Oficina 'config.json') -Raw -Encoding UTF8 | ConvertFrom-Json).publicacion.metodo
if ($Rol -eq 'studio' -and $Metodo -eq 'api_youtube') {
  try {
    $q = (& python (Join-Path $Oficina 'herramientas\cuota.py') estado | Out-String) | ConvertFrom-Json
    if ($q.subidas_aun_posibles_hoy -lt 1) { Write-Output "Sin cuota de subida hoy; no lanzo Studio."; exit 0 }
  } catch { }   # si el contador falla, se lanza igualmente
}

# Candado: nunca dos copias del mismo agente a la vez
$Candado = Join-Path $Logs "$Etiqueta.lock"
if (Test-Path $Candado) {
  $edad = (Get-Date) - (Get-Item $Candado).LastWriteTime
  if ($edad.TotalHours -lt 3) { Write-Output "$Etiqueta ya se esta ejecutando; salgo."; exit 0 }
  Remove-Item $Candado -Force   # candado viejo de una ejecucion que se colgo
}
New-Item -ItemType File -Path $Candado | Out-Null

$Fecha = Get-Date -Format 'yyyyMMdd-HHmmss'
$Log = Join-Path $Logs "$Etiqueta-$Fecha.log"
$Prompt = Get-Content (Join-Path $Oficina "agentes\$Rol.md") -Raw -Encoding UTF8
$Prompt = "Fecha y hora local: $(Get-Date -Format 'yyyy-MM-dd HH:mm zzz').`nCanal asignado: $Canal`n`n" + $Prompt
if ($Canal -ne 'TODOS') { $env:YT_CANAL = $Canal }

try {
  Set-Location $Repo
  # dontAsk: solo usa lo permitido en .claude/settings.json y nunca se queda esperando
  $Salida = $Prompt | & claude -p --permission-mode dontAsk --output-format text 2>&1
  $Salida | Out-File -FilePath $Log -Encoding UTF8
  $Texto = ($Salida | Out-String)

  if ($Texto -match '(ALARMA 10x|AVISO GUIONISTA|FALLO)[^\r\n]*') {
    $Aviso = $Matches[0]
    Add-Type -AssemblyName System.Windows.Forms
    $n = New-Object System.Windows.Forms.NotifyIcon
    $n.Icon = [System.Drawing.SystemIcons]::Information
    $n.Visible = $true
    $n.ShowBalloonTip(15000, "Oficina YouTube - $Etiqueta", $Aviso, 'Info')
    Start-Sleep -Seconds 16
    $n.Dispose()
  }
}
catch {
  "ERROR al lanzar ${Etiqueta}: $_" | Out-File -FilePath $Log -Append -Encoding UTF8
}
finally {
  Remove-Item $Candado -Force -ErrorAction SilentlyContinue
  # conserva 30 dias de registros
  Get-ChildItem $Logs -Filter '*.log' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force
}
