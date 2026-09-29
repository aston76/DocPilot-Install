# Installe DocPilot pour l'utilisateur Windows courant, sans droits administrateur.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$release = Invoke-RestMethod 'https://api.github.com/repos/aston76/DocPilot-Install/releases/latest'
$archive = $release.assets | Where-Object { $_.name -eq 'DocPilot-Windows-portable.zip' } | Select-Object -First 1
$checksum = $release.assets | Where-Object { $_.name -eq 'DocPilot-Windows-portable.zip.sha256' } | Select-Object -First 1
if (-not $archive -or -not $checksum) { throw 'Version Windows ou empreinte introuvable sur GitHub.' }
$temp = Join-Path $env:TEMP ("DocPilot-Install-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $zip = Join-Path $temp 'DocPilot-Windows-portable.zip'
    $shaFile = Join-Path $temp 'DocPilot-Windows-portable.zip.sha256'
    Write-Host 'Téléchargement de DocPilot depuis GitHub…'
    Invoke-WebRequest $archive.browser_download_url -OutFile $zip
    Invoke-WebRequest $checksum.browser_download_url -OutFile $shaFile
    $expected = ((Get-Content $shaFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -notmatch '^[0-9a-f]{64}$' -or $actual -ne $expected) { throw 'Empreinte SHA-256 incorrecte : installation interrompue.' }
    $folder = Join-Path $temp 'files'
    Expand-Archive $zip -DestinationPath $folder
    $installer = Join-Path $folder 'Install-DocPilot.ps1'
    if (-not (Test-Path $installer)) { throw 'Le script d’installation manque dans le paquet.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
    if ($LASTEXITCODE -ne 0) { throw "Installation échouée (code $LASTEXITCODE)." }
    Write-Host 'Installation terminée. Lancez DocPilot depuis le menu Démarrer.'
} finally {
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}
