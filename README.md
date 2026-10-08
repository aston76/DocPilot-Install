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

**Migration vers beta.13 :** le test depuis la beta.12 publique a révélé que son ancien script peut échouer avec `Get-FileHash introuvable` avant installation. Sur un poste touché, exécuter une fois la commande PowerShell ci-dessus pour recevoir beta.13 ; les données et réglages sont conservés. La beta.13 corrige ce problème dans son propre mécanisme de mise à jour, mais ne peut pas réparer à distance le script déjà présent dans une ancienne installation. L’installation publique et la réinstallation avec conservation des données ont été vérifiées sur Windows : [test réussi](https://github.com/aston76/DocPilot-Install/actions/runs/37771071192).

Pour les deploiements de plusieurs postes, un profil prive peut accompagner le paquet NAS dans un dossier deployment-profile. Il contient le catalogue de destinations et les references de classement, sans documents ni connexions. Il reste sur le partage interne et n'est pas dans ce depot public. Si le chemin d'origine est inaccessible, le programme d'installation recherche l'archive dans Commun parmi les lecteurs connectes et les dossiers Synology Drive ; une correspondance ambigue demande un choix. Les quatre postes conservent chacun leur base et leur connexion IA.

## Dossier de travail portable (beta.11)

Au démarrage, DocPilot vérifie le dossier Fournisseurs-Créanciers et la société attendue. Il recherche les lecteurs Windows, Commun et les racines configurées dans Synology Drive. Un seul résultat valide devient le dossier par défaut de ce poste. Aucun résultat ou plusieurs résultats bloquent le traitement jusqu’à vérification dans le bandeau Dossier de travail. Un dossier manuel doit avoir le bon nom de société et les catégories attendues.

Le contrôle vérifie la structure du dossier ; il ne prouve pas à lui seul que Synology a fini la synchronisation. Le tableau de synchronisation distingue la copie locale, la confirmation du NAS et une progression inconnue.

Sources du correctif : `tools/beta11`. Construction reproductible depuis la beta.10 publique dont le SHA-256 est fixé : `python tools/build_beta11.py` (Python 3.12). GitHub teste le paquet sur Windows avant publication. Aucun catalogue ni document privé ne fait partie de la release.

## Scan SHA automatique (beta.12)

Le scan démarre après vérification du dossier et se relance à chaque ouverture. Son état apparaît sur la page Documents/Ajouter et classer. La progression est calculée sur les fichiers vérifiés une fois la liste connue. Les empreintes des fichiers inchangés sont conservées localement, séparément pour chaque archive ; aucune écriture n’est faite dans les archives.

Les fichiers Synology uniquement en ligne doivent être rendus disponibles hors connexion pour être vérifiés. Un scan partiel ne confirme pas l’absence de doublon. La présence et le contenu des correspondances restent contrôlés avant de les déclarer identiques. Construction du paquet : `python tools/build_beta12.py` avec Python 3.12, à partir de la beta.11 publique vérifiée par SHA-256.

Les archives déjà utilisées sont réactualisées chaque minute et les nouveaux dossiers visibles via Synology Drive sont ajoutés au catalogue local. Les empreintes restent séparées par poste ; les fichiers et dossiers sont synchronisés par Synology. Cette synchronisation ne garantit pas l’exclusion de deux classements simultanés sur deux PC : un verrou commun sur le NAS serait nécessaire pour cette garantie.

## Index local et mise à jour visible (beta.13)

La beta.13 utilise SQLite embarqué sur chaque PC et reprend automatiquement les anciens caches SHA. Les recherches visent les correspondances indexées, sans relire chaque facture du fournisseur. Des instantanés distincts par poste dans `DocPilot-Partage/v1` servent d’indices partagés ; SQLite reste local. La cohérence entre postes dépend de la synchronisation Synology et ne constitue pas un verrou distribué.

La fenêtre de mise à jour indépendante montre le téléchargement, la préparation et le résultat. Après réussite, OK relance le programme. Les fichiers du programme sont préparés dans un dossier temporaire avant remplacement ; les données locales sont conservées. Les notifications Windows et un contrôle périodique actualisent les empreintes.

Le workflow `publish-beta13.yml` teste le paquet sur Windows x64 avant publication. L’interface Mac de développement ne constitue pas un paquet distribué et ne reçoit pas ce moteur automatiquement.

Le catalogue des destinations est partagé via les mêmes instantanés privés. Le contrôle se fait au démarrage, après notification Windows et toutes les cinq minutes. Il importe les alias et noms proposés pour les dossiers réellement présents et conserve les chemins et personnalisations du poste. Un dossier annoncé mais encore absent attend sa synchronisation Synology. Les PC doivent viser la même archive partagée ; ce mécanisme ne remplace pas la synchronisation des documents par Synology Drive.

## Factures oubliées sur le PC

Dans « Sur ce PC », « Détecter les factures sur ce PC » lance une recherche locale en arrière-plan. Les dossiers NAS/Drive identifiés et dossiers système sont exclus. Les copies exactes connues du NAS et les documents déjà présents dans DocPilot sont signalés ; une vérification incomplète ne confirme pas l’absence de doublon. Les images/scans/Office incertains demandent une vérification. Aucun import ni nettoyage ne se fait sans action de l’utilisateur.

« Retirer de la liste » garde le fichier. « Supprimer aussi du PC » demande confirmation, protège les archives et fichiers modifiés, et journalise l’utilisateur, la machine et le chemin. Cette suppression est définitive sur le PC ; elle n’efface pas le document archivé sur le NAS. Les fichiers uniquement en ligne ou de plus de 100 Mo ne sont pas lus ; les accès refusés et recherches limitées restent signalés.
