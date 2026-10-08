# Installation Windows de DocPilot

Ce dépôt public héberge les scripts d’installation Windows et les modules de correctifs distribués avec DocPilot. Il ne contient aucune donnée client.

Dans PowerShell sur le PC du client, exécuter :

```powershell
$p="$env:TEMP\install-docpilot.ps1"; Invoke-WebRequest https://raw.githubusercontent.com/aston76/DocPilot-Install/main/install.ps1 -OutFile $p; powershell -NoProfile -ExecutionPolicy Bypass -File $p
```

Le script récupère la dernière version publiée depuis GitHub, vérifie son empreinte SHA-256, l'extrait puis installe DocPilot dans `%LOCALAPPDATA%\Programs\DocPilot`. Les données seront dans `%LOCALAPPDATA%\DocPilot` et ne font pas partie du téléchargement. Aucun Python ou Node n'est requis sur le PC du client.

La version `v0.1.0-beta.10` ajoute un indicateur de chargement visible, vérifie les copies exactes avant OCR/IA, actualise les noms des doublons renommés et améliore la lecture des factures avec annexes. Le nommage utilise les codes ISO et le séparateur suisse des milliers. Les nouveautés des versions précédentes sont conservées.

Les nouveautés sont décrites dans [CHANGELOG.md](CHANGELOG.md). Les paquets sont disponibles dans les [versions publiées](https://github.com/aston76/DocPilot-Install/releases).

La mise à jour conserve les documents, les réglages et la connexion locale. Si DocPilot est ouvert, l'installateur demande son arrêt gracieux et attend la fin des traitements ; il interrompt l'installation si l'application ne peut pas être fermée. Un raccourci est ajouté au Bureau et au menu Démarrer.

Les archives publiques n'incluent aucune facture, base de données utilisateur, connexion enregistrée, catalogue fournisseur client ou index privé de fichiers. La vérification SHA-256 s'appuie sur l'index disponible sur chaque poste ; les fichiers illisibles ou non synchronisés ne permettent pas de garantir l'absence d'un doublon sur le serveur.

Pour installer depuis un fichier PowerShell portable, telecharger [Installer-DocPilot.ps1](Installer-DocPilot.ps1) et l'executer. Il telecharge la derniere version complete et controle son SHA-256. Un ZIP portable et son SHA places a cote du script permettent une installation depuis le NAS, sans retelecharger le logiciel pour chaque poste. Le lanceur [Installer-DocPilot.cmd](Installer-DocPilot.cmd) facilite l'execution sous Windows.

A partir de beta.7, DocPilot verifie GitHub au demarrage et installe automatiquement une version plus recente, apres la fin des analyses. Le bouton Mise a jour permet aussi de controler la version manuellement. L'installation conserve la base locale, les connexions et le profil NAS ; un echec de reseau ou de verification est signale sans lancer l'installation.

Pour les deploiements de plusieurs postes, un profil prive peut accompagner le paquet NAS dans un dossier deployment-profile. Il contient le catalogue de destinations et les references de classement, sans documents ni connexions. Il reste sur le partage interne et n'est pas dans ce depot public. Si le chemin d'origine est inaccessible, le programme d'installation recherche l'archive dans Commun parmi les lecteurs connectes et les dossiers Synology Drive ; une correspondance ambigue demande un choix. Les quatre postes conservent chacun leur base et leur connexion IA.

## Dossier de travail portable (beta.11)

Au démarrage, DocPilot vérifie le dossier Fournisseurs-Créanciers et la société attendue. Il recherche les lecteurs Windows, Commun et les racines configurées dans Synology Drive. Un seul résultat valide devient le dossier par défaut de ce poste. Aucun résultat ou plusieurs résultats bloquent le traitement jusqu’à vérification dans le bandeau Dossier de travail. Un dossier manuel doit avoir le bon nom de société et les catégories attendues.

Le contrôle vérifie la structure du dossier ; il ne prouve pas à lui seul que Synology a fini la synchronisation. Le tableau de synchronisation distingue la copie locale, la confirmation du NAS et une progression inconnue.

Sources du correctif : `tools/beta11`. Construction reproductible depuis la beta.10 publique dont le SHA-256 est fixé : `python tools/build_beta11.py` (Python 3.12). GitHub teste le paquet sur Windows avant publication. Aucun catalogue ni document privé ne fait partie de la release.
