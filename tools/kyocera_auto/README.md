# Importer automatiquement les PDF d’une application de scanner

Cet outil optionnel surveille un dossier local de PDF, par exemple la destination
de Kyocera Print Center, et utilise l’API locale de DocPilot pour leur import et
leur analyse. Il contourne une acquisition WIA défaillante : **il ne répare pas le
pilote et ne commande pas le scanner**.

Il n’est pas intégré aux paquets DocPilot existants. Il requiert un environnement
Python 3.12 avec PyMuPDF disponible. Les tests CI utilisent les dépendances de
`requirements.txt` ; aucune installation n’est déclenchée par cet outil.

## Préparation

1. Dans l’application du scanner, choisir PDF et un dossier local où les scans
   seront enregistrés. Un dossier synchronisé par Synology Drive convient s’il
   est disponible sur le poste ; un chemin réseau UNC est refusé.
2. Copier `config.example.json` vers un fichier **local et privé**, puis adapter
   `source_dir`. Les variables Windows `%USERPROFILE%` et `%LOCALAPPDATA%` sont
   développées à la lecture. Ne pas publier ce fichier, la base ou les journaux.
3. Dans les réglages de DocPilot, activer le classement automatique uniquement
   si souhaité. La liaison ne modifie aucun réglage DocPilot ou Kyocera. Si le
   classement automatique reste désactivé, elle importe et analyse, puis attend
   la validation dans DocPilot. La connexion IA existante de DocPilot est utilisée
   par son propre pipeline, lorsqu’elle est activée.
4. Avant le premier lancement, exclure les PDF déjà présents :

   ```powershell
   python tools/kyocera_auto/bridge.py --config C:\chemin-prive\config.json --initialize
   ```

   Cette étape conserve les fichiers et mémorise leurs empreintes sans les importer.
   Ne pas la relancer pour une file d’attente à traiter : elle exclurait ses nouveaux PDF.
5. Lancer la liaison :

   ```powershell
   python tools/kyocera_auto/bridge.py --config C:\chemin-prive\config.json
   ```

   Sous Windows, `pythonw` peut être utilisé avec les mêmes arguments pour un
   lancement sans console, dans un environnement Python déjà installé. La liaison
   ne crée aucun service, tâche planifiée ou démarrage automatique Windows.

## Comportement

- Un nouveau PDF doit conserver la même taille et date de modification pendant
  au moins 15 secondes. Sa structure et sa fin sont contrôlées avant import.
- Les PDF uniquement en ligne, protégés, incomplets, sans page ou dépassant 50 Mo
  ne sont pas importés. La liaison ne télécharge pas les fichiers du NAS.
- L’empreinte est mémorisée avant l’appel d’import. Une copie identique ou une
  réponse interrompue ne provoque pas un nouvel envoi automatique à l’aveugle.
- DocPilot décide du classement selon ses réglages, ses seuils, son catalogue et
  ses contrôles de doublons. Les cas incertains ou en erreur restent à vérifier.
  La liaison ne valide et ne classe jamais un document par une commande séparée.
- Les originaux du dossier de scan ne sont jamais déplacés, renommés ou supprimés.
- La liaison ouvre DocPilot si un PDF attend et que son API locale est indisponible.
  Une mise à jour ou un accès indisponible laisse le PDF en attente.
- Une seule instance de cette liaison par utilisateur Windows est autorisée.
- Pour arrêter, mettre `"enabled": false` dans le fichier de configuration. L’arrêt
  intervient après le cycle en cours ; il n’interrompt pas un import déjà lancé.

## Suivi du classement

Ouvrir `status.html` dans le répertoire `state_dir`. Il s’actualise toutes les
15 secondes et distingue l’analyse, les doublons, les cas à vérifier, les
simulations et les classements. **L’emplacement affiché après classement vient de
`final_path`, pas du chemin proposé.**

Le fichier classé n’est confirmé localement que si son empreinte correspond au
`stored_sha256` de la base DocPilot ouverte en lecture seule. La présence locale
dans Synology Drive ne confirme pas la synchronisation ou la réception sur le NAS.
Les règles de noms et d’année restent celles de DocPilot ; la liaison ne les modifie pas.

Les fichiers `state.sqlite3`, `status.json`, `status.html` et `bridge.log` restent
locaux. Ils contiennent des noms et chemins privés, sans texte OCR. Les conserver
hors du dépôt public. `state.sqlite3` est nécessaire pour éviter les réimports
après redémarrage.

## Validation

```powershell
python -m unittest discover -s tools/kyocera_auto -p test_bridge.py -v
```

Les tests utilisent des PDF fictifs, des dossiers temporaires et une fausse API
locale. Ils vérifient l’exclusion initiale, l’attente de stabilité, l’import
multipart, la conservation des originaux, les copies identiques, les fichiers
incomplets, les interruptions, les simulations et la vérification de l’intégrité.
Ils ne prouvent pas la précision de l’OCR/IA, l’acquisition physique, ni le
classement complet d’une facture réelle. Un essai réel reste nécessaire sur
chaque poste avant de considérer le parcours validé en production.
