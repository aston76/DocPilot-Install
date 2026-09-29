# Installation Windows de DocPilot

Ce dépôt public ne contient aucun code métier ni aucune donnée client. Il héberge uniquement le script de téléchargement et l'archive d'installation Windows.

Dans PowerShell sur le PC du client, exécuter :

```powershell
$p="$env:TEMP\install-docpilot.ps1"; Invoke-WebRequest https://raw.githubusercontent.com/aston76/DocPilot-Install/main/install.ps1 -OutFile $p; powershell -NoProfile -ExecutionPolicy Bypass -File $p
```

Le script récupère la dernière version publiée depuis GitHub, vérifie son empreinte SHA-256, l'extrait puis installe DocPilot dans `%LOCALAPPDATA%\Programs\DocPilot`. Les données seront dans `%LOCALAPPDATA%\DocPilot` et ne font pas partie du téléchargement. Aucun Python ou Node n'est requis sur le PC du client.
