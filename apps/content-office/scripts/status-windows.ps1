[CmdletBinding()]
param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory = $true)][string]$StateDir
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'windows-launcher.ps1')
$context = New-OfficeContext -ProjectRoot $ProjectRoot -StateDir $StateDir
$lock = Enter-OfficeManagementLock $context
try {
    $record = Read-OfficeRegistry $context
    if (-not $record) { Write-Output 'No managed Windows services recorded.'; return }
    foreach ($property in $record.services.PSObject.Properties) {
        [pscustomobject]@{Service=$property.Name; ProcessId=$property.Value.pid; Status=$(if (Test-OfficeManagedProcess $context $property.Value) {'running-owned'} else {'stopped-or-identity-mismatch'})}
    }
} finally { $lock.Dispose() }
