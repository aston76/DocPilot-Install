$ErrorActionPreference='Stop'
$script=Resolve-Path 'tools/beta17/DocPilot-Update.ps1'
$archive=Resolve-Path 'release-package/DocPilot-Windows-portable.zip'
$data=Join-Path $env:LOCALAPPDATA 'DocPilot'
$statusFile=Join-Path $data 'update-state.json'
Remove-Item $statusFile -Force -ErrorAction SilentlyContinue
$process=Start-Process powershell.exe -ArgumentList @('-STA','-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$script+'"'),'-Mode','Install','-PortableArchive',('"'+$archive+'"'),'-Restart') -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $data 'native-output.log') -RedirectStandardError (Join-Path $data 'native-error.log')
$null=$process.Handle
if(-not $process.WaitForExit(480000)){ $process.Kill();throw 'Silent update timed out' }
if($process.ExitCode -ne 0){throw (Get-Content (Join-Path $data 'native-error.log') -Raw)}
$state=Get-Content $statusFile -Raw | ConvertFrom-Json
if($state.status -ne 'complete' -or $state.percent -ne 100){throw 'Silent update did not finish'}
if($state.window_handle){throw 'Unexpected progress window'}
$deadline=(Get-Date).AddSeconds(45)
$ready=$false
while((Get-Date) -lt $deadline){
 try {
  $status=Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/system/update' -TimeoutSec 2
  if($status.current -eq 'v0.1.0-beta.17' -and -not $status.available -and $status.status -eq 'current'){$ready=$true;break}
 } catch {}
 Start-Sleep -Milliseconds 500
}
if(-not $ready){throw 'Restarted application did not settle to current'}
Write-Output 'PASS: silent installation, automatic restart, no repeated completion or install offer.'
