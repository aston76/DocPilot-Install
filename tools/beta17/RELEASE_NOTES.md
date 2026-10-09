# DocPilot v0.1.0-beta.17

- Mise à jour silencieuse : progression dans DocPilot, aucun second dialogue Windows, redémarrage automatique.
- Après relance : version installée et « Vous avez la dernière version ». Aucune proposition de réinstaller une version identique ou antérieure.
- Installation : le répertoire du programme reste en place, même si un ancien processus de mise à jour y travaille. Remplacement des fichiers avec sauvegarde et restauration en cas d’erreur, conservation des fichiers privés et données.
- Les fonctions scanner, factures locales et index de doublons sont conservées.

Le passage depuis beta.14–16 utilise encore leur ancien dialogue une dernière fois. Le fonctionnement silencieux prend effet avec beta.17. En cas d’installation déjà échouée, utiliser le script public PowerShell : il récupère la nouvelle version et conserve les données.

Vérification : tests API/UI, paquet et installation réelle sur Windows, réinstallation depuis un répertoire actif et relance silencieuse. Le scanner physique du client n’est pas testé dans cette version.
