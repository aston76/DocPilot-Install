$ErrorActionPreference='Stop'
$roots=@(Get-PSDrive -PSProvider FileSystem | ForEach-Object {$_.Root;$_.DisplayRoot})
if(Get-Command Get-SmbMapping -ErrorAction SilentlyContinue){$roots+=@(Get-SmbMapping -ErrorAction SilentlyContinue | ForEach-Object {$_.LocalPath;$_.RemotePath})}
$roots+=@(Get-ChildItem -LiteralPath $env:USERPROFILE -Directory -Force -ErrorAction SilentlyContinue | Where-Object {$_.Name -like 'SynologyDrive*' -or $_.Name -eq 'Commun'} | ForEach-Object {$_.FullName})
$system=Join-Path $env:LOCALAPPDATA 'SynologyDrive\SystemFolders'
$shell=$null
try {
    if(Test-Path -LiteralPath $system -PathType Container){
        $shell=New-Object -ComObject WScript.Shell
        $folders=@($system)+@(Get-ChildItem -LiteralPath $system -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {$_.FullName})
        foreach($folder in $folders){
            foreach($file in @(Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -File -Force -ErrorAction SilentlyContinue)){
                $shortcut=$null
                try {$shortcut=$shell.CreateShortcut($file.FullName);if($shortcut.TargetPath){$roots+=[Environment]::ExpandEnvironmentVariables($shortcut.TargetPath)}}
                catch {} finally {if($shortcut){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)}}
            }
        }
    }
} finally {if($shell){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}}
ConvertTo-Json -InputObject @($roots | Where-Object {$_} | Select-Object -Unique) -Compress
