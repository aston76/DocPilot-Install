$ErrorActionPreference='Stop'
Add-Type @'
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
public static class ProgressReader {
 public static Task Hold(string path) {
  var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read);
  return Task.Run(()=>{Thread.Sleep(200);stream.Dispose();});
 }
}
'@
$folder=Join-Path $env:RUNNER_TEMP ('progress-test-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
try {
 $statusFile=Join-Path $folder 'state.json';$form=$null;$release=@{tag_name='test'}
 $tokens=$null;$errors=$null
 $ast=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path 'DocPilot-Update.ps1'),[ref]$tokens,[ref]$errors)
 if($errors.Count){throw 'Updater syntax invalid'}
 $definition=$ast.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Update-Progress'},$true)
 Invoke-Expression $definition.Extent.Text
 Update-Progress 'checking' 'First state' 0
 $reader=[ProgressReader]::Hold($statusFile)
 Update-Progress 'complete' 'Finished' 100
 $reader.Wait()
 $state=Get-Content $statusFile -Raw|ConvertFrom-Json
 if($state.status -ne 'complete' -or $state.percent -ne 100){throw 'Progress lost during a concurrent read'}
 if(@(Get-ChildItem $folder -Filter '*.tmp').Count){throw 'Temporary progress file leaked'}
 Write-Host 'PASS: atomic progress replacement waits for a concurrent reader and preserves the complete state.'
} finally {if($reader){$reader.Wait()};Remove-Item $folder -Recurse -Force}
