$ErrorActionPreference='Stop'
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class UpdateWindowProbe {
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr FindWindow(string cls,string title);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr FindWindowEx(IntPtr parent,IntPtr after,string cls,string title);
 [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr window);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr window,uint msg,IntPtr w,IntPtr l);
}
'@
$script=Resolve-Path 'DocPilot-Update.ps1'
$archive=Resolve-Path 'release-package/DocPilot-Windows-portable.zip'
$data=Join-Path $env:LOCALAPPDATA 'DocPilot'
$statusFile=Join-Path $data 'update-state.json'
Remove-Item $statusFile -Force -ErrorAction SilentlyContinue
$process=Start-Process powershell.exe -ArgumentList @('-STA','-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$script+'"'),'-Mode','Install','-PortableArchive',('"'+$archive+'"'),'-ShowProgress','-Restart') -PassThru -RedirectStandardOutput (Join-Path $data 'native-output.log') -RedirectStandardError (Join-Path $data 'native-error.log')
$null=$process.Handle
try {
 $deadline=(Get-Date).AddMinutes(8)
 $complete=$false
 while((Get-Date) -lt $deadline){
  if($process.HasExited){throw ('Updater exited before OK: '+(Get-Content (Join-Path $data 'native-error.log') -Raw))}
  try {$state=Get-Content $statusFile -Raw | ConvertFrom-Json} catch {$state=$null}
  if($state.status -eq 'error'){throw $state.message}
  if($state.status -eq 'complete'){$complete=$true;break}
  Start-Sleep -Milliseconds 250
 }
 if(-not $complete -or $state.percent -ne 100){throw 'Native window never completed'}
 $window=[UpdateWindowProbe]::FindWindow($null,'Mise à jour de DocPilot')
 if($window -eq [IntPtr]::Zero){throw 'Completion window missing'}
 $button=[UpdateWindowProbe]::FindWindowEx($window,[IntPtr]::Zero,$null,'OK')
 for($i=0;$i -lt 20 -and ($button -eq [IntPtr]::Zero -or -not [UpdateWindowProbe]::IsWindowEnabled($button));$i++){Start-Sleep -Milliseconds 250;$button=[UpdateWindowProbe]::FindWindowEx($window,[IntPtr]::Zero,$null,'OK')}
 if($button -eq [IntPtr]::Zero -or -not [UpdateWindowProbe]::IsWindowEnabled($button)){throw 'OK button unavailable'}
 if($process.HasExited){throw 'Updater closed before acknowledgement'}
 [void][UpdateWindowProbe]::SendMessage($button,0x00F5,[IntPtr]::Zero,[IntPtr]::Zero)
 if(-not $process.WaitForExit(30000)){throw 'Updater did not close after OK'}
 if($process.ExitCode -ne 0){throw 'Native update failed'}
 $finished=Get-Content $statusFile -Raw | ConvertFrom-Json
 if(-not $finished.acknowledged){throw 'Acknowledgement not persisted'}
 $ready=$false
 for($i=0;$i -lt 60;$i++){
  try {
   $health=Invoke-RestMethod http://127.0.0.1:8765/api/v1/health -TimeoutSec 2
   if($health.status -eq 'ok'){$ready=$true;break}
  }catch{}
  Start-Sleep -Seconds 1
 }
 if(-not $ready){throw 'DocPilot did not restart after OK'}
 $version=Invoke-RestMethod http://127.0.0.1:8765/api/v1/system/update -TimeoutSec 5
 if($version.current -ne 'v0.1.0-beta.13' -or $version.status -eq 'complete'){throw 'Restarted version or completion acknowledgement incorrect'}
 Write-Host 'PASS: native completion window, enabled OK, persisted acknowledgement and automatic restart.'
} finally {
 Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
 Get-Process DocPilot -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
