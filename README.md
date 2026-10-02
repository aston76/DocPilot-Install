# Installation Windows de DocPilot

Ce dépôt public ne contient aucun code métier ni aucune donnée client. Il héberge uniquement le script de téléchargement et l'archive d'installation Windows.

Dans PowerShell sur le PC du client, exécuter :

```powershell
$p="$env:TEMP\install-docpilot.ps1"; Invoke-WebRequest https://raw.githubusercontent.com/aston76/DocPilot-Install/main/install.ps1 -OutFile $p; powershell -NoProfile -ExecutionPolicy Bypass -File $p
```

Le script récupère la dernière version publiée depuis GitHub, vérifie son empreinte SHA-256, l'extrait puis installe DocPilot dans `%LOCALAPPDATA%\Programs\DocPilot`. Les données seront dans `%LOCALAPPDATA%\DocPilot` et ne font pas partie du téléchargement. Aucun Python ou Node n'est requis sur le PC du client.

Les nouveautés sont décrites dans [CHANGELOG.md](CHANGELOG.md). Les paquets sont disponibles dans les [versions publiées](https://github.com/aston76/DocPilot-Install/releases).

La mise à jour conserve les documents, les réglages et la connexion locale. Si DocPilot est ouvert, l'installateur demande son arrêt gracieux et attend la fin des traitements ; il interrompt l'installation si l'application ne peut pas être fermée. Un raccourci est ajouté au Bureau et au menu Démarrer.

Les archives publiques n'incluent aucune facture, base de données utilisateur, connexion enregistrée, catalogue fournisseur client ou index privé de fichiers. La vérification SHA-256 s'appuie sur l'index disponible sur chaque poste ; les fichiers illisibles ou non synchronisés ne permettent pas de garantir l'absence d'un doublon sur le serveur.
