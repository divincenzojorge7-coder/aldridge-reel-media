<#
  Lanza un agente de la Oficina YouTube con Claude Code en modo no interactivo.
  Uso:  powershell -ExecutionPolicy Bypass -File ejecutar_agente.ps1 -Rol produccion
  Roles: tendencias, produccion, studio, retencion
#>
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('tendencias', 'produccion', 'studio', 'retencion')]
  [string]$Rol
)

$ErrorActionPreference = 'Stop'
$Oficina = $PSScriptRoot
$Repo = Split-Path $Oficina -Parent
$Logs = Join-Path $Oficina 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# Candado: nunca dos copias del mismo agente a la vez
$Candado = Join-Path $Logs "$Rol.lock"
if (Test-Path $Candado) {
  $edad = (Get-Date) - (Get-Item $Candado).LastWriteTime
  if ($edad.TotalHours -lt 3) { Write-Output "$Rol ya se esta ejecutando; salgo."; exit 0 }
  Remove-Item $Candado -Force   # candado viejo de una ejecucion que se colgo
}
New-Item -ItemType File -Path $Candado | Out-Null

$Fecha = Get-Date -Format 'yyyyMMdd-HHmmss'
$Log = Join-Path $Logs "$Rol-$Fecha.log"
$Prompt = Get-Content (Join-Path $Oficina "agentes\$Rol.md") -Raw -Encoding UTF8
$Prompt = "Fecha y hora local: $(Get-Date -Format 'yyyy-MM-dd HH:mm zzz').`n`n" + $Prompt

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
    $n.ShowBalloonTip(15000, "Oficina YouTube - $Rol", $Aviso, 'Info')
    Start-Sleep -Seconds 16
    $n.Dispose()
  }
}
catch {
  "ERROR al lanzar ${Rol}: $_" | Out-File -FilePath $Log -Append -Encoding UTF8
}
finally {
  Remove-Item $Candado -Force -ErrorAction SilentlyContinue
  # conserva 30 dias de registros
  Get-ChildItem $Logs -Filter '*.log' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Force
}
