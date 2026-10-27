[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory = $true)][string]$StateDir,
    [ValidateRange(1,65535)][int]$ApiPort = 8510,
    [ValidateRange(1,65535)][int]$FrontendPort = 3110,
    [string]$NodePath,
    [string]$EnvFile = $env:OFFICE_ENV_FILE,
    [ValidateSet('production','development')][string]$FrontendMode = 'production',
    [switch]$Worker,
    [switch]$Watcher
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-launcher.ps1')
$context = New-OfficeContext -ProjectRoot $ProjectRoot -StateDir $StateDir
if ($ApiPort -eq $FrontendPort) { throw 'API and frontend ports must differ.' }
$python = Join-Path $context.ProjectRoot 'backend\.venv\Scripts\python.exe'
$next = Join-Path $context.ProjectRoot 'frontend\node_modules\next\dist\bin\next'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Create a native Windows backend/.venv with Python 3.12 first.' }
if (-not $NodePath) {
    $candidates = @('C:\nvm4w\nodejs\node.exe', (Join-Path $env:ProgramFiles 'nodejs\node.exe'))
    $NodePath = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $NodePath) {
        $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
        if ($nodeCommand) { $NodePath = $nodeCommand.Source }
    }
}
if (-not $NodePath -or -not (Test-Path -LiteralPath $NodePath -PathType Leaf)) { throw 'Native node.exe not found; specify -NodePath.' }
if (-not (Test-Path -LiteralPath $next -PathType Leaf)) { throw 'Install native frontend dependencies with npm ci first.' }
if ($FrontendMode -eq 'production' -and -not (Test-Path -LiteralPath (Join-Path $context.ProjectRoot 'frontend\.next\BUILD_ID'))) { throw 'Production frontend build is missing; run npm run build or explicitly use -FrontendMode development.' }
$environment = Read-OfficeEnvironment $EnvFile
$environment['OFFICE_STATE_DIR'] = $context.StateDir
$environment['PYTHONUTF8'] = '1'
$environment['PYTHONIOENCODING'] = 'utf-8'
$environment['OFFICE_API_URL'] = "http://127.0.0.1:$ApiPort"
$lock = Enter-OfficeManagementLock $context
try {
    $previous = Read-OfficeRegistry $context
    $services = @{}
    if ($previous) {
        if ($previous.ports.api -ne $ApiPort -or $previous.ports.frontend -ne $FrontendPort) {
            foreach ($property in $previous.services.PSObject.Properties) {
                if (Test-OfficeManagedProcess $context $property.Value) { throw 'Stop existing managed services before changing ports.' }
            }
        }
        foreach ($property in $previous.services.PSObject.Properties) {
            if (Test-OfficeManagedProcess $context $property.Value) { $services[$property.Name] = $property.Value }
        }
    }
    if ($Worker -or $Watcher) { $null = Get-OfficeAuthorizedWindow -Python $python -StateDir $context.StateDir }
    $commands = [ordered]@{
        api=@{Executable=$python; Arguments=@('-m','uvicorn','office.api:app','--app-dir',(Join-Path $context.ProjectRoot 'backend'),'--host','127.0.0.1','--port',"$ApiPort"); Cwd=(Join-Path $context.ProjectRoot 'backend')}
        frontend=@{Executable=$NodePath; Arguments=@($next, $(if ($FrontendMode -eq 'production') {'start'} else {'dev'}),'--hostname','127.0.0.1','--port',"$FrontendPort"); Cwd=(Join-Path $context.ProjectRoot 'frontend')}
    }
    if ($Worker) { $commands['worker'] = Get-OfficeWorkerCommand -ProjectRoot $context.ProjectRoot }
    if ($Watcher) { $commands['watcher']=@{Executable=$python; Arguments=@((Join-Path $context.ProjectRoot 'scripts\watch_window.py'),'--api-url',"http://127.0.0.1:$ApiPort"); Cwd=$context.ProjectRoot} }
    if (-not $services.ContainsKey('api')) { Assert-OfficePortAvailable $ApiPort }
    if (-not $services.ContainsKey('frontend')) { Assert-OfficePortAvailable $FrontendPort }
    $record = @{scope='heobrain-content-office-windows'; project_root=$context.ProjectRoot; state_dir=$context.StateDir; ports=@{api=$ApiPort;frontend=$FrontendPort}; services=$services}
    $created = @()
    try {
        foreach ($name in $commands.Keys) {
            if ($services.ContainsKey($name)) { continue }
            $command = $commands[$name]
            $services[$name] = Start-OfficeManagedProcess -Context $context -Name $name -Executable $command.Executable -ArgumentList $command.Arguments -WorkingDirectory $command.Cwd -Environment $environment
            $created += $name
            Write-OfficeRegistry $context $record
        }
    } catch {
        foreach ($name in $created) {
            Stop-OfficeManagedProcess $context $services[$name] | Out-Null
            $services.Remove($name)
        }
        Write-OfficeRegistry $context $record
        throw
    }
    Write-Output "Windows office processes managed: http://127.0.0.1:$FrontendPort (API http://127.0.0.1:$ApiPort). Use status-windows.ps1 to inspect process ownership."
    Write-Output "Registry and local logs: $($context.RuntimeDir)"
    if (-not $Worker -and -not $Watcher) { Write-Output 'Worker/watcher were not requested. No work window or budget was changed.' }
} finally { $lock.Dispose() }
