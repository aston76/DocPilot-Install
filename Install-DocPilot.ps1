param([string]$RecoverBackup)
# Installe ou met à jour le programme uniquement. Les données restent dans LOCALAPPDATA\DocPilot.
function File-Sha256([string]$path) {
    $algorithm=[Security.Cryptography.SHA256]::Create()
    $stream=[IO.File]::OpenRead($path)
    try {return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant()}
    finally {$stream.Dispose();$algorithm.Dispose()}
}
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$target = Join-Path $env:LOCALAPPDATA 'Programs\DocPilot'
if(Test-Path -LiteralPath $target){$target=(Get-Item -LiteralPath $target).FullName}
$installedExe = Join-Path $target 'DocPilot.exe'
if (-not (Test-Path -LiteralPath (Join-Path $source 'DocPilot.exe'))) { throw 'Extrayez le ZIP complet avant installation.' }

function Get-InstalledProcesses {
    # CIM also sees the one-file bootloader and its child; never trust a stale snapshot.
    @(Get-CimInstance Win32_Process -Filter "Name = 'DocPilot.exe'" | Where-Object {
        if (-not $_.ExecutablePath) { throw 'Impossible de vérifier un processus DocPilot. Fermez-le puis réessayez.' }
        [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($installedExe)
    })
}
$running = @(Get-InstalledProcesses)
if ($running.Count -gt 0) {
    Write-Host 'Fermeture de DocPilot ; les traitements en cours doivent se terminer...'
    try {
        $response = Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/system/quit' -Method Post -ContentType 'application/json' -Body '{"quit":true}' -TimeoutSec 10
        if ($response.status -ne 'stopping') { throw 'Arrêt non confirmé.' }
    } catch { throw "Fermez DocPilot avec Quitter, puis relancez l'installation. Aucun fichier du programme n'a été remplacé. $($_.Exception.Message)" }
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 250
        $running = @(Get-InstalledProcesses)
        if ([DateTime]::UtcNow -ge $deadline -and $running.Count -gt 0) { throw 'DocPilot termine encore un traitement. Réessayez une fois fermé.' }
    } while ($running.Count -gt 0)
}

