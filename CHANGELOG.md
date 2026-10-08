## v0.1.0-beta.11

- Détection portable du dossier Commun, lecteurs mappés et racines Synology Drive, choix par défaut local.
- Vérification obligatoire au démarrage et avant classement ; message bloquant et choix manuel en cas de dossier absent, incorrect ou ambigu.
- Limites d’attente des lecteurs inaccessibles, étapes et durées du traitement, correction manuelle des champs ambigus.
- Dates de facture distinctes de l’échéance et de l’arrivée ; suivi de copie et états de synchronisation par fichier sans pourcentage inventé.
- Construction depuis le paquet public vérifié, test de démarrage Windows et publication après dépôt complet des fichiers ZIP/SHA-256.

# Versions de DocPilot

## v0.1.0-beta.10 — 5 octobre 2026

Cette version regroupe les corrections des 4 et 5 octobre 2026.

- Chargement : message immédiat, animation et durée écoulée ; suppression du pourcentage trompeur bloqué à 0 %.
- Copies exactes : contrôle SHA-256 sur les fichiers actuellement accessibles avant OCR et IA. Une copie confirmée évite ces analyses et reste bloquée au classement ; la réanalyse manuelle reste disponible.
- Doublons renommés : les chemins historiques sont revérifiés, les noms actuels affichés et les fichiers disparus écartés. Les limites de la vérification restent visibles.
- Doublons métier entre documents : société, date de facture, numéro et montant doivent correspondre, avec la même devise. Ce contrôle reste distinct de celui des copies exactes SHA-256.
- Lecture des factures avec annexes : jusqu’à 24 pages montrées intégralement à l’analyse ; les documents partiellement lus restent à vérifier.
- Monnaies : codes ISO en majuscules (CHF, EUR, USD…), deux décimales et séparateur de milliers suisse, par exemple CHF 1'000.00.
- Corrections des réponses API de mise à jour et de classement, du choix de devise et des types de document à confirmer.

Installation Windows : extraire le ZIP complet puis exécuter Installer-DocPilot.cmd. Depuis beta.7, utiliser aussi le bouton Mise à jour ou relancer DocPilot ; la mise à jour attend la fin des analyses et conserve les données locales.

Le paquet public ne contient aucune facture, base utilisateur, connexion enregistrée, catalogue d’entreprise ou profil privé du NAS. Les fichiers indisponibles ou non synchronisés empêchent de garantir une vérification exhaustive du serveur.

Vérifications locales : chargement du moteur empaqueté, classement en simulation sur base isolée, doublon précoce avec/sans correspondance et vérification incomplète, réanalyse, indicateur de chargement, version interne, intégrité ZIP et exclusions privées. Le contrôle d’installation Windows GitHub Actions complète ces vérifications.

SHA-256 de DocPilot-Windows-portable.zip :
`b5bf587a5a4442269f1256e5538f63443123dd0244ced07e1faefe8038821c81`


## v0.1.0-beta.8 — 3 octobre 2026

- Chemin proposé et modifiable directement dans la liste, sans ouvrir la fiche complète.
- Pour un fournisseur absent du catalogue, proposition d’un nouveau dossier sous la catégorie du document ; création après validation explicite uniquement.
- Aucun millésime inventé pour une destination confirmée manuellement.
- Contrôles conservés : doublon SHA-256, données inchangées avant confirmation, confinement dans l’archive, simulation et refus d’écraser un fichier existant.
- Versions du paquet et du contrôle automatique synchronisées sur beta.8.

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
