param([Parameter(Mandatory=$true)][string]$Candidate)
$ErrorActionPreference='Stop'
$Candidate=(Resolve-Path $Candidate).Path
$process=Start-Process (Join-Path $Candidate 'DocPilot.exe') -WorkingDirectory $Candidate -PassThru -WindowStyle Hidden
try {
    $healthy=$false
    for($i=0;$i -lt 60;$i++){
        try {$health=Invoke-RestMethod http://127.0.0.1:8765/api/v1/health -TimeoutSec 2;if($health.status -eq 'ok'){$healthy=$true;break}}catch{}
        Start-Sleep -Seconds 1
    }
    if(-not $healthy){throw 'Packaged app failed to start for archive regression'}
$nas = Join-Path $env:RUNNER_TEMP 'DocPilot-SHA\Example\Fournisseurs-Créanciers'
New-Item -ItemType Directory -Path (Join-Path $nas 'Factures') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $nas 'Contrats') -Force | Out-Null
$file = Join-Path $nas 'Factures\test.pdf'
[IO.File]::WriteAllBytes($file, [Text.Encoding]::ASCII.GetBytes('%PDF-SHA-test'))
$expected = (Get-FileHash $file -Algorithm SHA256).Hash
$body = @{root=$nas} | ConvertTo-Json -Compress
$chosen = Invoke-RestMethod http://127.0.0.1:8765/api/v1/workspace/select -Method Post -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 40
if (-not $chosen.ready) { throw 'Test archive not selected' }
for ($i = 0; $i -lt 30; $i++) {
  $sha = Invoke-RestMethod http://127.0.0.1:8765/api/v1/archive/sha256 -TimeoutSec 5
  if ($sha.phase -eq 'complete') { break }
  Start-Sleep -Seconds 1
}
if ($sha.phase -ne 'complete' -or $sha.indexed_files -ne 1 -or $sha.percent -ne 100) { throw ('Automatic SHA scan failed after workspace verification: '+($sha | ConvertTo-Json -Depth 6 -Compress)) }
if ((Get-FileHash $file -Algorithm SHA256).Hash -ne $expected) { throw 'SHA scan changed an archive file' }
for($n=0;$n -lt 36;$n++){New-Item -ItemType Directory -Path (Join-Path $nas ('Factures\Recovery '+$n+'\2026')) -Force | Out-Null}
Invoke-RestMethod http://127.0.0.1:8765/api/v1/catalogue-directory -Method Post -TimeoutSec 5 | Out-Null
for($i=0;$i -lt 30;$i++){
  $catalogue=Invoke-RestMethod http://127.0.0.1:8765/api/v1/catalogue-directory -TimeoutSec 5
  if(-not $catalogue.running){break}
  Start-Sleep -Seconds 1
}
if($catalogue.status -ne 'complete' -or $catalogue.discovered -ne 36){throw ('Packaged catalogue recovery failed: '+($catalogue|ConvertTo-Json -Compress))}
$entities=Invoke-RestMethod http://127.0.0.1:8765/api/v1/legal-entities -TimeoutSec 5
$recovered=@($entities | Where-Object {$_.name -like 'Recovery *'}).Count
if($recovered -ne 36){throw ('Recovered directory rows missing from real packaged API. Count: '+$recovered+'. Response: '+($entities|ConvertTo-Json -Depth 5 -Compress))}

$second = Join-Path $nas 'Factures\second.pdf'
[IO.File]::WriteAllBytes($second,[Text.Encoding]::ASCII.GetBytes('%PDF-second'))
$found=$false
for($i=0;$i -lt 30;$i++){
  $sha=Invoke-RestMethod http://127.0.0.1:8765/api/v1/archive/sha256 -TimeoutSec 5
  if($sha.phase -eq 'complete' -and $sha.indexed_files -eq 2){$found=$true;break}
  Start-Sleep -Seconds 1
}
if(-not $found){throw 'Native change notification did not index the new file'}
if(-not (Test-Path (Join-Path $nas 'DocPilot-Partage\v1'))){throw 'Shared index not published'}
    Invoke-RestMethod http://127.0.0.1:8765/api/v1/system/quit -Method Post -ContentType 'application/json' -Body '{"quit":true}' -TimeoutSec 10 | Out-Null
    $closed=$false
    for($i=0;$i -lt 90;$i++) {
        if(@(Get-CimInstance Win32_Process -Filter "Name = 'DocPilot.exe'" | Where-Object {$_.ExecutablePath -eq (Join-Path $Candidate 'DocPilot.exe')}).Count -eq 0){$closed=$true;break}
        Start-Sleep -Seconds 1
    }
    if(-not $closed){throw 'Current candidate did not close before restart verification'}
    $process=Start-Process (Join-Path $Candidate 'DocPilot.exe') -WorkingDirectory $Candidate -PassThru -WindowStyle Hidden
    $completed=$false
    for($i=0;$i -lt 60;$i++){
        try {$sha=Invoke-RestMethod http://127.0.0.1:8765/api/v1/archive/sha256 -TimeoutSec 2;if($sha.phase -eq 'complete' -and $sha.indexed_files -eq 2){$completed=$true;break}}catch{}
        Start-Sleep -Seconds 1
    }
    if(-not $completed){throw ('Packaged SHA index did not recover on a fresh process: '+($sha|ConvertTo-Json -Depth 6 -Compress))}
    Write-Host ('PASS: packaged initial SHA, unchanged archive bytes, catalogue recovery, live file notification, shared index and fresh-process recovery: '+($sha | ConvertTo-Json -Depth 6 -Compress))
} finally {
    try {Invoke-RestMethod http://127.0.0.1:8765/api/v1/system/quit -Method Post -ContentType 'application/json' -Body '{"quit":true}' -TimeoutSec 10 | Out-Null}catch{}
    Start-Sleep -Seconds 2
    Get-CimInstance Win32_Process -Filter "Name = 'DocPilot.exe'" | Where-Object {$_.ExecutablePath -eq (Join-Path $Candidate 'DocPilot.exe')} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}
}
