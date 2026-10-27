[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory = $true)][string]$StateDir,
    [ValidateSet('all','api','frontend','worker','watcher')][string]$Service = 'all'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-launcher.ps1')
$context = New-OfficeContext -ProjectRoot $ProjectRoot -StateDir $StateDir
$lock = Enter-OfficeManagementLock $context
try {
    $record = Read-OfficeRegistry $context
    if (-not $record) { Write-Output 'No Windows service registry. No process was changed.'; return }
    $targets = @($record.services.PSObject.Properties | ForEach-Object { $_.Name })
    if ($Service -ne 'all') { $targets = @($Service) }
    foreach ($name in $targets) {
        $property = $record.services.PSObject.Properties[$name]
        if (-not $property) { continue }
        if (Stop-OfficeManagedProcess $context $property.Value) {
            $property.Value | Add-Member -NotePropertyName termination_requested -NotePropertyValue $true -Force
            Write-Output "$name stopped (verified native identity)."
        } else { Write-Output "$name skipped (absent or ownership mismatch)." }
    }
    Write-OfficeRegistry $context $record
} finally { $lock.Dispose() }
