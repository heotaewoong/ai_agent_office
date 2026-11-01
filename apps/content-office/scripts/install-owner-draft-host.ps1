param([switch]$Register, [switch]$Unregister)
$ErrorActionPreference='Stop'
$extensionId='cmmaecbhnkhbbpnkfkhnihbmboacolhm'
$target='C:\AI-Office\owner-social-agent'
$runtime=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$key='HKCU:\Software\Google\Chrome\NativeMessagingHosts\kr.heobrain.owner_drafts'
if($Unregister){if(Test-Path -LiteralPath $key){Remove-Item -LiteralPath $key};Write-Output '본인 계정의 연결 등록만 해제했습니다. 인증·원본 파일은 보존합니다.';exit}
if(!(Test-Path -LiteralPath (Join-Path $target 'owner_agent.py')) -or !(Test-Path -LiteralPath $runtime)){throw '기존 Windows 인증 실행기와 Python을 확인하세요.'}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'owner-draft-host.py') -Destination (Join-Path $target 'draft_host.py')
$extension=Join-Path $target 'draft-extension'
New-Item -ItemType Directory -Path $extension -Force | Out-Null
Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'owner-draft-extension') -File | Where-Object Name -NotMatch '\.test\.mjs$' | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $extension $_.Name)}
$launcher='@echo off'+"`r`n"+'"'+$runtime+'" -I -u "'+(Join-Path $target 'draft_host.py')+'"'+"`r`n"
[IO.File]::WriteAllText((Join-Path $target 'draft_host.cmd'),$launcher,[Text.Encoding]::ASCII)
$manifest=[ordered]@{name='kr.heobrain.owner_drafts';description='HeoBrain private/draft only owner-PC host';path=(Join-Path $target 'draft_host.cmd');type='stdio';allowed_origins=@("chrome-extension://$extensionId/")}
[IO.File]::WriteAllText((Join-Path $target 'native-host.json'),($manifest | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
if($Register){New-Item -Path $key -Force | Out-Null;Set-Item -LiteralPath $key -Value (Join-Path $target 'native-host.json')}
Write-Output "Chrome 확장 폴더: $extension"
Write-Output "허용 확장 ID: $extensionId"
Write-Output "본인 Windows 계정 등록: $($Register.IsPresent)"
Write-Output 'Chrome에 자동 설치하거나 권한을 확대하지 않았습니다. 검토 후 직접 확장을 로드하세요.'
