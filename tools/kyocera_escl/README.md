# Scan Kyocera direct par API eSCL

Prototype de capture locale PDF, sans application Kyocera, sans WIA, sans import
ni classement. **Ce prototype n'est pas encore raccordé au bouton Numériser de
DocPilot, et ne constitue pas une nouvelle version installable de DocPilot.**

## Résultat matériel du 9 octobre 2026

Sur un ECOSYS MA3500cix, l'API eSCL a créé un travail (HTTP 201), puis livré un
PDF (HTTP 200) : une page A4, couleur, 200 dpi. Le premier test a pris 14,53 s.
Le PDF a été décodé localement : environ 209,93 × 296,93 mm. Le contenu d'une
facture, sa reconnaissance, le classement et le réveil après veille ne sont pas
validés par cet essai. Aucun document test n'a été importé ou classé.

Le service eSCL est annoncé sur **9096** pour HTTPS et 9095 pour HTTP sur ce
périphérique. Le port HTTPS général 443 renvoyait HTTP 500 aux requêtes eSCL.
Toujours utiliser l'adresse déclarée par le périphérique ; ne pas supposer un
port identique pour tous les appareils.

Les essais WIA renvoyaient 0x80210064 sur eSCL et 0x80210006 sur WSD. Le succès
direct ne prouve pas à lui seul la cause interne de ces erreurs de pilotes.

## Découvrir l'adresse sans modifier Windows

PowerShell :

```powershell
Get-PnpDevice | Where-Object {$_.InstanceId -like 'SWD\Escl\*'} |
  ForEach-Object { Get-PnpDeviceProperty -InstanceId $_.InstanceId } |
  Where-Object {$_.Data -is [string] -and $_.Data -match '^https?://.*/eSCL$'} |
  Select-Object InstanceId, Data
```

## Confiance TLS explicite

Le certificat DER et son empreinte SHA256 doivent avoir été obtenus et approuvés
pour le scanner voulu avant utilisation. Le script ne récupère ni n'approuve
automatiquement un certificat inconnu. Ne pas utiliser une option qui désactive
la vérification TLS. Le certificat n'est pas ajouté au magasin Windows.

L'URL utilise le nom présent dans le certificat. `--address` donne l'IP de
connexion du scanner. Le contexte TLS vérifie la validité et le nom ; l'empreinte
est vérifiée sur le fichier local et sur le certificat effectivement reçu.

## Exécuter

Python 3.12, bibliothèque standard uniquement. Les valeurs ci-dessous sont des
exemples et doivent être remplacées par celles du scanner. Aucun certificat,
identifiant d'appareil ou document réel n'est fourni dans le dépôt.

```powershell
python tools/kyocera_escl/escl_scan.py probe --endpoint "https://scanner.example:9096/eSCL" --address "192.0.2.10" --certificate "C:\Diagnostic\scanner.der" --sha256 "EMPREINTE_SHA256_APPROUVEE"
python tools/kyocera_escl/escl_scan.py scan --endpoint "https://scanner.example:9096/eSCL" --address "192.0.2.10" --certificate "C:\Diagnostic\scanner.der" --sha256 "EMPREINTE_SHA256_APPROUVEE" --output-dir "C:\Diagnostic\essais"
```

`probe` lit uniquement capacités et état. `scan` lance explicitement une page
sur la vitre, A4, RGB24, PDF, 200 dpi. Il refuse un scanner occupé, un profil non
annoncé, un changement de certificat ou une redirection de travail vers un autre
hôte. Il ne lit pas les travaux existants et n'annule pas ceux d'une autre
application. Les erreurs laissent éventuellement un fichier temporaire local ;
aucun original existant n'est supprimé ou écrasé. Un en-tête et une fin de PDF sont
contrôlés avant publication ; un décodeur PDF reste nécessaire dans DocPilot pour
valider complètement le document.

## Intégration restant à faire dans DocPilot

- Découvrir l'endpoint et demander la confiance du certificat sur le poste.
- Ajouter un backend eSCL au panneau scanner avec sélection explicite de la source.
- Récupérer le PDF dans la session d'aperçu locale et le décoder avant import.
- Conserver la validation actuelle du document et le suivi de sa destination.
- Gérer progression, délais, annulation du seul travail créé, chargeur et pages multiples.
- Tester une vraie facture et le retour après veille avant toute publication de version.

Références : [documentation Kyocera Print Center](https://www.kyoceradocumentsolutions.com/support/printcenter/data/en/scanning.html),
[implémentation eSCL OpenPrinting](https://github.com/OpenPrinting/go-mfp/tree/master/proto/escl).

Tests sans matériel : `python -m unittest discover -s tools/kyocera_escl -v`.
