param([ValidateSet('Install','Update')][string]$Mode='Install',[switch]$Restart,[string]$PortableArchive,[switch]$ShowProgress)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$target=Join-Path $env:LOCALAPPDATA 'Programs\DocPilot'
$data=Join-Path $env:LOCALAPPDATA 'DocPilot'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$log=Join-Path $data 'updater.log'
$mutex=New-Object Threading.Mutex($false,'Local\DocPilotUpdate')
$owned=$mutex.WaitOne(0)

$temp=Join-Path $env:TEMP ('DocPilot-Update-'+[Guid]::NewGuid().ToString('N'))
$statusFile=Join-Path $data 'update-state.json'
$form=$null
if ($ShowProgress) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form=New-Object Windows.Forms.Form
    $form.Text='Mise à jour de DocPilot';$form.Width=520;$form.Height=230
    $form.StartPosition='CenterScreen';$form.FormBorderStyle='FixedDialog';$form.MaximizeBox=$false;$form.MinimizeBox=$false;$form.ControlBox=$false
    $label=New-Object Windows.Forms.Label;$label.SetBounds(24,24,460,60);$label.Font=New-Object Drawing.Font('Segoe UI',11)
    $bar=New-Object Windows.Forms.ProgressBar;$bar.SetBounds(24,100,460,24);$bar.Style='Marquee'
    $button=New-Object Windows.Forms.Button;$button.Text='OK';$button.SetBounds(384,140,100,32);$button.Enabled=$false
    $button.Add_Click({$form.Close()});$form.Controls.AddRange(@($label,$bar,$button));$form.Show()
}
function Update-Progress([string]$phase,[string]$message,[Nullable[int]]$percent=$null) {
    $payload=@{status=$phase;message=$message;percent=$percent;version=$release.tag_name;updated_at=(Get-Date).ToUniversalTime().ToString('o')}
    $temporary=$statusFile+'.tmp'
    $payload | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $statusFile -Force
    if($form){
        $label.Text=$message
        if($null -eq $percent){$bar.Style='Marquee'}else{$bar.Style='Continuous';$bar.Value=[Math]::Min(100,[Math]::Max(0,$percent))}
        [Windows.Forms.Application]::DoEvents()
    }
}
function Download-Archive([string]$url,[string]$destination) {
    $request=[Net.HttpWebRequest]::Create($url);$request.Timeout=30000;$request.ReadWriteTimeout=30000
    $response=$request.GetResponse();$stream=$response.GetResponseStream();$output=[IO.File]::Create($destination)
    try {
        $buffer=New-Object byte[] (1024*1024);$received=[long]0;$last=[datetime]::MinValue
        while(($count=$stream.Read($buffer,0,$buffer.Length)) -gt 0){
            $output.Write($buffer,0,$count);$received+=$count
            if(((Get-Date)-$last).TotalMilliseconds -ge 200){
                $percent=$null;if($response.ContentLength -gt 0){$percent=[int](100*$received/$response.ContentLength)}
                Update-Progress 'downloading' ('Téléchargement : '+[Math]::Round($received/1MB)+' Mo') $percent
                $last=Get-Date
            }
        }
    } finally {$output.Dispose();$stream.Dispose();$response.Dispose()}
}
function Extract-Archive([string]$archive,[string]$destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    $root=[IO.Path]::GetFullPath($destination).TrimEnd('\')+'\'
    $zipFile=[IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $count=0;$total=$zipFile.Entries.Count
        foreach($entry in $zipFile.Entries){
            $path=[IO.Path]::GetFullPath((Join-Path $destination $entry.FullName))
            if(-not $path.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)){throw 'Chemin invalide dans le paquet.'}
            if($entry.FullName.EndsWith('/')){New-Item -ItemType Directory -Path $path -Force | Out-Null}else{
                New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($path)) -Force | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$path,$true)
            }
            $count++;if($count%20 -eq 0 -or $count -eq $total){Update-Progress 'extracting' ('Préparation : '+$count+' / '+$total+' fichiers') ([int](100*$count/$total))}
        }
    } finally {$zipFile.Dispose()}
}
function Version-Key([string]$tag) {
    if ($tag -notmatch '^v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$') { throw 'Version inconnue.' }
    $beta=1000000
    if ($Matches[4]) { $beta=[int]$Matches[4] }
    return [Version]::new([int]$Matches[1],[int]$Matches[2],[int]$Matches[3],$beta)
}
try {
    if (-not $owned) { throw 'Une mise à jour est déjà en cours.' }
    Update-Progress 'checking' 'Recherche de la dernière version…'
    if($PortableArchive -and $Mode -ne 'Install'){throw 'Le paquet portable est reserve a une installation manuelle.'}
    if(-not $PortableArchive){
    $releases=Invoke-RestMethod 'https://api.github.com/repos/aston76/DocPilot-Install/releases?per_page=20' -TimeoutSec 20
    $release=$releases | Where-Object { -not $_.draft -and $_.tag_name -match '^v?\d+\.\d+\.\d+(?:-beta\.\d+)?$' -and @($_.assets | Where-Object {$_.name -in @('DocPilot-Windows-portable.zip','DocPilot-Windows-portable.zip.sha256')}).Count -eq 2 } | Sort-Object {Version-Key $_.tag_name} -Descending | Select-Object -First 1
    if (-not $release) { throw 'Aucune version complete disponible.' }
    }
    $marker=Join-Path $target 'version.json'
    if (-not $PortableArchive -and (Test-Path -LiteralPath $marker)) {
        $current=(Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json).version
        if ((Version-Key $release.tag_name) -le (Version-Key $current)) { Update-Progress 'current' 'DocPilot est déjà à jour.' 100; if($form){$button.Enabled=$true;while($form.Visible){[Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 100}}; return }
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
        Update-Progress 'downloading' 'Téléchargement de la mise à jour…'
        Download-Archive $archive.browser_download_url $zip
    }
    Update-Progress 'verifying' 'Vérification de l’intégrité du téléchargement…'
    $expected=((Get-Content -LiteralPath $sha -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    if ($expected -notmatch '^[a-f0-9]{64}$' -or (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'SHA-256 incorrect : installation interrompue.' }
    $files=Join-Path $temp 'files'
    Update-Progress 'extracting' 'Préparation des fichiers…'
    Extract-Archive $zip $files
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
        Update-Progress 'waiting' 'Fin des traitements en cours avant installation…'
        $deadline=(Get-Date).AddMinutes(10)
        while ($true) {
            try { $documents=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/documents' -TimeoutSec 5 } catch { throw 'DocPilot ne repond pas : mise a jour differee.' }
            $busy=@($documents | Where-Object {$_.status -in @('NEW','FETCHED','EXTRACTING','EXTRACTED','CLASSIFYING','STORING')})
            if (-not $busy.Count) { break }
            if ((Get-Date) -gt $deadline) { throw 'Traitement en cours : mise a jour differee.' }
            if($form){[Windows.Forms.Application]::DoEvents()};Start-Sleep -Milliseconds 500
        }
    }
    Update-Progress 'installing' 'Installation de la mise à jour. Veuillez patienter…'
    $installer=Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+(Join-Path $files 'Install-DocPilot.ps1')+'"')) -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $data 'installer-output.log') -RedirectStandardError (Join-Path $data 'installer-error.log')
    while(-not $installer.HasExited){if($form){[Windows.Forms.Application]::DoEvents()};Start-Sleep -Milliseconds 100}
    if($installer.ExitCode -ne 0){throw 'Installation interrompue. Vos données sont conservées.'}
    # Only successful installation advances the version marker.
    @{version=$release.tag_name;package_sha256=$expected} | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    Update-Progress 'complete' 'Mise à jour terminée. DocPilot sera relancé après un clic sur OK.' 100
    if($form){$button.Enabled=$true;while($form.Visible){[Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 100}}
    if($ShowProgress){
        $finished=Get-Content -LiteralPath $statusFile -Raw | ConvertFrom-Json
        $finished | Add-Member -NotePropertyName acknowledged -NotePropertyValue $true -Force
        $finished | ConvertTo-Json | Set-Content -LiteralPath $statusFile -Encoding UTF8
    }
    if ($Restart) { Start-Process -FilePath (Join-Path $target 'DocPilot.exe') -WorkingDirectory $target -WindowStyle Hidden }
    Add-Content -LiteralPath $log -Value ((Get-Date -Format o)+' installed '+$release.tag_name)
} catch {
    if($owned){Update-Progress 'error' ('Mise à jour échouée : '+$_.Exception.Message)}else{if($form){$label.Text='Une mise à jour est déjà en cours.'}}
    if($form){$button.Enabled=$true;while($form.Visible){[Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 100}}
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
    if($form){$form.Dispose()}
}