# Stage and verify the entire program before replacing the installed folder.
# Data lives elsewhere; keep the previous program for rollback.
$parent=Split-Path $target -Parent
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$parent=(Get-Item -LiteralPath $parent).FullName
$target=Join-Path $parent 'DocPilot'
$stage=Join-Path $parent ('DocPilot-stage-'+[Guid]::NewGuid().ToString('N'))
$backup=Join-Path $parent ('DocPilot-backup-'+[Guid]::NewGuid().ToString('N'))
$replaced=New-Object 'System.Collections.Generic.List[object]'
function Invoke-FileOperation([scriptblock]$operation) {
    for($attempt=0;$attempt -lt 40;$attempt++) {
        try { & $operation; return }
        catch {if($attempt -eq 39){throw};Start-Sleep -Milliseconds 250}
    }
}
function Restore-Program([string]$backupPath, $entries) {
    $failed=$false
    foreach($entry in @($entries | Sort-Object -Property order -Descending)) {
        $relative=[string]$entry.path
        $destination=[IO.Path]::GetFullPath((Join-Path $target $relative))
        if(-not $destination.StartsWith($target.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Chemin de restauration invalide.'}
        $saved=Join-Path $backupPath $relative
        try {
            if(Test-Path -LiteralPath $saved) {
                Invoke-FileOperation {
                    if(Test-Path -LiteralPath $destination){[IO.File]::Replace($saved,$destination,[NullString]::Value)}
                    else {[IO.File]::Move($saved,$destination)}
                }
            } elseif(-not $entry.existed -and (Test-Path -LiteralPath $destination)) {
                Invoke-FileOperation { [IO.File]::Delete($destination) }
            }
        } catch {$failed=$true;Write-Warning ('Restauration à terminer : '+$destination)}
    }
    return (-not $failed)
}
if($RecoverBackup) {
    $RecoverBackup=(Get-Item -LiteralPath $RecoverBackup).FullName
    if((Split-Path $RecoverBackup -Parent) -ne $parent -or (Split-Path $RecoverBackup -Leaf) -notmatch '^DocPilot-backup-[0-9a-f]{32}$'){throw 'Dossier de sauvegarde invalide.'}
    $journal=Get-Content -LiteralPath (Join-Path $RecoverBackup 'recovery.json') -Raw | ConvertFrom-Json
    if(-not (Restore-Program $RecoverBackup $journal)){throw "Restauration incomplète. Sauvegarde conservée : $RecoverBackup"}
    Remove-Item -LiteralPath $RecoverBackup -Recurse -Force
    Write-Host 'Programme précédent restauré.'
    return
}
try {
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $stage=(Get-Item -LiteralPath $stage).FullName
    Get-ChildItem -LiteralPath $source -Force | Where-Object {$_.Name -ne 'Install-DocPilot.ps1'} | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force
    }
    $sourceHash=(File-Sha256 (Join-Path $source 'DocPilot.exe'))
    if((File-Sha256 (Join-Path $stage 'DocPilot.exe')) -ne $sourceHash){throw 'Vérification du programme échouée.'}
    if(-not (Test-Path -LiteralPath (Join-Path $stage 'web\index.html'))){throw 'Interface absente du paquet.'}
    New-Item -ItemType Directory -Force -Path $target,$backup | Out-Null
    $files=@(Get-ChildItem -LiteralPath $stage -Recurse -File -Force | Sort-Object FullName)
    $plan=New-Object 'System.Collections.Generic.List[object]'
    # Reject existing locks before changing any file. Atomic replacement remains the final guard.
    foreach($file in $files) {
        $destination=Join-Path $target $file.FullName.Substring($stage.Length+1)
        $existed=Test-Path -LiteralPath $destination
        $plan.Add([pscustomobject]@{path=$file.FullName.Substring($stage.Length+1);existed=$existed;order=$plan.Count})
        if($existed) {
            Invoke-FileOperation { $handle=[IO.File]::Open($destination,'Open','ReadWrite','None');$handle.Dispose() }
        }
    }
    if(@(Get-InstalledProcesses).Count -gt 0){throw 'DocPilot a redémarré. Aucun fichier remplacé.'}
    # Persist the complete plan once: the package contains thousands of files.
    # A saved file proves that its atomic replacement committed; otherwise old files stay untouched.
    ConvertTo-Json -InputObject @($plan.ToArray()) | Set-Content -LiteralPath (Join-Path $backup 'recovery.json') -Encoding UTF8
    Write-Host ('Remplacement de '+$files.Count+' fichiers du programme...')
    # Keep the root directory stable: an old updater can still use it as its cwd.
    # Replace only package files; unrelated private files remain untouched.
    foreach($file in $files) {
        $relative=$file.FullName.Substring($stage.Length+1)
        $destination=Join-Path $target $relative
        $saved=Join-Path $backup $relative
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($saved))
        $existed=Test-Path -LiteralPath $destination
        $replaced.Add([pscustomobject]@{path=$relative;existed=$existed;order=$replaced.Count})
        Invoke-FileOperation {
            if($existed){[IO.File]::Replace($file.FullName,$destination,$saved)}
            else {[IO.File]::Move($file.FullName,$destination)}
        }
    }
} catch {
    $failure=$_
    if(-not (Restore-Program $backup $replaced.ToArray())){throw ('Installation interrompue. Sauvegarde conservée dans '+$backup+'. Relancez ce script avec -RecoverBackup "'+$backup+'". '+$failure.Exception.Message)}
    if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Recurse -Force}
    throw $failure
} finally {
    if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue}
}
if(Test-Path -LiteralPath $backup){Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue}

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
