# Shared Windows PowerShell 5.1 functions. Dot-source; no startup side effects.
Set-StrictMode -Version Latest

function New-OfficeContext {
    param([string]$ProjectRoot, [string]$StateDir)
    if ($StateDir -notmatch '^(?:[A-Za-z]:\\|\\\\[^\\]+\\[^\\]+)') { throw 'StateDir must be an explicit absolute path.' }
    $project = (Resolve-Path -LiteralPath $ProjectRoot -ErrorAction Stop).ProviderPath.TrimEnd('\')
    $state = [IO.Path]::GetFullPath($StateDir).TrimEnd('\')
    $runtime = Join-Path $state 'runtime'
    [IO.Directory]::CreateDirectory($runtime) | Out-Null
    return [pscustomobject]@{ProjectRoot=$project; StateDir=$state; RuntimeDir=$runtime; Registry=(Join-Path $runtime 'services-windows.json')}
}

function Enter-OfficeManagementLock {
    param($Context)
    try {
        return [IO.File]::Open((Join-Path $Context.RuntimeDir 'services-management-windows.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch { throw 'Another Windows service manager is active, or the management lock cannot be opened.' }
}

function Read-OfficeEnvironment {
    param([string]$Path)
    $values = @{}
    if (-not $Path) { return $values }
    $lineNumber = 0
    foreach ($line in [IO.File]::ReadAllLines((Resolve-Path -LiteralPath $Path -ErrorAction Stop).ProviderPath, [Text.Encoding]::UTF8)) {
        $lineNumber++
        if ($line -match '^\s*(#.*)?$') { continue }
        if ($line -notmatch '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
            throw "Invalid environment assignment at line $lineNumber. Values are not displayed."
        }
        $name = $matches[1]
        $value = $matches[2].Trim()
        if ($value.StartsWith('"') -or $value.StartsWith("'")) {
            if ($value.Length -lt 2 -or $value[$value.Length-1] -cne $value[0]) {
                throw "Unclosed environment value at line $lineNumber. Values are not displayed."
            }
            $value = $value.Substring(1, $value.Length-2)
        }
        $values[$name] = $value
    }
    return $values
}

function ConvertTo-OfficeNativeArgument {
    param([AllowEmptyString()][string]$Value)
    # CommandLineToArgvW/CRT escaping: double backslashes before quotes/end.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Get-OfficeProcessIdentity {
    param([int]$ProcessId)
    try {
        $process = [Diagnostics.Process]::GetProcessById($ProcessId)
        try {
            if ($process.HasExited) { return $null }
            $start = $process.StartTime.ToUniversalTime().Ticks.ToString()
            $executable = $process.MainModule.FileName
            $native = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
            if (-not $native -or -not $native.CommandLine) { return $null }
            return [pscustomobject]@{pid=$ProcessId; start_time_utc_ticks=$start; executable=$executable; command_line=[string]$native.CommandLine}
        } finally { $process.Dispose() }
    } catch { return $null }
}

function Test-OfficeManagedProcess {
    param($Context, $Record)
    try {
        if (-not [string]::Equals($Record.project_root, $Context.ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) { return $false }
        $identity = Get-OfficeProcessIdentity ([int]$Record.pid)
        if (-not $identity) { return $false }
        return ($identity.start_time_utc_ticks -ceq [string]$Record.start_time_utc_ticks -and
            [string]::Equals($identity.executable, $Record.executable, [StringComparison]::OrdinalIgnoreCase) -and
            $identity.command_line -ceq $Record.command_line -and
            ($identity.executable.StartsWith($Context.ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
             $identity.command_line.IndexOf($Context.ProjectRoot + '\', [StringComparison]::OrdinalIgnoreCase) -ge 0))
    } catch { return $false }
}

function Start-OfficeManagedProcess {
    param($Context, [string]$Name, [string]$Executable, [string[]]$ArgumentList, [string]$WorkingDirectory, [hashtable]$Environment)
    $saved = @{}
    $process = $null
    try {
        foreach ($key in $Environment.Keys) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], 'Process')
        }
        $arguments = ($ArgumentList | ForEach-Object { ConvertTo-OfficeNativeArgument $_ }) -join ' '
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
        $stdout = Join-Path $Context.RuntimeDir "$Name-$stamp.stdout.log"
        $stderr = Join-Path $Context.RuntimeDir "$Name-$stamp.stderr.log"
        $process = Start-Process -FilePath $Executable -ArgumentList $arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -ErrorAction Stop
        $null = $process.Handle
        $childStartTime = $process.StartTime.ToUniversalTime().Ticks.ToString()
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process') }
    }
    try {
        Start-Sleep -Milliseconds 400
        $identity = Get-OfficeProcessIdentity $process.Id
        if ($process.HasExited -or -not $identity -or $identity.start_time_utc_ticks -cne $childStartTime) { throw "$Name exited during startup; inspect its local logs." }
        $record = [pscustomobject]@{
            pid=$identity.pid; start_time_utc_ticks=$identity.start_time_utc_ticks
            executable=$identity.executable; command_line=$identity.command_line
            project_root=$Context.ProjectRoot; cwd=$WorkingDirectory
            stdout_log=$stdout; stderr_log=$stderr
        }
        if (-not (Test-OfficeManagedProcess $Context $record)) { throw "$Name has no verifiable project identity." }
        return $record
    } catch {
        # The handle refers to the child just created, never a port/PID lookup.
        if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ceq $childStartTime) {
            Stop-OfficeProcessTree -RootProcess $process
        }
        throw
    } finally { $process.Dispose() }
}

function Stop-OfficeProcessTree {
    param([Diagnostics.Process]$RootProcess)
    # RootProcess is a handle to a directly created or fully verified process.
    # Keep every discovered handle open until all exits have been verified.
    $null = $RootProcess.Handle
    $nodes = [Collections.Generic.List[object]]::new()
    $seen = @{}
    $rootNode = [pscustomobject]@{Process=$RootProcess; StartTicks=$RootProcess.StartTime.ToUniversalTime().Ticks}
    $nodes.Add($rootNode)
    $seen["$($RootProcess.Id):$($rootNode.StartTicks)"] = $true
    $discover = {
        param($ParentNode)
        $parent = $ParentNode.Process
        $upperTicks = [long]::MaxValue
        if ($parent.HasExited) { $upperTicks = $parent.ExitTime.ToUniversalTime().Ticks }
        foreach ($native in @(Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $($parent.Id)" -ErrorAction Stop)) {
            $child = $null
            try {
                $child = [Diagnostics.Process]::GetProcessById([int]$native.ProcessId)
                $null = $child.Handle
                $ticks = $child.StartTime.ToUniversalTime().Ticks
                # CreationDate is microsecond precision. The handle must match
                # the CIM snapshot, and the child must have been born while its
                # verified parent was alive. PID reuse fails these checks.
                $snapshotTicks = ([DateTime]$native.CreationDate).ToUniversalTime().Ticks
                if ($parent.HasExited) { $upperTicks = $parent.ExitTime.ToUniversalTime().Ticks }
                if ([Math]::Abs($ticks - $snapshotTicks) -ge 10 -or
                    $ticks -lt $ParentNode.StartTicks -or $ticks -gt $upperTicks) { continue }
                $key = "$($child.Id):$ticks"
                if ($seen.ContainsKey($key)) { continue }
                $seen[$key] = $true
                $nodes.Add([pscustomobject]@{Process=$child; StartTicks=$ticks})
                $child = $null # ownership of the handle transfers to nodes
            } catch [ArgumentException] {
                # Exited between the CIM snapshot and handle acquisition.
            } finally { if ($child) { $child.Dispose() } }
        }
    }
    try {
        for ($index=0; $index -lt $nodes.Count; $index++) {
            $node = $nodes[$index]
            $process = $node.Process
            & $discover $node
            # Kill parents before their children. Then inspect again using the
            # parent's native exit time to catch children born during discovery;
            # the stopped parent can no longer create any more descendants.
            if (-not $process.HasExited) {
                if ($process.StartTime.ToUniversalTime().Ticks -ne $node.StartTicks) { throw 'Managed process identity changed before termination.' }
                $process.Kill()
                if (-not $process.WaitForExit(5000)) { throw 'Managed process tree did not stop within five seconds.' }
            }
            & $discover $node
        }
        foreach ($node in $nodes) {
            if (-not $node.Process.HasExited) { throw 'A managed descendant survived termination.' }
        }
    } finally {
        foreach ($node in $nodes) {
            if ($node.Process -ne $RootProcess) { $node.Process.Dispose() }
        }
    }
}

function Stop-OfficeManagedProcess {
    param($Context, $Record)
    if (-not (Test-OfficeManagedProcess $Context $Record)) { return $false }
    try {
        $process = [Diagnostics.Process]::GetProcessById([int]$Record.pid)
        try {
            # Pin and recheck the native start time immediately before termination.
            $null = $process.Handle
            if ($process.StartTime.ToUniversalTime().Ticks.ToString() -cne [string]$Record.start_time_utc_ticks) { return $false }
            Stop-OfficeProcessTree -RootProcess $process
        } finally { $process.Dispose() }
        return $true
    } catch [ArgumentException] { return $false }
}

function Get-OfficeWorkerCommand {
    param([string]$ProjectRoot)
    # Import by its real module name so Windows spawn can pickle _worker_loop.
    return @{Executable=(Join-Path $ProjectRoot 'backend\.venv\Scripts\python.exe'); Arguments=@('-c','import sys;sys.path.insert(0,sys.argv.pop(1));from office.worker import main;main()',(Join-Path $ProjectRoot 'backend')); Cwd=(Join-Path $ProjectRoot 'backend')}
}

function Read-OfficeRegistry {
    param($Context)
    if (-not (Test-Path -LiteralPath $Context.Registry)) { return $null }
    $record = [IO.File]::ReadAllText($Context.Registry, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if ($record.scope -cne 'heobrain-content-office-windows' -or
        -not [string]::Equals($record.project_root, $Context.ProjectRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not [string]::Equals($record.state_dir, $Context.StateDir, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Service registry belongs to another project/state directory. No process was changed.'
    }
    return $record
}

function Write-OfficeRegistry {
    param($Context, $Record)
    $temporary = $Context.Registry + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, ($Record | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $Context.Registry -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force } }
}

function Get-OfficeLongPathsEnabled {
    try {
        return ((Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled -eq 1)
    } catch { return $false }
}

function Assert-OfficeStatePathBudget {
    param([string]$StateDir, [bool]$LongPathsEnabled)
    # Deepest artifact below the state folder: artifacts\job_<16>\<64-hex source hash>\production-<24>\<file name>.
    # That adds about 160 characters, so without long-path support the state folder itself must stay short.
    $artifactBudget = 160
    $limit = 259 - $artifactBudget
    if (-not $LongPathsEnabled -and $StateDir.TrimEnd('\').Length -gt $limit) {
        throw "StateDir exceeds $limit characters and Windows long paths are disabled; artifact paths would pass MAX_PATH (260). Use a shorter state folder, or set HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem LongPathsEnabled=1 and restart. No process was changed."
    }
}

function Assert-OfficePortAvailable {
    param([int]$Port)
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    try { $listener.Start() }
    catch { throw "Port $Port is in use. No existing process was changed." }
    finally { $listener.Stop() }
}

function Test-OfficeAuthorizedWindow {
    param($Window, [DateTimeOffset]$Now = [DateTimeOffset]::UtcNow)
    try {
        if (-not $Window -or -not $Window['authorized_end'] -or $Window['status'] -in @('closed','stopped')) { return $false }
        $end = [DateTimeOffset]::Parse($Window['authorized_end'])
        if ($Window['authorized_end'] -notmatch '(Z|[+-]\d\d:\d\d)$') { return $false }
        if ($Window['authorized_start']) {
            if ($Window['authorized_start'] -notmatch '(Z|[+-]\d\d:\d\d)$') { return $false }
            if ([DateTimeOffset]::Parse($Window['authorized_start']) -gt $Now) { return $false }
        }
        return $Now -lt $end
    } catch { return $false }
}

function Get-OfficeAuthorizedWindow {
    param([string]$Python, [string]$StateDir)
    # Read SQLite in read-only mode: never initialize, authorize, reset or extend.
    $code = @'
import datetime,json,pathlib,sqlite3,sys
p=pathlib.Path(sys.argv[1])/'office.sqlite3'
if not p.is_file(): raise SystemExit('No existing office database; automation was not started.')
with sqlite3.connect(p.as_uri()+'?mode=ro',uri=True) as db:
    row=db.execute('SELECT value FROM settings WHERE key=?',('work_window',)).fetchone()
print(json.dumps(json.loads(row[0]) if row else {},ensure_ascii=True))
'@
    $result = & $Python -c $code $StateDir
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read the saved authorized window; automation was not started.' }
    $windowObject = $result | ConvertFrom-Json
    $window = @{}
    foreach ($property in $windowObject.PSObject.Properties) { $window[$property.Name] = $property.Value }
    if (-not (Test-OfficeAuthorizedWindow $window)) { throw 'No existing open authorized window; automation was not started.' }
    return $window
}
