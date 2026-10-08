# Installe ou met à jour le programme uniquement. Les données restent dans LOCALAPPDATA\DocPilot.
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$target = Join-Path $env:LOCALAPPDATA 'Programs\DocPilot'
$installedExe = Join-Path $target 'DocPilot.exe'
if (-not (Test-Path -LiteralPath (Join-Path $source 'DocPilot.exe'))) { throw 'Extrayez le ZIP complet avant installation.' }

$running = @(Get-Process -Name DocPilot -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $installedExe })
if ($running.Count -gt 0) {
    Write-Host 'Fermeture de DocPilot ; les traitements en cours doivent se terminer...'
    $requestSent = $false
    try {
        $response = Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/system/quit' -Method Post -ContentType 'application/json' -Body '{"quit":true}' -TimeoutSec 10
        $requestSent = $response.status -eq 'stopping'
    } catch {}
    if (-not $requestSent) { throw "Fermez DocPilot avec Quitter, puis relancez l'installation. Aucun fichier du programme n'a été remplacé." }
    foreach ($process in $running) {
        try { Wait-Process -Id $process.Id -Timeout 90 -ErrorAction Stop } catch {
            if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) { throw 'DocPilot termine encore un traitement. Réessayez une fois fermé.' }
        }
    }
}

# Stage and verify the entire program before replacing the installed folder.
# Data lives elsewhere; keep the previous program for rollback.
$parent=Split-Path $target -Parent
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$stage=Join-Path $parent ('DocPilot-stage-'+[Guid]::NewGuid().ToString('N'))
$backup=Join-Path $parent ('DocPilot-backup-'+[Guid]::NewGuid().ToString('N'))
$swapped=$false
try {
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    if(Test-Path -LiteralPath $target){
        Get-ChildItem -LiteralPath $target -Force | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force}
    }
    Get-ChildItem -LiteralPath $source -Force | Where-Object {$_.Name -ne 'Install-DocPilot.ps1'} | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force
    }
    $sourceHash=(Get-FileHash -LiteralPath (Join-Path $source 'DocPilot.exe') -Algorithm SHA256).Hash
    if((Get-FileHash -LiteralPath (Join-Path $stage 'DocPilot.exe') -Algorithm SHA256).Hash -ne $sourceHash){throw 'Vérification du programme échouée.'}
    if(-not (Test-Path -LiteralPath (Join-Path $stage 'web\index.html'))){throw 'Interface absente du paquet.'}
    if(Test-Path -LiteralPath $target){Move-Item -LiteralPath $target -Destination $backup}
    try {Move-Item -LiteralPath $stage -Destination $target;$swapped=$true} catch {
        if(Test-Path -LiteralPath $backup){Move-Item -LiteralPath $backup -Destination $target}
        throw
    }
} finally {
    if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Recurse -Force}
    if($swapped -and (Test-Path -LiteralPath $backup)){Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue}
}
try {
$shell = New-Object -ComObject WScript.Shell
$shortcutPaths = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\DocPilot.lnk'),
    (Join-Path ([Environment]::GetFolderPath('Desktop')) 'DocPilot.lnk')
)
foreach ($shortcutPath in $shortcutPaths) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $installedExe
    $shortcut.WorkingDirectory = $target
    $shortcut.Description = 'DocPilot - classement des documents'
    $icon = Join-Path $target 'assets\docpilot.ico'
    if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = $icon }
    $shortcut.Save()
}
} catch { Write-Warning ('Programme installé ; raccourci indisponible : '+$_.Exception.Message) }
Write-Host "DocPilot installé : $target"
Write-Host 'Lancez DocPilot depuis le Bureau ou le menu Démarrer.'
Write-Host 'Vos documents et informations de connexion sont conservés.'
