param(
    [Parameter(Mandatory = $true)][string]$TestRoot,
    [string]$PythonPath = 'C:\Python312\python.exe',
    [string]$NodePath,
    [string]$RealProjectRoot
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '..\windows-launcher.ps1')

function Assert-True($Condition, [string]$Message) {
    if (-not $Condition) { throw "FAIL: $Message" }
}
function Assert-Throws([scriptblock]$Action, [string]$Message) {
    $threw = $false
    try { & $Action | Out-Null } catch { $threw = $true }
    Assert-True $threw $Message
}

# Breaks caught: unsafe PID reuse, shell evaluation/argument splitting, environment
# leaks, registry scope confusion, duplicate managers, and unbounded automation.
$testName = 'office ' + [char]0xD55C + [char]0xAE00 + ' (launcher) ' + [guid]::NewGuid().ToString('N')
$root = Join-Path $TestRoot $testName
$app = Join-Path $root 'project (native)'
$state = Join-Path $root 'state'
$processRecord = $null
[IO.Directory]::CreateDirectory($app) | Out-Null
try {
    Assert-Throws { New-OfficeContext -ProjectRoot $app -StateDir 'relative-state' } 'relative state rejected'
    Assert-Throws { New-OfficeContext -ProjectRoot $app -StateDir 'C:relative-state' } 'drive-relative state rejected'
    Assert-Throws { New-OfficeContext -ProjectRoot $app -StateDir '\relative-state' } 'current-drive relative state rejected'
    $context = New-OfficeContext -ProjectRoot $app -StateDir $state
    $lock = Enter-OfficeManagementLock $context
    try {
        Assert-Throws { Enter-OfficeManagementLock $context } 'second manager rejected'
    } finally { $lock.Dispose() }
    $lock = Enter-OfficeManagementLock $context
    $lock.Dispose()

    $envFile = Join-Path $root 'secret.env'
    [IO.File]::WriteAllText($envFile, "# local only`nOFFICE_LAUNCHER_TEST='secret literal `$() & value'`nEMPTY_VALUE=`n", [Text.UTF8Encoding]::new($false))
    $environment = Read-OfficeEnvironment $envFile
    Assert-True ($environment['OFFICE_LAUNCHER_TEST'] -ceq 'secret literal $() & value') 'environment values are literal'
    Assert-True ($environment['EMPTY_VALUE'] -ceq '') 'empty environment value retained'
    [IO.File]::WriteAllText($envFile, 'bad secret literal', [Text.UTF8Encoding]::new($false))
    $parseError = $null
    try { Read-OfficeEnvironment $envFile | Out-Null } catch { $parseError = $_.Exception.Message }
    Assert-True ($null -ne $parseError) 'invalid environment assignment rejected'
    Assert-True (-not $parseError.Contains('bad secret literal')) 'parse errors hide secret content'

    $now = [DateTimeOffset]::Parse('2026-10-27T03:00:00Z')
    Assert-True (-not (Test-OfficeAuthorizedWindow @{} $now)) 'missing window is closed'
    Assert-True (-not (Test-OfficeAuthorizedWindow @{authorized_end='2026-10-27T02:00:00Z'} $now)) 'expired window closed'
    Assert-True (-not (Test-OfficeAuthorizedWindow @{authorized_start='2026-10-27T04:00:00Z'; authorized_end='2026-10-27T05:00:00Z'} $now)) 'future window closed'
    Assert-True (-not (Test-OfficeAuthorizedWindow @{status='stopped'; authorized_end='2026-10-27T04:00:00Z'} $now)) 'stopped window closed'
    Assert-True (Test-OfficeAuthorizedWindow @{authorized_start='2026-10-27T02:00:00Z'; authorized_end='2026-10-27T04:00:00Z'} $now) 'existing active window accepted'

    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { Assert-Throws { Assert-OfficePortAvailable $listener.LocalEndpoint.Port } 'occupied port rejected' }
    finally { $listener.Stop() }

    # Regression: artifact paths add about 160 characters below the state folder.
    # Without Windows long-path support a long state folder must be refused up front.
    $longState = 'C:' + ('x' * 120)
    Assert-Throws { Assert-OfficeStatePathBudget -StateDir $longState -LongPathsEnabled $false } 'long state folder rejected without long path support'
    Assert-OfficeStatePathBudget -StateDir $longState -LongPathsEnabled $true
    Assert-OfficeStatePathBudget -StateDir 'C:\office-state' -LongPathsEnabled $false
    Assert-True ((Get-OfficeLongPathsEnabled) -is [bool]) 'long path setting is readable as a boolean'

    $fixture = Join-Path $app 'harmless fixture.py'
    $output = Join-Path $app 'arguments.json'
    [IO.File]::WriteAllText($fixture, "import json,os,pathlib,sys,time`npathlib.Path(sys.argv[1]).write_text(json.dumps({'args':sys.argv[2:],'env':os.getenv('OFFICE_LAUNCHER_TEST')},ensure_ascii=False),encoding='utf-8')`ntime.sleep(120)`n", [Text.UTF8Encoding]::new($false))
    $special = @('space value', 'paren (value)', ('unicode ' + [char]0xD55C), 'embedded"quote', 'trailing\', '')
    $original = [Environment]::GetEnvironmentVariable('OFFICE_LAUNCHER_TEST', 'Process')
    [Environment]::SetEnvironmentVariable('OFFICE_LAUNCHER_TEST', 'parent-preserved', 'Process')
    try {
        $processRecord = Start-OfficeManagedProcess -Context $context -Name 'fixture' -Executable $PythonPath -ArgumentList (@($fixture, $output) + $special) -WorkingDirectory $app -Environment $environment
        Assert-True ([Environment]::GetEnvironmentVariable('OFFICE_LAUNCHER_TEST','Process') -ceq 'parent-preserved') 'parent environment restored'
    } finally { [Environment]::SetEnvironmentVariable('OFFICE_LAUNCHER_TEST', $original, 'Process') }
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while (-not (Test-Path -LiteralPath $output) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
    $result = [IO.File]::ReadAllText($output, [Text.Encoding]::UTF8) | ConvertFrom-Json
    for ($i=0; $i -lt $special.Count; $i++) {
        Assert-True ($result.args[$i] -ceq $special[$i]) "native argument $i round trips"
    }
    Assert-True ($result.env -ceq 'secret literal $() & value') 'child gets literal secret'
    Assert-True (Test-OfficeManagedProcess $context $processRecord) 'owned process recognized'
    $recordJson = $processRecord | ConvertTo-Json -Depth 8
    Assert-True (-not $recordJson.Contains('secret literal')) 'record omits environment values'
    $wrongStart = $recordJson | ConvertFrom-Json
    $wrongStart.start_time_utc_ticks = '1'
    Assert-True (-not (Stop-OfficeManagedProcess $context $wrongStart)) 'reused PID refused'
    $wrongExe = $recordJson | ConvertFrom-Json
    $wrongExe.executable = 'C:\unrelated.exe'
    Assert-True (-not (Stop-OfficeManagedProcess $context $wrongExe)) 'wrong executable refused'
    $wrongCommand = $recordJson | ConvertFrom-Json
    $wrongCommand.command_line = 'different project'
    Assert-True (-not (Stop-OfficeManagedProcess $context $wrongCommand)) 'wrong command refused'
    $otherContext = New-OfficeContext -ProjectRoot $root -StateDir $state
    Assert-True (-not (Stop-OfficeManagedProcess $otherContext $processRecord)) 'other project refused'
    Assert-True (Test-OfficeManagedProcess $context $processRecord) 'identity mismatches left process alive'

    $registry = @{scope='heobrain-content-office-windows'; project_root=$context.ProjectRoot; state_dir=$context.StateDir; services=@{fixture=$processRecord}; ports=@{api=18510; frontend=13110}}
    Write-OfficeRegistry $context $registry
    $read = Read-OfficeRegistry $context
    Assert-True ($read.services.fixture.pid -eq $processRecord.pid) 'registry UTF-8 round trips'
    Assert-Throws { Read-OfficeRegistry $otherContext } 'foreign registry rejected'
    Assert-True (Stop-OfficeManagedProcess $context $processRecord) 'exact owned process stopped'
    Assert-True (-not (Test-OfficeManagedProcess $context $processRecord)) 'stopped process no longer owned'
    $processRecord = $null

    # Regression: stopping the recorded supervisor must also stop descendants,
    # including a grandchild. The real worker case also covers spawn children
    # whose commands contain no project path.
    $treeScript = Join-Path $app 'process-tree.py'
    $treePids = Join-Path $app 'tree-pids'
    [IO.Directory]::CreateDirectory($treePids) | Out-Null
    $treeCode = @'
import os,pathlib,subprocess,sys,time
out=pathlib.Path(sys.argv[1])
level=int(sys.argv[2])
if level < 2:
    subprocess.Popen([sys.executable,__file__,str(out),str(level+1)])
(out/str(level)).write_text(str(os.getpid()))
time.sleep(120)
'@
    [IO.File]::WriteAllText($treeScript, $treeCode, [Text.UTF8Encoding]::new($false))
    $processRecord = Start-OfficeManagedProcess -Context $context -Name 'tree' -Executable $PythonPath -ArgumentList @($treeScript,$treePids,'0') -WorkingDirectory $app -Environment @{}
    $treeIdentities = @()
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(10)
        while (-not (Test-Path -LiteralPath (Join-Path $treePids '2')) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
        foreach ($level in 0..2) {
            $identity = Get-OfficeProcessIdentity ([int][IO.File]::ReadAllText((Join-Path $treePids "$level")))
            Assert-True ($null -ne $identity) "tree level $level started"
            $treeIdentities += $identity
        }
        Assert-True (Stop-OfficeManagedProcess $context $processRecord) 'owned process tree stopped'
        foreach ($identity in $treeIdentities) {
            Assert-True ($null -eq (Get-OfficeProcessIdentity $identity.pid)) "tree PID $($identity.pid) has exited"
        }
        Assert-True ($null -ne (Get-Process -Id $PID -ErrorAction SilentlyContinue)) 'unrelated test parent survives tree stop'
        $processRecord = $null
    } finally {
        # Cleanup uses the test's captured identities, including on the red run.
        foreach ($identity in $treeIdentities) {
            $live = Get-OfficeProcessIdentity $identity.pid
            if ($live -and $live.start_time_utc_ticks -ceq $identity.start_time_utc_ticks) {
                $remaining = [Diagnostics.Process]::GetProcessById($identity.pid)
                try { $remaining.Kill(); $remaining.WaitForExit(5000) | Out-Null } finally { $remaining.Dispose() }
            }
        }
    }

    Assert-Throws { Get-OfficeAuthorizedWindow -Python $PythonPath -StateDir $state } 'automation refuses missing database'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $state 'office.sqlite3'))) 'window read does not create database'
    $seed = Join-Path $app 'seed-window.py'
    [IO.File]::WriteAllText($seed, "import json,pathlib,sqlite3,sys`nwith sqlite3.connect(pathlib.Path(sys.argv[1])/'office.sqlite3') as db:`n db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')`n db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',('work_window',json.dumps({'status':'active','authorized_start':'2020-01-01T00:00:00+00:00','authorized_end':'2099-01-01T00:00:00+00:00'})))`n", [Text.UTF8Encoding]::new($false))
    & $PythonPath $seed $state
    Assert-True ($LASTEXITCODE -eq 0) 'window fixture seeded'
    $window = Get-OfficeAuthorizedWindow -Python $PythonPath -StateDir $state
    Assert-True ($window.authorized_end -ceq '2099-01-01T00:00:00+00:00') 'read-only native window lookup works with Unicode state path'

    # Optional full entrypoint lifecycle uses synthetic modules only; no app data,
    # HTTP calls, model calls, approvals, or production services are involved.
    if ($NodePath) {
        $backend = Join-Path $app 'backend'
        $frontend = Join-Path $app 'frontend'
        $fixtureScripts = Join-Path $app 'scripts'
        [IO.Directory]::CreateDirectory((Join-Path $backend 'office')) | Out-Null
        [IO.Directory]::CreateDirectory((Join-Path $frontend 'node_modules\next\dist\bin')) | Out-Null
        [IO.Directory]::CreateDirectory((Join-Path $frontend '.next')) | Out-Null
        [IO.Directory]::CreateDirectory($fixtureScripts) | Out-Null
        & $PythonPath -m venv --without-pip (Join-Path $backend '.venv')
        Assert-True ($LASTEXITCODE -eq 0) 'native disposable venv created'
        [IO.File]::WriteAllText((Join-Path $backend 'uvicorn.py'), "import os,pathlib,time`npathlib.Path('api-process.txt').write_text(str(os.getpid()))`ntime.sleep(120)`n", [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $backend 'office\__init__.py'), '', [Text.UTF8Encoding]::new($false))
        $spawnWorker = @'
import multiprocessing,pathlib,time

def child():
    pathlib.Path('worker-child-started.txt').write_text('spawned')
    time.sleep(120)

def main():
    process = multiprocessing.get_context('spawn').Process(target=child)
    process.start()
    process.join()

if __name__ == '__main__':
    main()
'@
        [IO.File]::WriteAllText((Join-Path $backend 'office\worker.py'), $spawnWorker, [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $fixtureScripts 'watch_window.py'), "import time`ntime.sleep(120)`n", [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $frontend 'node_modules\next\dist\bin\next'), "setTimeout(() => {}, 120000);", [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $frontend '.next\BUILD_ID'), 'synthetic-test-build', [Text.UTF8Encoding]::new($false))
        $start = Join-Path $PSScriptRoot '..\start-windows.ps1'
        $stop = Join-Path $PSScriptRoot '..\stop-windows.ps1'
        $status = Join-Path $PSScriptRoot '..\status-windows.ps1'
        try {
            & $start -ProjectRoot $app -StateDir $state -NodePath $NodePath -ApiPort 28510 -FrontendPort 23110 | Out-Null
            $statuses = @(& $status -ProjectRoot $app -StateDir $state)
            Assert-True ($statuses.Count -eq 2) 'default start launches only API/frontend'
            Assert-True (@($statuses | Where-Object Status -eq 'running-owned').Count -eq 2) 'both default processes have native ownership'
            $first = Read-OfficeRegistry $context
            & $start -ProjectRoot $app -StateDir $state -NodePath $NodePath -ApiPort 28510 -FrontendPort 23110 -Worker -Watcher | Out-Null
            $second = Read-OfficeRegistry $context
            $deadline = [DateTime]::UtcNow.AddSeconds(10)
            $spawnMarker = Join-Path $backend 'worker-child-started.txt'
            while (-not (Test-Path -LiteralPath $spawnMarker) -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 100 }
            Assert-True (Test-Path -LiteralPath $spawnMarker) 'worker launches a real Windows spawn child'
            Assert-True ($first.services.api.pid -eq $second.services.api.pid) 'incremental automation keeps API process'
            Assert-True ($first.services.frontend.pid -eq $second.services.frontend.pid) 'incremental automation keeps frontend process'
            $statuses = @(& $status -ProjectRoot $app -StateDir $state)
            Assert-True (@($statuses | Where-Object Status -eq 'running-owned').Count -eq 4) 'explicit worker/watcher start with saved authorization'
            & $stop -ProjectRoot $app -StateDir $state -Service worker | Out-Null
            $statuses = @(& $status -ProjectRoot $app -StateDir $state)
            Assert-True (@($statuses | Where-Object Status -eq 'running-owned').Count -eq 3) 'targeted stop preserves other managed services'
        } finally { & $stop -ProjectRoot $app -StateDir $state | Out-Null }
        $statuses = @(& $status -ProjectRoot $app -StateDir $state)
        Assert-True (@($statuses | Where-Object Status -eq 'running-owned').Count -eq 0) 'stop all clears all synthetic processes'
        $actualApiId = [int][IO.File]::ReadAllText((Join-Path $backend 'api-process.txt'))
        Assert-True ($null -eq (Get-OfficeProcessIdentity $actualApiId)) 'stop all leaves no native venv Python child running'
    }

    if ($RealProjectRoot) {
        # Real application worker, fresh empty database, zero budget, brief test
        # window. No queued work, provider requests, or production state changes.
        $realState = Join-Path $root 'real-worker-state'
        $realContext = New-OfficeContext -ProjectRoot $RealProjectRoot -StateDir $realState
        $realPython = Join-Path $RealProjectRoot 'backend\.venv\Scripts\python.exe'
        $probe = Join-Path $root 'real-worker-probe.py'
        $probeCode = @'
import datetime,json,pathlib,sys
sys.path.insert(0,sys.argv[1])
from office.store import Store
store=Store(sys.argv[2],budget_krw=0)
if sys.argv[3]=='seed':
    now=datetime.datetime.now(datetime.timezone.utc)
    store.set_setting('work_window',{'status':'active','authorized_start':(now-datetime.timedelta(seconds=1)).isoformat(),'authorized_end':(now+datetime.timedelta(seconds=90)).isoformat()})
with store.connection() as db:
    counts={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('tasks','jobs','costs','approvals')}
print(json.dumps({'status':store.setting('worker_status',{}),'window':store.setting('work_window',{}),'counts':counts}))
'@
        [IO.File]::WriteAllText($probe,$probeCode,[Text.UTF8Encoding]::new($false))
        $backendPath = Join-Path $RealProjectRoot 'backend'
        $before = (& $realPython $probe $backendPath $realState seed) | ConvertFrom-Json
        Assert-True ($LASTEXITCODE -eq 0) 'real worker empty test database seeded'
        $null = Get-OfficeAuthorizedWindow -Python $realPython -StateDir $realState
        $realRecord = $null
        $workerChild = $null
        try {
            $command = Get-OfficeWorkerCommand -ProjectRoot $RealProjectRoot
            $realRecord = Start-OfficeManagedProcess -Context $realContext -Name 'real-worker' -Executable $command.Executable -ArgumentList $command.Arguments -WorkingDirectory $command.Cwd -Environment @{OFFICE_STATE_DIR=$realState;PYTHONUTF8='1';PYTHONIOENCODING='utf-8'}
            $deadline = [DateTime]::UtcNow.AddSeconds(15)
            do {
                $after = (& $realPython $probe $backendPath $realState inspect) | ConvertFrom-Json
                Assert-True ($LASTEXITCODE -eq 0) 'real worker state readable'
                if ($after.status.PSObject.Properties['state'] -and $after.status.state -eq 'online') { break }
                Start-Sleep -Milliseconds 200
            } while ([DateTime]::UtcNow -lt $deadline)
            Assert-True ($after.status.PSObject.Properties['state'] -and $after.status.state -eq 'online') 'real worker Windows spawn child posts online heartbeat'
            Assert-True ($after.status.pid -ne $realRecord.pid) 'real heartbeat comes from supervised child'
            $workerChild = Get-OfficeProcessIdentity $after.status.pid
            Assert-True ($null -ne $workerChild) 'real worker child is alive'
            foreach ($name in 'tasks','jobs','costs','approvals') {
                Assert-True ($after.counts.$name -eq 0) "real worker leaves $name empty"
            }
            Assert-True ($before.window.authorized_end -ceq $after.window.authorized_end) 'real worker does not extend test window'
            Assert-True (Stop-OfficeManagedProcess $realContext $realRecord) 'real worker supervisor tree stopped'
            Assert-True ($null -eq (Get-OfficeProcessIdentity $workerChild.pid)) 'actual worker child exits with supervisor'
            $realRecord = $null
        } finally {
            if ($realRecord) { Stop-OfficeManagedProcess $realContext $realRecord | Out-Null }
        }
        Write-Output 'PASS: real Windows worker spawn, online heartbeat, empty work/cost/approval tables, and complete tree shutdown'
    }

    Write-Output 'PASS: Windows launcher ownership, quoting, environment, window, port, lock and registry behavior'
} finally {
    if ($processRecord) { Stop-OfficeManagedProcess $context $processRecord | Out-Null }
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
