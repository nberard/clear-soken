# Clear Soken

Une appli web installable (PWA) pour les patients hospitalisés en psychiatrie. Elle les aide à prendre soin d'eux pendant le séjour, puis à reprendre contact avec la vie sociale après la sortie.

Le patient scanne un QR code affiché dans le service : l'appli s'ouvre et s'installe sur l'écran d'accueil. Pas de store, pas de compte.

## Fonctionnalités (V1)

| Écran | Rôle |
|---|---|
| **Accueil** | Résumé du jour, invitation à installer l'appli |
| **Humeur** | Météo intérieure en un geste + note libre, frise de la semaine |
| **Respirer** | Cohérence cardiaque guidée (2 ou 5 min), exercice d'ancrage 5-4-3-2-1 |
| **Échelons** | Petits pas en 4 paliers (soin de soi → autres → lien → sortie), personnalisables |
| **Ressources** | Annuaire : écoute, GEM, Clubhouse, CMP, proches… |
| **Besoin d'aide** | Toujours accessible : soignants, 3114, 15, 112, SMS 114. Effacement des données |

L'appli fonctionne hors ligne grâce au service worker.

## Confidentialité

**Aucune donnée de santé n'est envoyée au serveur.** L'humeur et les échelons sont stockés uniquement sur le téléphone (`localStorage`). Le serveur ne sert que l'appli et l'annuaire public, et Caddy ne journalise pas les adresses IP.

Conséquence : la V1 n'a pas besoin d'un hébergeur certifié **HDS**. Dès que des données patient seront stockées côté serveur (comptes, communauté, partage avec les soignants), il faudra :
- un hébergement HDS (OVH propose des offres dédiées) ;
- une analyse d'impact RGPD (AIPD) ;
- l'accord de l'établissement.

## Architecture

```
frontend/   SvelteKit 3 + TypeScript, rendu statique (adapter-static), PWA
backend/    Rust (Axum) : sert la PWA + /api/health, /api/resources
  data/resources.json   annuaire (modifiable sans recompiler)
Dockerfile, docker-compose.yml   image et conteneur de l'appli
proxy/      reverse proxy Caddy commun au serveur (HTTPS auto, plusieurs domaines)
```

**Pour le design :** les couleurs, typos et arrondis sont tous dans `frontend/src/lib/theme.css` (thèmes clair et sombre). Les icônes de l'appli sont dans `frontend/static/icons/`. Pour régénérer les PNG : `node scripts/render-icons.cjs`.

## Développer

```bash
make dev-api     # terminal 1 — API sur :8080
make dev-web     # terminal 2 — PWA sur :5173
make test        # typecheck + tests Rust
```

Prérequis : Node 22, Rust stable.

## Déployer sur le serveur OVH

Un seul **Caddy** écoute sur les ports 80/443 du serveur. Il obtient les certificats HTTPS et envoie chaque domaine au bon conteneur :

```
Internet ──► Caddy (80/443) ──► clearsoken.touplitoui.me ──► conteneur clearsoken:8080
```

### 1. DNS

Chez ton registrar, crée un enregistrement **A** `clearsoken.touplitoui.me` vers l'IP du serveur.

### 2. Ports 80/443 libres

Rien d'autre ne doit écouter sur 80/443 : `sudo ss -tlnp | grep -E ':(80|443) '` ne doit rien afficher.

### 3. Lancer le proxy puis l'appli

```bash
cd /home/nico/dev
git clone https://github.com/nberard/clear-soken && cd clear-soken
cp proxy/.env.example proxy/.env && nano proxy/.env   # ton email
make proxy     # Caddy (crée aussi le réseau Docker "proxy")
make deploy    # build + démarrage de Clear Soken (quelques minutes la 1re fois)
```

Vérifie : https://clearsoken.touplitoui.me (le certificat peut prendre une minute).

### Au quotidien

