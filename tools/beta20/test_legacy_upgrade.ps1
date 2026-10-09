$ErrorActionPreference='Stop'
if($env:GITHUB_ACTIONS -ne 'true'){throw 'This destructive fixture setup is restricted to an isolated GitHub Windows runner.'}
$target=Join-Path $env:LOCALAPPDATA 'Programs/DocPilot'
$data=Join-Path $env:LOCALAPPDATA 'DocPilot'
$newInstaller=Resolve-Path 'release-package/candidate/Install-DocPilot.ps1'
$hosts=Join-Path $env:SystemRoot 'System32/drivers/etc/hosts'
$originalHosts=[IO.File]::ReadAllBytes($hosts)
$cases=@(
 @{version='v0.1.0-beta.12';sha='e1275234749d2d13f1c24690d9973da87e6d0f0ccc099f51ac7922c4f704becf'},
 @{version='v0.1.0-beta.14';sha='eb1a7d8bc26d7e5bb92731b835e50bd41d1a9339d9e0eb203790380c27292af8'}
)
function Stop-Fixture {
 Get-Process DocPilot -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
 Start-Sleep -Seconds 2
}
function Wait-Version([string]$expected) {
 for($i=0;$i -lt 90;$i++){
  try {
   $status=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/system/update' -TimeoutSec 2
   if($status.current -eq $expected){return}
  } catch {}
  Start-Sleep -Seconds 1
 }
 throw ('Executable did not start on '+$expected)
}
try {
 foreach($case in $cases){
  Stop-Fixture
  # Each case owns a clean, disposable runner profile. Never run on a client PC.
  if(Test-Path $target){Remove-Item $target -Recurse -Force}
  if(Test-Path $data){Remove-Item $data -Recurse -Force}
  $folder=Join-Path $env:RUNNER_TEMP ('compatibility-'+$case.version)
  New-Item -ItemType Directory -Force -Path $folder | Out-Null
  $zip=Join-Path $folder 'old.zip'
  if($case.version -eq 'v0.1.0-beta.12') {Copy-Item 'release-package/beta12.zip' $zip}
  else {Invoke-WebRequest ('https://github.com/aston76/DocPilot-Install/releases/download/'+$case.version+'/DocPilot-Windows-portable.zip') -OutFile $zip}
  if((Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $case.sha){throw 'Legacy archive checksum mismatch'}
  $files=Join-Path $folder 'files';Expand-Archive $zip $files
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $files 'Install-DocPilot.ps1')
  if($LASTEXITCODE -ne 0){throw 'Legacy installer failed'}
  # Keep the real old binary from contacting public releases while preparing its database.
  [IO.File]::AppendAllText($hosts,"`r`n127.0.0.1 api.github.com`r`n",[Text.Encoding]::ASCII)
  Clear-DnsClientCache
  Start-Process (Join-Path $target 'DocPilot.exe') -WorkingDirectory $target -WindowStyle Hidden
  Wait-Version $case.version
  $entity=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/legal-entities' -Method Post -ContentType 'application/json' -Body '{"name":"Compatibility fixture","identifiers":[]}' -TimeoutSec 10
  'keep-local-data' | Set-Content (Join-Path $data 'legacy-data-sentinel.txt')
  'keep-private-profile' | Set-Content (Join-Path $target 'legacy-profile-sentinel.txt')
  $quit=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/system/quit' -Method Post -ContentType 'application/json' -Body '{"quit":true}' -TimeoutSec 10
  if($quit.status -ne 'stopping'){throw 'Legacy graceful shutdown refused'}
  for($i=0;$i -lt 90;$i++){
   $running=@(Get-Process DocPilot -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq (Join-Path $target 'DocPilot.exe')})
   if(-not $running.Count){break};Start-Sleep -Seconds 1
  }
  if($running.Count){
   Write-Output ('Legacy version: '+$case.version+'; processes: '+(($running|Select-Object Id,ProcessName,Path,Responding)|ConvertTo-Json -Compress))
   foreach($log in @('startup.log','runtime.log')){
    $path=Join-Path $data $log
    if(Test-Path $path){Write-Output ('Shutdown diagnostics: '+$log);Get-Content $path -Tail 50}
   }
   try{Write-Output ('API still responding: '+((Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/health' -TimeoutSec 2)|ConvertTo-Json -Compress))}catch{Write-Output 'API no longer responds'}
   throw 'Legacy application did not close gracefully'
  }
  Push-Location $target
  try {
   if($case.version -eq 'v0.1.0-beta.14'){
    # Exercise the actual old updater against the candidate archive and its checksum.
    $oldUpdater=Join-Path $target 'DocPilot-Update.ps1'
    $candidate=Resolve-Path (Join-Path $env:GITHUB_WORKSPACE 'release-package/DocPilot-Windows-portable.zip')
    & powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File $oldUpdater -Mode Install -PortableArchive $candidate -Restart
   } else {
    # beta.12 can require the public bootstrap, bypassing its broken old updater.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $newInstaller
   }
   if($LASTEXITCODE -ne 0){throw 'Direct upgrade failed'}
  } finally {Pop-Location}
  $marker=Get-Content (Join-Path $target 'version.json') -Raw | ConvertFrom-Json
  if($marker.version -ne 'v0.1.0-beta.20'){throw 'Upgraded marker incorrect'}
  if($case.version -eq 'v0.1.0-beta.12'){Start-Process (Join-Path $target 'DocPilot.exe') -WorkingDirectory $target -WindowStyle Hidden}
  Wait-Version 'v0.1.0-beta.20'
  $entities=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/legal-entities' -TimeoutSec 10
  if(-not @($entities | Where-Object {$_.id -eq $entity.id -and $_.name -eq 'Compatibility fixture'}).Count){throw 'Existing database entry lost'}
  if((Get-Content (Join-Path $data 'legacy-data-sentinel.txt')).Trim() -ne 'keep-local-data'){throw 'User data lost'}
  if((Get-Content (Join-Path $target 'legacy-profile-sentinel.txt')).Trim() -ne 'keep-private-profile'){throw 'Private profile lost'}
  $health=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/health' -TimeoutSec 5
  if($health.status -ne 'ok'){throw 'Upgraded API unhealthy'}
  $scanner=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/scanner' -TimeoutSec 5
  if(-not $scanner.supported -or $scanner.running){throw 'Scanner upgrade invalid'}
  [IO.File]::WriteAllBytes($hosts,$originalHosts);Clear-DnsClientCache
  Write-Output ('PASS: actual '+$case.version+' -> beta.20 direct upgrade; real database entry and private files preserved.')
 }
} finally {
 Stop-Fixture
 [IO.File]::WriteAllBytes($hosts,$originalHosts);Clear-DnsClientCache
}
