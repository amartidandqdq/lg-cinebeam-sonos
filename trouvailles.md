# Trouvailles — LG CineBeam Q (HU710QKE), webOS 24

> Dernière mise à jour : 2026-10-25. Méthode inspirée de cleanyourtv (backup → désactivation réversible → vérification), adaptée à webOS.

## 1. Ce que nous avons établi

| Sujet | Trouvaille |
|---|---|
| Modèle | LG CineBeam Q — HU710QKE (2024, webOS 24) |
| Réseau | `192.168.1.2` — ports SSAP 3000 (HTTP) et 3001 (WSS) |
| Root | **Impossible** : RootMyTV corrigé par LG depuis mi-2022 ; les exploits caniroot s'arrêtent aux projecteurs 2021 (`HE_PJT_W21Z`) |
| API | SSAP WebSocket ; ce firmware accepte `type: "request"` (pas `call`), origin vide, clé de certificat auto-signée (SSL sans vérification) |
| Appairage | Fait le 2026-10-25 ; clé cliente dans `backup/client-key.txt` (à NE PAS partager) |
| Sauvegarde | `backup/inventaire-*.json` : 99 apps listées, apps au premier plan, launch points de l'accueil |

## 2. Usage déclaré (notre feuille de route)

- **Utilisé** : Jellyfin en DLNA (le projecteur est un *renderer* via l'app `Media Player`) et **AirPlay**.
- **Non utilisé** : LG Channels / Live TV, **assistants vocaux** (Alexa, Google).
- **À retirer de l'accueil** : CANAL+, TF1+, M6+, ARTE, Orange TV, france.tv, Pathé Home.

### À garder impérativement
| App / service | Pourquoi |
|---|---|
| `com.webos.app.mediadiscovery` (Media Player) | le renderer DLNA du projecteur |
| `airplay` | AirPlay 2 (iPhone / Mac / iPad) |
| `com.webos.app.hdmi1-4`, `inputcommon` | les entrées HDMI |
| `com.webos.app.miracast` | Screen Share (au cas où) |
| `com.webos.app.home` / `homeconnect` | l'accueil LG (on le garde, on l'épure) |
| `com.webos.app.screensaver` | écran de veille |
| mise à jour firmware | laisser les correctifs passer |

### À supprimer de l'accueil (apps « utilisateur »)
`CANAL+`, `TF1+`, `M6+`, `ARTE`, `Orange TV`, `france.tv`, `Pathé Home` — soit depuis l'UI
(maintien sur la tuile → retirer), soit en désinstallation via le mode développeur
(`ares-install --remove`), voir §4.

> Sauvegarde de l'inventaire confirme : ces 7 apps ont `systemApp: false` + `CPApp: true`
> (apps du store, désinstallables proprement). La pub/ACR/Live TV ont `systemApp: true`
> (non désinstallables sans root : on les coupe par réglages + DNS).

### À neutraliser (bloat / pub / télémétrie)
| Cible | Ce que c'est | Comment |
|---|---|---|
| `com.webos.app.adapp` | app « Advertisement » | invisible sans root : coupée via réglages + DNS |
| `com.webos.app.shoppinghdmi1-4` + `shoppingoverlay` | les overlays de pub shopping sur les entrées HDMI | disparaissent avec l'ACR / les promos désactivées |
| `com.webos.app.acr*` (LivePlus) | reconnaissance de contenu (télémétrie) | réglage « Informations de visionnage » + DNS |
| `com.webos.app.exampleapp.*` | apps de démo LG oubliées | inertes, sans tuile ; aucun risque |
| `amazon.alexapr`, `google.assistant` | assistants non utilisés | se désactivent depuis leurs réglages / à masquer |
| `com.webos.app.livetv`, `livemenu`, `livepick`… | stack TV live | masquage des tuiles ; LG Channels désactivable |

## 3. Blocage DNS via Pi-hole (niveau 0, zéro risque)

Liste prête à importer : `scripts/pihole-blocklist.txt` (une domaine par ligne).
Procédure :
1. Pi-hole → Group Management → **Groups** → créer un groupe `lg-projecteur`.
2. Adressage statique du projecteur sur ta box (réservation DHCP) puis, dans Pi-hole,
   ajouter l'IP du projecteur au groupe.
3. Domainlist → ajouter les domaines du fichier avec le groupe `lg-projecteur` ciblé.
4. Vérification : `nslookup eic.ads.lgtvcommon.com 192.168.1.x` (IP du Pi-hole) → doit répondre `0.0.0.0`.

