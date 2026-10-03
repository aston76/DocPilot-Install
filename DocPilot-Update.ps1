param([ValidateSet('Install','Update')][string]$Mode='Install',[switch]$Restart,[string]$PortableArchive)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$target=Join-Path $env:LOCALAPPDATA 'Programs\DocPilot'
$data=Join-Path $env:LOCALAPPDATA 'DocPilot'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$log=Join-Path $data 'updater.log'
$mutex=New-Object Threading.Mutex($false,'Local\DocPilotUpdate')
$owned=$mutex.WaitOne(0)
if (-not $owned) { throw 'Une mise a jour est deja en cours.' }
$temp=Join-Path $env:TEMP ('DocPilot-Update-'+[Guid]::NewGuid().ToString('N'))
function Version-Key([string]$tag) {
    if ($tag -notmatch '^v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$') { throw 'Version inconnue.' }
    $beta=1000000
    if ($Matches[4]) { $beta=[int]$Matches[4] }
    return [Version]::new([int]$Matches[1],[int]$Matches[2],[int]$Matches[3],$beta)
}
try {
    if($PortableArchive -and $Mode -ne 'Install'){throw 'Le paquet portable est reserve a une installation manuelle.'}
    if(-not $PortableArchive){
    $releases=Invoke-RestMethod 'https://api.github.com/repos/aston76/DocPilot-Install/releases?per_page=20' -TimeoutSec 20
    $release=$releases | Where-Object { -not $_.draft -and $_.tag_name -match '^v?\d+\.\d+\.\d+(?:-beta\.\d+)?$' -and @($_.assets | Where-Object {$_.name -in @('DocPilot-Windows-portable.zip','DocPilot-Windows-portable.zip.sha256')}).Count -eq 2 } | Sort-Object {Version-Key $_.tag_name} -Descending | Select-Object -First 1
    if (-not $release) { throw 'Aucune version complete disponible.' }
    }
    $marker=Join-Path $target 'version.json'
    if (-not $PortableArchive -and (Test-Path -LiteralPath $marker)) {
        $current=(Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).version
        if ((Version-Key $release.tag_name) -le (Version-Key $current)) { return }
    }
    if(-not $PortableArchive){
    $archive=$release.assets | Where-Object {$_.name -eq 'DocPilot-Windows-portable.zip'} | Select-Object -First 1
    $checksum=$release.assets | Where-Object {$_.name -eq 'DocPilot-Windows-portable.zip.sha256'} | Select-Object -First 1
    $expectedPrefix='https://github.com/aston76/DocPilot-Install/releases/download/'
    if (-not $archive.browser_download_url.StartsWith($expectedPrefix) -or -not $checksum.browser_download_url.StartsWith($expectedPrefix)) { throw 'Source de mise a jour refusee.' }
    }
    New-Item -ItemType Directory -Path $temp | Out-Null
    $zip=Join-Path $temp 'DocPilot-Windows-portable.zip'
    $sha=Join-Path $temp 'checksum.sha256'
    if($PortableArchive){
        Copy-Item -LiteralPath $PortableArchive -Destination $zip
        Copy-Item -LiteralPath ($PortableArchive+'.sha256') -Destination $sha
    }else{
        Invoke-WebRequest $checksum.browser_download_url -OutFile $sha -TimeoutSec 60
        Invoke-WebRequest $archive.browser_download_url -OutFile $zip -TimeoutSec 900
    }
    $expected=((Get-Content -LiteralPath $sha -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    if ($expected -notmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'SHA-256 incorrect : installation interrompue.' }
    $files=Join-Path $temp 'files'
    Expand-Archive -LiteralPath $zip -DestinationPath $files
    if($PortableArchive){
        $release=[PSCustomObject]@{tag_name=(Get-Content -LiteralPath (Join-Path $files 'version.json') -Raw | ConvertFrom-Json).version}
        [void](Version-Key $release.tag_name)
        if(Test-Path -LiteralPath $marker){
            $current=(Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).version
            if((Version-Key $release.tag_name) -lt (Version-Key $current)){throw 'Ce paquet est plus ancien que la version installee.'}
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $files 'Install-DocPilot.ps1'))) { throw 'Installateur absent.' }
    # A pending scan/classification must finish before closing the application.
    if ($Mode -eq 'Update') {
        $deadline=(Get-Date).AddMinutes(10)
        while ($true) {
            try { $documents=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/documents' -TimeoutSec 5 } catch { throw 'DocPilot ne repond pas : mise a jour differee.' }
            $busy=@($documents | Where-Object {$_.status -in @('NEW','FETCHED','EXTRACTING','EXTRACTED','CLASSIFYING','STORING')})
            if (-not $busy.Count) { break }
            if ((Get-Date) -gt $deadline) { throw 'Traitement en cours : mise a jour differee.' }
            Start-Sleep -Seconds 5
        }
    }
    & (Join-Path $files 'Install-DocPilot.ps1')
    # Only successful installation advances the version marker.
    @{version=$release.tag_name;package_sha256=$expected} | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    if ($Restart) { Start-Process -FilePath (Join-Path $target 'DocPilot.exe') -WorkingDirectory $target -WindowStyle Hidden }
    Add-Content -LiteralPath $log -Value ((Get-Date -Format o)+' installed '+$release.tag_name)
} catch {
    Add-Content -LiteralPath $log -Value ((Get-Date -Format o)+' '+$_.Exception.Message)
    throw
} finally {
    if (Test-Path -LiteralPath $temp) {
        $resolved=[IO.Path]::GetFullPath($temp)
        $allowed=[IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')+'\'
        if ($resolved.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolved) -like 'DocPilot-Update-*') { Remove-Item -LiteralPath $resolved -Recurse -Force }
    }
    if ($owned) {$mutex.ReleaseMutex()}
    $mutex.Dispose()
}
