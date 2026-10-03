param([string]$NasRoot)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
# Keep this portable file with DocPilot-Update.ps1 and the optional private profile.
$updater=Join-Path $PSScriptRoot 'DocPilot-Update.ps1'
if (-not (Test-Path -LiteralPath $updater)) {
    $updater=Join-Path $env:TEMP ('DocPilot-Update-'+[Guid]::NewGuid().ToString('N')+'.ps1')
    Invoke-WebRequest 'https://raw.githubusercontent.com/aston76/DocPilot-Install/main/DocPilot-Update.ps1' -OutFile $updater -TimeoutSec 30
}
$portable=Join-Path $PSScriptRoot 'DocPilot-Windows-portable.zip'
if(Test-Path -LiteralPath $portable){& $updater -Mode Install -PortableArchive $portable}else{& $updater -Mode Install}
$profile=Join-Path $PSScriptRoot 'deployment-profile\Importer-Profil-DocPilot.ps1'
if(Test-Path -LiteralPath $profile){
    if($NasRoot){& $profile -NasRoot $NasRoot}else{& $profile}
}
Write-Host 'Installation terminee. Lancez DocPilot depuis le Bureau.'
