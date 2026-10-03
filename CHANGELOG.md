# Versions de DocPilot

## v0.1.0-beta.7 — 3 octobre 2026

- Bouton Mise a jour dans l'application et verification automatique de GitHub a chaque demarrage.
- Installation automatique des nouvelles versions completes : SHA-256 controle, attente de la fin des analyses, fermeture gracieuse et redemarrage.
- Protection contre un retour a une version plus ancienne ; erreur reseau consultable dans le bouton et updater.log.
- Fichier PowerShell portable et lanceur Windows pour installation depuis le NAS, avec paquet local ou telechargement GitHub.
- Import hors ligne d'un profil NAS prive : destinations, societes, fournisseurs et nommage, sans documents ni connexions ; recherche de Commun en cas de chemin introuvable.
- Correctif de demarrage beta.6 conserve. Les profils et index prives ne sont pas distribues dans la release publique.



## v0.1.0-beta.6 — 2 octobre 2026

- Correction du blocage au démarrage lorsque la connexion de contrôle à `127.0.0.1:8765` ne répond pas : délai maximal de deux secondes avant le démarrage du serveur.
- Correctif ciblé du lanceur de la bêta 5 ; tous les autres fichiers du paquet sont identiques. Script de reproduction : `tools/hotfix_probe_timeout.py` (Python 3.12, réservé à la préparation du paquet).
- Vérifications : reproduction exacte de l’exécutable corrigé, intégrité du ZIP, démarrage Windows, réponse HTTP 200 de l’API de santé et de l’interface. Installation sur un poste Windows vierge non vérifiée.
- SHA-256 du ZIP : `4298cb1c9ae6e4c5d7d1c64be1a28ecb2366fcff1f43fc4ba0570413a329634f`.

## v0.1.0-beta.5 — 2 octobre 2026

- Interface simplifiée : Classer, Documents et Réglages ; une seule liste par vue.
- Validation directe du dossier proposé après analyse, sans ouvrir la fiche complète.
- Détection des doublons exacts par SHA-256, alerte rouge et blocage d'un second classement. La source de l'index et ses limites restent consultables.
- Scan des fichiers lisibles du dossier de classement depuis les réglages.
- Corbeille retirant le document du programme uniquement, en conservant le fichier archivé.
- Informations et nom du fichier modifiables sous des volets ; corrections nécessaires visibles.
- Fermeture plus fiable : demande idempotente, arrêt gracieux, confirmation et possibilité de réessayer.
- Lecture améliorée des dates multilingues, montants, devises et types documentaires ; originaux Office/XML conservés.
- Icône et raccourci Bureau ; mise à jour conservant les données.

Les règles et les index propres à chaque client restent locaux et ne sont pas distribués dans le paquet public. La comparaison SHA-256 reconnaît les fichiers strictement identiques ; elle ne remplace pas une comparaison du contenu de fichiers différents.
