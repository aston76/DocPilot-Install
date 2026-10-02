# Installe DocPilot pour l'utilisateur Windows courant, sans droits administrateur.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$releases = Invoke-RestMethod 'https://api.github.com/repos/aston76/DocPilot-Install/releases?per_page=20'
$release = $releases | Where-Object { -not $_.draft } | Select-Object -First 1
if (-not $release) { throw 'Aucune version Windows publiee sur GitHub.' }
$archive = $release.assets | Where-Object { $_.name -eq 'DocPilot-Windows-portable.zip' } | Select-Object -First 1
$checksum = $release.assets | Where-Object { $_.name -eq 'DocPilot-Windows-portable.zip.sha256' } | Select-Object -First 1
if (-not $archive -or -not $checksum) { throw 'Version Windows ou empreinte introuvable sur GitHub.' }
$temp = Join-Path $env:TEMP ("DocPilot-Install-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    $zip = Join-Path $temp 'DocPilot-Windows-portable.zip'
    $shaFile = Join-Path $temp 'DocPilot-Windows-portable.zip.sha256'
    Write-Host 'Telechargement de DocPilot depuis GitHub...'
    Invoke-WebRequest $archive.browser_download_url -OutFile $zip
    Invoke-WebRequest $checksum.browser_download_url -OutFile $shaFile
    $expected = ((Get-Content $shaFile -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($expected -notmatch '^[0-9a-f]{64}$' -or $actual -ne $expected) { throw 'Empreinte SHA-256 incorrecte : installation interrompue.' }
    $folder = Join-Path $temp 'files'
    Expand-Archive $zip -DestinationPath $folder
    $installer = Join-Path $folder 'Install-DocPilot.ps1'
    if (-not (Test-Path $installer)) { throw 'Le script d installation manque dans le paquet.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer
    if ($LASTEXITCODE -ne 0) { throw "Installation echouee (code $LASTEXITCODE)." }
    Write-Host 'Installation terminee. Lancez DocPilot depuis le menu Demarrer.'
} finally {
    $resolvedTemp = [IO.Path]::GetFullPath($temp)
    $allowedTemp = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    if ($resolvedTemp.StartsWith($allowedTemp, [StringComparison]::OrdinalIgnoreCase) -and
        ([IO.Path]::GetFileName($resolvedTemp) -like 'DocPilot-Install-*')) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
