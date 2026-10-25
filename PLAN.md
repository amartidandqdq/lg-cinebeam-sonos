# Débloat LG CineBeam Q (HU710QKE) — plan inspiré de cleanyourtv

Objectif : enlever la couche pub / reco / télémétrie et l'accueil LG chargé, tout
en gardant une restauration en une ligne. Méthode cleanyourtv reprise telle
quelle : **sauvegarde → désactivation réversible → vérification par capture →
script de restauration**. Adaptée à webOS, qui n'a pas ADB ni `pm disable-user`.

## Ce qui est acquis

- Modèle : **CineBeam Q, HU710QKE** (2024, webOS 24).
- root : **non disponible aujourd'hui**. RootMyTV est corrigé par LG depuis
  mi-2022 ; la base caniroot ne couvre les projecteurs que jusqu'aux modèles
  2021 (`HE_PJT_W21Z`, exploit `kisscurl`). Donc pas de `systemctl stop` ni de
  montage de stub tout de suite.
- Le projecteur répond sur le réseau (IP pas encore relevée : il est en veille
  avec les ports fermés, à vérifier projecteur allumé).

## Les 4 niveaux, du moins risqué au plus intrusif

### Niveau 0 — réseau (0 % de risque, s'applique tout de suite)
Bloquer les domaines pub/télémétrie sur le routeur, pour la seule IP du
projecteur (`scripts/adblock-list.txt`). Rien n'est installé, on désactive la
règle pour revenir en arrière. C'est le seul niveau qui marche sans dev mode.

Avant de bloquer : relever les requêtes DNS du projecteur pendant 10 min
(`scripts/net-discover.py` ou logs du routeur) pour ne pas casser LG Channels
si on le garde.

### Niveau 1 — réglages internes (0 % de risque)
`scripts/settings-checklist.md` : promotions d'accueil, reco de contenu,
publicité personnalisée, Informations de visionnage, ACR, tuiles promo retirées.

### Niveau 2 — dev mode + accueil maison (réversible, LG officiel)
1. Compte développeur gratuit sur webostv.developer.lge.com, app **Developer
   Mode** installée sur le projecteur, mode dev + Key Server activés → IP +
   passphrase affichées.
2. Depuis ce PC :
   ```
   npx -y -p @webos-tools/cli ares-setup-device -a cinebeam -i "{'host':'IP','port':'9922','username':'prisoner'}"
   npx -y -p @webos-tools/cli ares-novacom --device cinebeam --getkey
   ```
3. `scripts/recon.sh` puis choix des apps : `ares-install`, `ares-launch`,
   `ares-package` (gel des apps inutilisées = équivalent webOS du disable).
4. Accueil maison : fourche de Razdva122 (`clean-your-tv-lg-webos`) ou
   `webos-vibehack`, toutes deux **sans root**. Sur un projecteur, on peut se
   contenter d'un accueil avec 6 tuiles + entrées HDMI, sans les rangées LG.
   Limite : session dev 1000 h à prolonger, et l'appui Home peut encore faire
   clignoter l'accueil LG selon firmware.

### Niveau 3 — root (si un exploit sort pour `HE_PJT_W24…`)
`scripts/debloat.sh` (services `admanager`, `acr2`, `contentminer`, `nudge`,
`sportsalarm`, `adoverlay-service` + hosts marqués), `scripts/restore-root.sh`
pour tout annuler. Rien n'est supprimé : stub monté en RAM + journal
`undo.log`.

## Sauvegarde (à faire avant toute action, niveau 2 ou 3)
```
mkdir -p backup
sh scripts/recon.sh > backup/avant-$(date +%F).txt     # root
# ou, dev mode : ares-shell < scripts/recon.sh > backup/avant.txt
```
On garde aussi : liste des apps installées, `/etc/hosts` d'origine, contenu de
`/proc/mounts`.

## Vérification
`scripts/verify.sh` avant / après. Critère de réussite : `ps` sans
`admanager|contentminer|nudge`, hosts marqués présents, accueil sans rangée
pub, et projecteur toujours utilisable (HDMI, AirPlay, Screen Share, apps).

## Restauration
Niveau 0 : désactiver la règle DNS. Niveau 1 : récocher. Niveau 2 :
suppression de l'app dev (ou `ares-uninstall`). Niveau 3 :
`sh scripts/restore-root.sh`, puis reboot.

## À ne pas casser sur un projecteur
| Service | Pourquoi on le garde |
|---|---|
| `lginput2` / service input | touche Input, HDMI-CEC |
| `com.webos.app.airplay*` | AirPlay 2 depuis iPhone/Mac |
| `mediaserver` / `media` | lecture, ARC |
| mise à jour firmware | si on veut suivre les correctifs |
| `acr2` uniquement | ACR alimente aussi les recos : coupable, mais l'accueil LG perd ses rangées |

## Ordre d'exécution proposé
1. Allumer le projecteur, reléver IP + firmware + OTAID (`recon.sh`).
2. Niveau 0 (blocage DNS ciblé) + niveau 1 (réglages) — 10 min.
3. Niveau 2 si l'accueil reste chargé (dev mode, accueil maison).
4. Recontrôler `rootmy.tv` / caniroot dans quelques semaines : dès qu'un
   exploit `HE_PJT_W24` sort, on passe au niveau 3 et on récupère le brossage
   des services.