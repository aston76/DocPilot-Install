# Versions de DocPilot

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