| Commande | Effet |
|---|---|
| `make update` | `git pull` + rebuild + redémarrage |
| `make restart` | après modification de `backend/data/resources.json` |
| `make logs` | journaux de l'appli |
| `make proxy` | après modification de `proxy/Caddyfile` ou `proxy/.env` |
| `make proxy-check` | vérifie la config Caddy avant de recharger (sans couper les sites) |
| `make qr` | QR code à afficher dans le service (`sudo apt install qrencode`) |

Pour ajouter un autre site plus tard : un nouveau bloc dans `proxy/Caddyfile`, le conteneur sur le réseau `proxy`, puis `make proxy`.

### Optionnel : Docker Hub

Si le serveur est lent à compiler, construis l'image sur ton PC et publie-la : `docker login` puis `make push` (image `touplitoui/clear-soken`, à créer en **privé** sur Docker Hub). Sur le serveur, remplace `build: .` par `image: touplitoui/clear-soken:latest` dans `docker-compose.yml`, puis `docker compose pull && docker compose up -d`.

## À côté : tableau de bord santé perso (`mint-health/`)

Projet séparé, sans lien avec l'appli patients : synchro de **mes** données Google Health, Grafana et applet Linux Mint, publiés sur `https://health.touplitoui.me` derrière un mot de passe. Il n'entre pas dans l'image Docker de Clear Soken (`.dockerignore`) et le site Caddy n'est activé que par `make health-proxy`. Voir [`mint-health/README.md`](mint-health/README.md).

## À côté : rapports Clearmind (site privé, perso)

Projet séparé, sans lien avec l'appli patients : les rapports d'activité produits par
[`clearmind-tools`](https://github.com/nberard/clearmind-tools) (`social_analytics/site_rapports.py`), consultables
sur `https://rapports.touplitoui.me` derrière un mot de passe. Le serveur ne reçoit **que les rapports** (HTML, PDF) :
les exports bruts restent sur le PC. Caddy sert simplement le dossier, sans journal d'accès et avec `noindex`.

```
PC : python site_rapports.py publier ──rsync/SSH──► serveur : /home/nico/clearmind-rapports ──► Caddy (mot de passe) ──► rapports.touplitoui.me
```

### Mise en place (une fois)

1. **DNS** : enregistrement **A** `rapports.touplitoui.me` vers l'IP du serveur.
2. **Mot de passe** : `docker run --rm caddy:2 caddy hash-password --plaintext 'ton-mot-de-passe'`, puis dans
   `proxy/.env` : `RAPPORTS_HOST`, `RAPPORTS_AUTH_USER`, `RAPPORTS_AUTH_HASH` (entre apostrophes) et
   `RAPPORTS_DIR=/home/nico/clearmind-rapports` (voir `proxy/.env.example`).
3. **Activer le site** : `git pull && make rapports-proxy`. La config est vérifiée (`make proxy-check`) avant de
   recharger Caddy, pour ne jamais couper l'appli patients sur une erreur.
4. **Sur le PC**, dans `clearmind-tools/social_analytics/.env` :
   `RAPPORTS_SERVEUR=nico@IP_DU_SERVEUR:/home/nico/clearmind-rapports`, puis `python site_rapports.py publier`.

Le QR code du site est dans `site/qr.png` côté PC, ou `make rapports-qr` côté serveur. Il mène à la page de
connexion : sans le mot de passe, il ne donne accès à rien.

## Pistes V2

- Communauté d'anciens patients (groupes modérés, parrainage) : nécessite HDS, modération et protocole de crise
- Planning du service (ateliers, visites) saisi par l'équipe
- Annuaire géolocalisé par secteur (GEM, CMP, associations)
- Export PDF du journal d'humeur à montrer au psychiatre
- Notifications douces (rappel respiration, échelon du jour)

> Les ressources de l'annuaire sont des exemples nationaux. Elles doivent être validées par l'équipe soignante avant diffusion.
