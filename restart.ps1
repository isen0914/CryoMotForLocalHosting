param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 8001
)

$ErrorActionPreference = 'Stop'

function Stop-PortListeners {
  param([int[]]$Ports)

  foreach ($p in $Ports) {
    $listeners = @()
    try {
      $listeners = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    } catch {
      # If Get-NetTCPConnection isn't available, just skip.
      $listeners = @()
    }

    foreach ($l in $listeners) {
      if ($null -ne $l.OwningProcess -and $l.OwningProcess -ne 0) {
        try {
          Stop-Process -Id $l.OwningProcess -Force -ErrorAction Stop
          Write-Host "Stopped PID $($l.OwningProcess) (port $p)"
        } catch {
          Write-Warning "Failed stopping PID $($l.OwningProcess) on port ${p}: $($_.Exception.Message)"
        }
      }
    }
  }
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
  throw "Missing venv python at: $venvPython`nExpected backend venv at backend\\.venv."
}

Stop-PortListeners -Ports @($BackendPort, $FrontendPort)

$backendCmd = "Set-Location -LiteralPath '$backendDir'; & '$venvPython' -m uvicorn main:app --host 0.0.0.0 --port $BackendPort"
$frontendCmd = "Set-Location -LiteralPath '$frontendDir'; & '$venvPython' -m http.server $FrontendPort"

Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command', $backendCmd) | Out-Null
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command', $frontendCmd) | Out-Null

Write-Host "Backend:  http://localhost:$BackendPort"
Write-Host "Docs:     http://localhost:$BackendPort/docs"
Write-Host "Frontend: http://localhost:$FrontendPort/"
Write-Host "Alt UI:   http://localhost:$BackendPort/frontend/"
