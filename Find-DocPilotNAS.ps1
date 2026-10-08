function Find-DocPilotNAS {
 param([string]$ExpectedRoot,[string]$InstallerFolder,[string[]]$SearchRoots,
       [string]$SynologySystemFolders=(Join-Path $env:LOCALAPPDATA 'SynologyDrive\SystemFolders'))
 if (Test-Path -LiteralPath $ExpectedRoot -PathType Container) {return @($ExpectedRoot)}
 $leaf=Split-Path $ExpectedRoot -Leaf
 $company=Split-Path (Split-Path $ExpectedRoot -Parent) -Leaf
 $roots=@($SearchRoots)
 if (-not $SearchRoots) {
    $roots+=@(Get-PSDrive -PSProvider FileSystem | ForEach-Object {$_.Root;$_.DisplayRoot})
    if(Get-Command Get-SmbMapping -ErrorAction SilentlyContinue){$roots+=@(Get-SmbMapping -ErrorAction SilentlyContinue | ForEach-Object {$_.LocalPath;$_.RemotePath})}
    $roots+=@(Get-ChildItem -LiteralPath $env:USERPROFILE -Directory -ErrorAction SilentlyContinue | Where-Object {$_.Name -like 'SynologyDrive*'} | ForEach-Object {$_.FullName})
    if($InstallerFolder){$roots+=$InstallerFolder; $roots+=(Split-Path $InstallerFolder -Parent);$roots+=(Split-Path (Split-Path $InstallerFolder -Parent) -Parent)}
 }
 # Drive keeps shortcuts to team folders here, including custom sync locations.
 # SystemFolders and its numbered subfolders can have Hidden/System attributes.
 if(Test-Path -LiteralPath $SynologySystemFolders -PathType Container) {
    $shell=$null
    try {
        $shell=New-Object -ComObject WScript.Shell
        $folders=@($SynologySystemFolders)+@(Get-ChildItem -LiteralPath $SynologySystemFolders -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {$_.FullName})
        foreach($folder in $folders) {
            foreach($link in @(Get-ChildItem -LiteralPath $folder -Filter '*.lnk' -File -Force -ErrorAction SilentlyContinue)) {
                $shortcut=$null
                try {
                    $shortcut=$shell.CreateShortcut($link.FullName)
                    $target=[Environment]::ExpandEnvironmentVariables($shortcut.TargetPath)
                    if($target -and (Test-Path -LiteralPath $target -PathType Container)) {$roots+=$target}
                } catch { Write-Verbose ('Raccourci Synology ignore : '+$link.FullName) }
                finally {if($shortcut){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)}}
            }
        }
    } catch { Write-Verbose 'Raccourcis Synology Drive indisponibles.' }
    finally {if($shell){[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}}
 }
 $found=@()
 foreach($base in @($roots | Where-Object {$_} | Select-Object -Unique)) {
    if(-not (Test-Path -LiteralPath $base -PathType Container)) {continue}
    $suffixes=@($leaf,('Commun\'+$leaf),($company+'\'+$leaf),('Commun\'+$company+'\'+$leaf))
    $candidates=@($base)+@($suffixes | ForEach-Object {Join-Path $base $_})
    foreach($candidate in $candidates){
        if((Test-Path -LiteralPath $candidate -PathType Container) -and (Test-Path -LiteralPath (Join-Path $candidate 'Factures') -PathType Container)){$found+=[IO.Path]::GetFullPath($candidate)}
    }
 }
 return @($found | Select-Object -Unique)
}
