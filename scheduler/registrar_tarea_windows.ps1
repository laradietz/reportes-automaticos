# Registra una tarea diaria en el Programador de tareas de Windows que ejecuta el pipeline completo.
# Uso:  powershell -ExecutionPolicy Bypass -File scheduler\registrar_tarea_windows.ps1 [-Hora "07:00"]
param([string]$Hora = "07:00", [string]$Nombre = "ReportesAutomaticos")

$raiz   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "No existe $python. Creá el entorno: python -m venv .venv; .\.venv\Scripts\pip install -e ." }

$accion  = New-ScheduledTaskAction -Execute $python -Argument "-m reportes ejecutar" -WorkingDirectory $raiz
$trigger = New-ScheduledTaskTrigger -Daily -At $Hora
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $Nombre -Action $accion -Trigger $trigger -Settings $ajustes -Force | Out-Null
Write-Host "Tarea '$Nombre' registrada: todos los días a las $Hora. Logs en $raiz\logs\pipeline.log"
