function Find-DocPilotNAS {
 param([string]$ExpectedRoot,[string]$InstallerFolder,[string[]]$SearchRoots)
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
 $found=@()
 foreach($base in @($roots | Where-Object {$_} | Select-Object -Unique)) {
    $suffixes=@($leaf,('Commun\'+$leaf),($company+'\'+$leaf),('Commun\'+$company+'\'+$leaf))
    $candidates=@($base)+@($suffixes | ForEach-Object {Join-Path $base $_})
    foreach($candidate in $candidates){
        if((Test-Path -LiteralPath $candidate -PathType Container) -and (Test-Path -LiteralPath (Join-Path $candidate 'Factures') -PathType Container)){$found+=[IO.Path]::GetFullPath($candidate)}
    }
 }
 return @($found | Select-Object -Unique)
}
