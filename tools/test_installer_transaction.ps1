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
    Write-Host 'PASS: lock preflight, atomic replacement, retained recovery, resumed recovery and private data'
} finally {
    $env:LOCALAPPDATA=$originalLocal
    $env:APPDATA=$originalApp
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
