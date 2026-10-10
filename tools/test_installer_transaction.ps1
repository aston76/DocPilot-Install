$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot
$root=Join-Path $env:TEMP ('DocPilot-transaction-test-'+[Guid]::NewGuid().ToString('N'))
$originalLocal=$env:LOCALAPPDATA
$originalApp=$env:APPDATA
function Assert([bool]$condition,[string]$message){if(-not $condition){throw $message}}
try {
    $env:LOCALAPPDATA=Join-Path $root 'local'
    $env:APPDATA=Join-Path $root 'roaming'
    $package=Join-Path $root 'package'
    $target=Join-Path $env:LOCALAPPDATA 'Programs\DocPilot'
    New-Item -ItemType Directory -Force -Path $package,$target,(Join-Path $package 'web') | Out-Null
    Copy-Item (Join-Path $repo 'Install-DocPilot.ps1') $package
    Set-Content (Join-Path $package 'DocPilot.exe') 'new-executable'
    Set-Content (Join-Path $package 'web\index.html') 'new-web'
    Set-Content (Join-Path $target 'DocPilot.exe') 'old-executable'
    Set-Content (Join-Path $target 'private.txt') 'keep-private'
    $data=Join-Path $env:LOCALAPPDATA 'DocPilot'
    New-Item -ItemType Directory $data | Out-Null
    Set-Content (Join-Path $data 'document.txt') 'keep-document'
    # Synthetic package: never inspect or close the user's real processes.
    function Get-CimInstance { @() }
    function New-Object {
        param([string]$TypeName,[string]$ComObject)
        if($ComObject){throw 'Synthetic test skips shell shortcuts'}
        Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName
    }
    $installer=Join-Path $package 'Install-DocPilot.ps1'
    $locked=[IO.File]::Open((Join-Path $target 'DocPilot.exe'),'Open','Read','None')
    try {
        $failed=$false
        try { & $installer } catch {$failed=$true}
        Assert $failed 'Locked destination must fail before mutation'
    } finally {$locked.Dispose()}
    Assert ((Get-Content (Join-Path $target 'DocPilot.exe') -Raw).Trim() -eq 'old-executable') 'Lock failure changed executable'
    Assert (@(Get-ChildItem (Split-Path $target) -Filter 'DocPilot-backup-*').Count -eq 0) 'Preflight left a backup'
    & $installer
    Assert ((Get-Content (Join-Path $target 'DocPilot.exe') -Raw).Trim() -eq 'new-executable') 'Successful replacement failed'
    Assert ((Get-Content (Join-Path $target 'private.txt') -Raw).Trim() -eq 'keep-private') 'Private file changed'
    Assert ((Get-Content (Join-Path $data 'document.txt') -Raw).Trim() -eq 'keep-document') 'Data changed'
    # Acquire a lock after preflight, after the installer rechecks process state.
    # DocPilot.exe sorts before web/index.html, so this exercises partial rollback.
    Set-Content (Join-Path $package 'DocPilot.exe') 'third-executable'
    $script:queries=0
    $script:lateLock=$null
    function Get-CimInstance {
        $script:queries++
        if($script:queries -eq 2){$script:lateLock=[IO.File]::Open((Join-Path $target 'web\index.html'),'Open','Read','None')}
        @()
    }
    try {
        $failed=$false
        try { & $installer } catch {$failed=$true}
        Assert $failed 'Late lock must fail replacement'
    } finally {if($script:lateLock){$script:lateLock.Dispose()}}
    Assert ((Get-Content (Join-Path $target 'DocPilot.exe') -Raw).Trim() -eq 'new-executable') 'Partial rollback did not restore executable'
    Assert (@(Get-ChildItem (Split-Path $target) -Filter 'DocPilot-backup-*').Count -eq 0) 'Successful rollback left backup'
    function Get-CimInstance { @() }
    # Simulate an interrupted rollback: backup + durable journal, current file locked.
    $backup=Join-Path (Split-Path $target) ('DocPilot-backup-'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $backup | Out-Null
    Set-Content (Join-Path $backup 'DocPilot.exe') 'old-executable'
    '[{"path":"DocPilot.exe","existed":true,"order":0}]' | Set-Content (Join-Path $backup 'recovery.json')
    $locked=[IO.File]::Open((Join-Path $target 'DocPilot.exe'),'Open','Read','None')
    try {
        $failed=$false
        try { & $installer -RecoverBackup $backup } catch {$failed=$true}
        Assert $failed 'Locked recovery should fail'
        Assert (Test-Path (Join-Path $backup 'DocPilot.exe')) 'Failed recovery lost backup'
    } finally {$locked.Dispose()}
    & $installer -RecoverBackup $backup
    Assert ((Get-Content (Join-Path $target 'DocPilot.exe') -Raw).Trim() -eq 'old-executable') 'Recovery failed'
    Assert (-not (Test-Path $backup)) 'Completed recovery left backup'
    # Pre-journal backups do not prove which new files were introduced.
    # Reject without mutating either tree; never guess a rollback manifest.
    $legacy=Join-Path (Split-Path $target) ('DocPilot-backup-'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory $legacy | Out-Null
    Set-Content (Join-Path $legacy 'DocPilot.exe') 'legacy-executable'
    $failed=$false
    try { & $installer -RecoverBackup $legacy } catch {$failed=$true}
    Assert $failed 'Legacy backup must require an explicit recovery plan'
    Assert ((Get-Content (Join-Path $legacy 'DocPilot.exe') -Raw).Trim() -eq 'legacy-executable') 'Legacy backup changed'
    Assert ((Get-Content (Join-Path $target 'DocPilot.exe') -Raw).Trim() -eq 'old-executable') 'Legacy recovery changed installed program'
    Remove-Item -LiteralPath (Join-Path $target 'DocPilot.exe')
    & $installer
    Assert ((Get-Content (Join-Path $target 'DocPilot.exe') -Raw).Trim() -eq 'third-executable') 'Full reinstall did not recover missing executable'
    Assert ((Get-Content (Join-Path $legacy 'DocPilot.exe') -Raw).Trim() -eq 'legacy-executable') 'Full reinstall changed legacy backup'
    Assert ((Get-Content (Join-Path $data 'document.txt') -Raw).Trim() -eq 'keep-document') 'Recovery reinstall changed data'
    Write-Host 'PASS: legacy backup is preserved without guessing; full reinstall recovers missing executable; lock preflight, atomic replacement, retained recovery, resumed recovery and private data'
} finally {
    $env:LOCALAPPDATA=$originalLocal
    $env:APPDATA=$originalApp
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