⚠️ Certains firmwares LG codent en dur un DNS de secours (8.8.8.8). Si des requêtes passent
malgré le Pi-hole, il faut une règle de redirection DNS (NAT hairpin DNS) sur la box —
on regarde ça seulement si les pubs passent encore.

**Ne pas bloquer en entier** : `lgtvcommon.com` et `lge.com` portent aussi des services
légitimes (mises à jour, TinyM wrapper). On ne vise que les sous-domaines pub/pub/reco.

## 4. Réglages sur le projecteur (checklist ciblée)

Voir `scripts/settings-checklist.md` — résumé pour nous :
- Accueil : désactiver **Promotion de l'écran d'accueil** et **Recommandation de contenu**.
- Confidentialité : **Informations de visionnage** OFF (= coupe l'ACR/LivePlus),
  **Publicité personnalisée** OFF, **Recommandations basées sur les centres d'intérêt** OFF.
- Retirer les tuiles FR inutilisées de l'accueil (maintien tuile → retirer).
- LG Channels : désactiver si présent.
- Ne pas toucher : mise à jour auto, ThinQ, réseau.

## 5. Réversibilité (notre contrat « rien de briqué »)

| Action | Annulation |
|---|---|
| Blocage Pi-hole | retirer le domaine du groupe |
| Retrait d'une tuile de l'accueil | tu peux la remettre depuis « Apps » |
| Désactivation réglages | recocher dans les menus |
| Désinstallation d'une app user (dev mode) | réinstallation via LG Content Store |
| `client-key` révoquée | refaire un appairage (popup) |

Aucune manipulation ne touche la partition système ; sans root, rien n'est désinstallé
de force, et le pire cas reste « l'app revient après une mise à jour LG ».

## 6. Prochaines étapes

1. **Toi** : checklist réglages (§4) + import Pi-hole (§3).
2. **Moi** : script de vérification avant/après (`scripts/verify.sh` adapté en Python SSAP,
   car pas de shell root ici).
3. Optionnel : activer le **mode développeur** pour `ares-install --remove` des apps FR
   proprement (l'UI suffit souvent, le dev mode permet en plus un audit complet).
4. Watch-out : à chaque mise à jour LG, on relit l'inventaire (script `backup.py` relançable
   à volonté, lecture seule).

## 7. Son — Sonos en Bluetooth (reconnexion auto)

**Diagnostic (SSAP, 2026-10-25)** : la sortie audio persistante du projecteur est
`tv_speaker`. Quand la connexion Bluetooth échoue à l'allumage, le CineBeam retombe sur
son haut-parleur interne — c'est pourquoi tu dois refaire la connexion à chaque fois.

### Le point clé côté Sonos
Sur les barres Sonos (Ray, Beam G2, Arc, Arc Ultra), le Bluetooth n'accepte une connexion
entrante que quand la barre est **allumée et en source Bluetooth** (touche BT). Si le
CineBeam tente la reconnexion pendant que la barre est sur HDMI ou sur une autre source,
la tentative échoue et le projecteur retombe sur `tv_speaker`.

### Procédure
1. **Sur la Sonos** : allume-la et passe-la en source Bluetooth (touche BT) ; elle accepte
   alors les connexions des appareils déjà jumelés.
2. **Sur le CineBeam** : Paramètres → Son → **Sortie sonore** → sélectionner la Sonos
   (le « Sound Out » persiste). Vérifier le jumelage dans Paramètres → Général →
   Périphériques → Bluetooth (statut « jumelé », pas juste « connecté »).
3. **Tester** : éteindre le projecteur, rallumer, la Sonos restant en source BT →
   la reconnexion doit se faire seule.
4. Si ça saute encore : vérifier dans l'app Sonos que la barre ne passe pas en veille
   profonde — le BT doit rester joignable.

### Ce qu'on a observé (2026-10-25)
- Jumelage fait via le menu : `soundOutput` passé de `tv_speaker` à **`bt_soundbar`** (vu en direct via SSAP).
- La Sonos garde le BT actif en permanence.
- Boot à froid (projecteur débranché) : le jumelage et la sortie mémorisée survivent ; la
  tentative de reconnexion part très tôt au boot — la Sonos doit être prête (allumée, BT actif)
  à ce moment. Sinon retombe sur `tv_speaker` d'où l'impression de devoir tout refaire.
- Test en cours : boot à froid avec Sonos prête → vérifier si la reconnexion est automatique.

### Tests de reconnexion (2026-10-25, verifié en direct via SSAP)
- **Boot à froid (débranché) : PAS de reconnexion automatique** — sortie restée sur
  `tv_speaker` 100 s après redémarrage, Sonos prête. C'est un comportement LG webOS :
  les barres tierces ne se reconnectent pas seules après un cold boot.
- `ssap://audio/changeSoundOutput` avec `{"output": "bt_soundbar"}` répond
  `returnValue: true` → **déclencheur à distance possible** (utile pour un futur script
  « reconnexion 1 clic »), mais sur cet essai la connexion BT ne s'est pas établie
  (côté Sonos : vérifier que la barre est en source Bluetooth au moment T).
- Contournement retenu : 2 clics dans Sortie sonore, ou surveillance à distance SSAP.

### Alternative plus fiable : HDMI eARC
Le CineBeam Q a un port HDMI avec **eARC** ; les Sonos Ray/Beam G2/Arc/Arc Ultra l'ont
aussi. Un câble HDMI entre les deux supprime totalement le problème de reconnexion
(connexion permanente, pas de latence, meilleure qualité). Le Bluetooth reste utile si
le câblage gêne ; notre débloat n'interfère pas avec l'un ni l'autre.

### Conclusion du test (2026-10-25, avec Sonos en source BT)
- `changeSoundOutput` met a jour le reglage persiste mais **ne declenche pas la connexion
  BT en direct** — l'action interne des menus LG reste necessaire.
- **Limite firmware confirmee** : reconnexion BT tierce non automatique au boot a froid.
- Rituel retenu : a chaque allumage, Parametres -> Son -> Sortie sonore -> Sonos (2 clics,
  jumelage retenu).
- A verifier par l'utilisateur : presence d'une option « connexion automatique » sur la
  fiche de l'appareil dans le gestionnaire Bluetooth (libelles variables selon firmware).
- Piste non exploree : lancement direct de la page reglages via
  `ssap://com.webos.applicationManager/launch` (deep-link) pour reduire le rituel.

## 9. Session de debugging SSAP (2026-10-25 soir) — trouvailles decisives

### Les services reellement exposes (ssap://api/getServiceList)
```
api, audio, config, externalpq, media.controls, media.viewer, pairing,
settings, system, system.launcher, system.notifications, timer, tv, user, webapp
```
Un manifeste de permissions plus large **n'elargit pas** cette liste : elle est figee
par le profil d'appairage. Les services `com.webos.service.bluetooth*` sont donc
**inaccessibles** — aucun endpoint de connexion BT direct n'existe pour nous.

### Les deux noms de sortie Bluetooth (tous deux valides !)
| Nom | Effet observe |
|---|---|
| `bt_soundbar` | accepte, etat passe a `bt_soundbar` (a fonctionne a 21:47) |
| `bt_audio` | accepte, etat passe a `bt_audio` ~9 s puis **annule** si la barre refuse |

Noms refuses : `external_bluetooth`, `bluetooth`, `bt`, `external_bt`,
`bluetooth_soundbar`, `bt_speaker`, `external_bluetooth_speaker`.

### Le mecanisme d'annulation (la vraie cause)
Surveillance des deux canaux en parallele (`settings/getSystemSettings` et
`audio/getStatus`) :
```
+3s   setting=bt_audio    actif=tv_speaker
+9s   setting=bt_audio    actif=tv_speaker
+12s  setting=tv_speaker  actif=tv_speaker   <-- annulation automatique
```
Le projecteur : accepte l'ordre -> tente la connexion BT -> echoue (la barre Sonos
n'ecoute pas) -> **annule le reglage** au bout de ~10 s. D'ou l'impression qu'il faut
tout refaire a la main.

### Le service `settings` (cle pour lire, mais pas pour ecrire)
- `ssap://settings/getSystemSettings {category, keys}` ✅ **fonctionne** (lecture)
  - `settings/soundOutput` et `settings/soundMode` sont des cles autorisees
- `ssap://settings/setSystemSettings` ❌ **401 insufficient permissions**

### Ce qui marche / ne marche pas
| Canal | Etat |
|---|---|
| `createToast` | ✅ le projecteur affiche nos messages |
| Touches `VOLUMEUP`/`VOLUMEDOWN` | ✅ recues (volume 51 -> 54) |
| Touches directionnelles (RIGHT/DOWN/ENTER) | ⚠️ envoyees sans effet visible |
| Curseur souris (`type:move`/`click`/`down`+`up`) | ❌ aucun pointeur affiche |
| `changeSoundOutput` (apiadapter) | ✅ declenche, mais annule si Sonos pas prete |
| Contournement alerte -> luna | ❌ `isCallAllowed reply returnValue false` |
| Capture d'ecran `executeOneShot` | ✅ ecrit un JPEG sur le projecteur, ❌ non telechargeable (pas de SSH) |

### Conclusion operationnelle
La reconnexion BT est **possible par API** et reussit en ~4 s **quand la barre Sonos est
en source Bluetooth**. Sinon le projecteur annule apres 10 s. Le watcher m720q retente
4 fois par cycle, cible `bt_audio`, et journalise chaque tentative.

## 10. Solution retenue : reconnexion auto par rejeu du menu (2026-10-25 23:19, validee)

- Sonos = **Arc Ultra** `192.168.1.139` (nom BT : `Living Room (SONOS XXXX)`). Pas de cable HDMI
  vers le projecteur (`HDMI_1 connected:false`), donc pas d'eARC.
- Cause : apres un boot a froid le lien BT n'existe pas ; `changeSoundOutput` ne change que le
  reglage (puis le projecteur l'annule). Seul le bouton **Connect** du menu ouvre le lien.
  `bt_soundbar` est le bon nom de sortie (pas `bt_audio`).
- Les touches telecommande via `getPointerInputSocket` **fonctionnent** (`type:button\nname:DOWN\n\n`),
  et `ssap://tv/executeOneShot` + telechargement de `imageUri` donne une capture d'ecran.
- `com.webos.app.btspeakerapp` = **Sound Share** (mauvais ecran, ne pas utiliser).
- Sequence (depuis `com.palm.app.settings`, focus Picture) :
  `DOWN ENTER RIGHT DOWN ENTER DOWN DOWN ENTER RIGHT ENTER DOWN ENTER DOWN ENTER`, puis `EXIT`
  = Sound → Sound Out → Use Wireless Speaker → ⋮ → Living Room (SONOS XXXX) → Connect.
- Watcher m720q (`~/sonos-watcher/sonos-watcher.py`, copie dans `scripts/`) : une seule
  reconnexion par allumage (un choix manuel ensuite est respecte), 4 essais.
- Test boot reel 23:19 : essai 2 (essai 1 trop tot) ; delai passe de 3 a 7 s, puis cycle extinction API + Wake-on-LAN (MAC aa:bb:cc:00:00:01) a 23:21 : **connecte des l essai 1** (23:22:43).
- Limite : la sequence depend de l'ordre des menus et de la Sonos en 1re position des
  appareils enregistres. Apres une mise a jour webOS ou un nouvel appareil BT, revalider.

## 11. Meilleure methode : connexion A2DP directe via luna (2026-10-25 23:32, validee)

Trouvee en lisant `brunofgmag/lgtv-control-mcp` (`lunaRequest`) : une alerte creee par
`ssap://system.notifications/createAlert` dont le `onclose` pointe vers un `luna://...`, puis
fermee par `closeAlert`, execute l'appel luna. **Fonctionne sur ce webOS 24** (toast de test
affiche). L'echec note au §9 venait de la variante « clic sur le bouton ».

- Appel : `luna://com.webos.service.bluetooth2/a2dp/connect {"address": "aa:bb:cc:00:00:a9"}`
  (adresse BT de l'Arc Ultra = sa MAC Wi-Fi), puis 6 s apres `changeSoundOutput bt_soundbar`.
- Temoin apres extinction + Wake-on-LAN : adresse fausse `...:a8` → reste `tv_speaker` ;
  bonne adresse `...:a9` → `bt_soundbar` stable.
- Watcher : 2 essais luna, puis 2 essais menu (§10) en secours si LG ferme l'astuce.
  Test reel : connectee 9 s apres le warmup, sans aucun menu a l'ecran.
- Extinction/allumage a distance : `ssap://system/turnOff` + Wake-on-LAN sur `aa:bb:cc:00:00:01`.

## 12. Popup de confirmation "wants to connect" (2026-10-25 23:49, valide)

- Apres `a2dp/connect` (luna), la Sonos repond par une demande que le projecteur affiche :
  « [Living Room (SONOS XXXX)] wants to connect to your Projector... » **Yes / No** (focus sur Yes).
  Sans validation, `soundOutput` peut afficher `bt_soundbar` mais le son reste sur le projecteur
  (faux positif de l'ancienne version).
- Watcher : capture `executeOneShot` toutes les 2 s ; si les pixels du popup correspondent
  (No (125,132,140), Yes (230,230,230), fond (202,203,205)), touche ENTER, puis
  `changeSoundOutput bt_soundbar`. Pas d'ENTER a l'aveugle (sinon ouverture de l'app focus).
- Pillow installe dans `~/.venvs/sonos-watcher` (wheel PyPI dezippee, pas de pip).
- Test extinction + WoL : popup detecte 5 s apres, Yes, connecte, toast « is connected ».
- Note : la Sonos qui lance une autre source (radio Sonos) coupe le BT ; le watcher ne
  reconnecte qu'une fois par allumage pour ne pas voler la Sonos.
