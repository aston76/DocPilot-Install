# Versions de DocPilot

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
