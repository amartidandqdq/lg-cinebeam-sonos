# lg-cinebeam-sonos — fiche projet et consignes agents

> Dernière mise à jour de la fiche : 2026-11-27

## Fiche projet

- **À quoi ça sert** : Un petit programme qui rebranche la barre de son Sonos en Bluetooth quand le projecteur LG CineBeam se rallume. Il marche avec ou sans accès administrateur (« root ») au projecteur.
- **État au 2026-11-27** : Version 0.5.1. Le service `sonos-watcher` est actif sur le m720q, avec le même code que le dépôt. Le journal note des reconnexions Bluetooth jusqu'au 25 novembre (cela ne prouve pas que le son sort). Les 142 tests automatiques passent. Le fichier `~/sonos-watcher/VERSION` affiche encore 0.3.2 : ne pas s'y fier.
- **Fichiers clés** :
  - `watcher/sonos-watcher.py` : le programme principal
  - `watcher/sonos-watcher.service` et `watcher/watcher.env.example` : le service et le modèle de réglages
  - `tools/install.py` : installe le programme (sans le démarrer)
  - `README.md` : fonctionnement, réglages, dépannage
  - `docs/validation.md` : ce qui a été vraiment testé sur le matériel
- **Lancer / tester** :
  - Tests : `.venv/bin/python -m pytest -q` et `.venv/bin/ruff check .`
  - État du service : `systemctl --user status sonos-watcher`
  - Installation et diagnostic : voir `README.md`. Mise à jour et retour arrière : voir `docs/operations.md`.
  - Le dépôt est **public** : jamais de clé, d'adresse Bluetooth réelle ni de capture d'écran privée.
  - Ne pas déployer ni redémarrer le service sans demande explicite.
- **Liens** : projecteur LG CineBeam (HU710QKE), barre Sonos Arc Ultra, machine m720q (fait tourner le service). Dossiers voisins : `lg-cinebeam-sonos-campaign` (essais répétés d'extinction et rallumage), `cinebeam-projector` (accès root du projecteur).
- **En attente** :
  - Essais sur le matériel ([ticket #11](https://github.com/amartidandqdq/lg-cinebeam-sonos/issues/11)) : 30 cycles réussis d'affilée, 48 h sans interruption, vérification stricte du certificat, droits d'appairage minimaux
  - Deux mises à jour de dépendances proposées automatiquement : PR #19 (websockets) et #21 (ruff)

## Règle d'auto-mise-à-jour (obligatoire)

1. Tout agent lit cette fiche avant de travailler dans ce dépôt.
2. Tout agent qui modifie ce dépôt met à jour la fiche dans le même commit : la date en tête, la ligne « État au », et « En attente » si le changement les concerne. Un commit qui laisse la fiche fausse est incomplet.
3. Phrases courtes en français simple : l'utilisateur n'est pas développeur.
