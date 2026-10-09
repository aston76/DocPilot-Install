# DocPilot v0.1.0-beta.18

- Scanner préféré mémorisé sur chaque poste, après choix manuel et numérisation réussie.
- Connexions portant le même nom distinguées ; seules les entrées ayant le même identifiant exact sont supprimées. Aucun choix arbitraire du premier scanner si plusieurs sont ambigus.
- Bouton Tester la connexion : résultat réel de connexion WIA au moment du test. Une liste Windows ne garantit pas à elle seule que le scanner est accessible ou prêt.
- Aperçu PDF dans Scanner, puis analyse, correction, gestion des doublons et classement dans le même onglet. Le PDF reste disponible si l’analyse échoue.
- Apparence : clair, sombre ou système, choix mémorisé. Le document lui-même reste lisible sur fond blanc.
- Migration directe depuis les paquets réels beta.12 et beta.14 : base et profils conservés, pas besoin d’installer les versions intermédiaires. Test du mécanisme ancien beta.14 avec le ZIP candidat vérifié ; la récupération beta.12 passe par le nouvel installateur.

Les anciens mécanismes qui échouent avant téléchargement ne peuvent pas être corrigés à distance par un paquet qu’ils n’arrivent pas à installer. Sur un poste concerné, exécuter une fois la commande PowerShell publique du README. La beta.12 a notamment un ancien problème Get-FileHash. La connexion physique au scanner du client dépend toujours du pilote WIA et n’est pas testée par GitHub.
