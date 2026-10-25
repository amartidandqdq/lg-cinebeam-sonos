# Réglages à faire au projecteur (sans root, sans outil)

Menu LG CineBeam Q (webOS 24) — libellés FR. Si un libellé diffère, dis-le, on
le retrouve ensemble ; ne change rien que tu ne reconnais pas.

## 1. Accueil
- Paramètres → Général → Paramètres supplémentaires → **Paramètres de l'écran
  d'accueil** : désactiver **Promotion de l'écran d'accueil** et **Recommandation
  de contenu**.
- Sur l'écran d'accueil : **Modifier** → retirer les tuiles LG Channels, Sports,
  « Découvrir », jeux, etc. Garder seulement tes apps + entrées HDMI.
- Si **LG Channels** n'est pas utilisé : le désactiver (Paramètres → Chaînes).

## 2. Confidentialité
- Paramètres → Support → **Confidentialitité et conditions** (ou Général →
  Confidentialité) :
  - désactiver **Informations de visionnage**
  - désactiver **Recommandations basées sur les centres d'intérêt**
  - désactiver **Publicité personnalisée**
  - désactiver **Reconnaissance de contenu (ACR)** si présent
- Ne pas désactiver « Conditions d'utilization » (nécessaire aux mises à jour).

## 3. Comportement
- Désactiver **Démarrage rapide+** seulement si tu veux couper l'état de veille
  réseau (sinon le projecteur reste joignable et relance les services pub).
- Désactiver **Sports Alert** / **Alerte de sport**.
- Écran de veille : choisir l'horloge ou le logo, pas les visuels promotionnels.
- Désactiver **Mise à jour auto** si tu veux figer le firmware (sinon laisser).

## Vérification
Après reboot : l'accueil doit être une grille sans bandeau pub, et
`ps | grep -E 'admanager|contentminer|nudge'` doit être vide (si accès shell).