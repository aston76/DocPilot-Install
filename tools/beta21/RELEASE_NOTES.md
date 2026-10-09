# DocPilot beta 21 — scanner direct par API eSCL

Le panneau « Scanner et classer » propose désormais les scanners eSCL détectés
par Windows comme connexions « API directe · PDF A4 · vitre ». Cette acquisition
évite le chemin WIA qui renvoyait notamment 0x80210064 sur le Kyocera testé.

Sur chaque nouveau poste, sélectionnez la connexion API, cliquez « Approuver le
scanner API », vérifiez le nom et le certificat du scanner puis confirmez.
L'approbation est limitée à DocPilot sur ce PC ; aucun certificat n'est ajouté à
Windows. Le nom, la validité et l'empreinte du certificat restent vérifiés lors
des scans. Un changement de certificat demande une nouvelle approbation.

« Numériser la facture » reçoit une page PDF A4 couleur à 200 dpi sur la vitre.
« Ajouter une page » conserve les précédentes dans l'aperçu PDF. Les connexions
WIA existantes restent proposées. Le PDF reçu est décodé avant d'être ajouté à
l'aperçu. Une erreur préserve les pages déjà acquises. Le traitement et le
classement restent dans le flux existant « Analyser et classer ici ».

Validation matérielle sur ECOSYS MA3500cix : capture par API, puis capture via
l'application beta.21 installée et aperçu PDF disponible. Les tests logiciels
couvrent WIA, eSCL, les erreurs de certificat, la conservation des pages et les
protections d'origine. Aucun document de test n'a été importé ou classé.

Limites : cette connexion API utilise la vitre ; le chargeur et le réveil après
veille ne sont pas validés. Les scanners doivent être détectés par Windows sur
le réseau du poste. Les paramètres et certificats locaux ne font pas partie du
paquet publié.
