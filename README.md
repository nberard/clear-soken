# Clear Soken

Une appli web installable (PWA) pour les patients hospitalisés en psychiatrie. Elle les aide à prendre soin d'eux pendant le séjour, puis à reprendre contact avec la vie sociale après la sortie.

Le patient scanne un QR code affiché dans le service : l'appli s'ouvre et s'installe sur l'écran d'accueil. Pas de store, pas de compte.

## Fonctionnalités (V1)

| Écran | Rôle |
|---|---|
| **Accueil** | Résumé du jour, invitation à installer l'appli |
| **Humeur** | Météo intérieure en un geste + note libre, frise de la semaine |
| **Respirer** | Cohérence cardiaque guidée (2 ou 5 min), exercice d'ancrage 5-4-3-2-1 |
| **Ma voix** | Mémos vocaux en un geste : enregistrer, réécouter, renommer, partager. Raccourci « Enregistrer » sur l'icône de l'appli (appui long) |
| **Échelons** | Petits pas en 4 paliers (soin de soi → autres → lien → sortie), personnalisables |
| **Ressources** | Annuaire : écoute, GEM, Clubhouse, CMP, proches… |
| **Trouver un centre** | Addictions (alcool, cannabis, cocaïne, opioïdes, tabac, jeux…) : le centre le plus adapté autour de moi (GPS) ou de mon futur chez-moi (adresse, ville, ou un lieu de « Ma sortie »). Appeler, itinéraire, lignes d'écoute |
| **Besoin d'aide** | Toujours accessible : soignants, 3114, 15, 112, SMS 114. Effacement des données |

L'appli fonctionne hors ligne grâce au service worker.

## Confidentialité

**Aucune donnée de santé n'est envoyée au serveur.** L'humeur et les échelons sont stockés uniquement sur le téléphone (`localStorage`), les mémos vocaux aussi (IndexedDB). Ils ne quittent le téléphone que si le patient choisit de les partager. Le serveur ne sert que l'appli et l'annuaire public, et Caddy ne journalise pas les adresses IP.

« Trouver un centre » suit la même règle : l'annuaire des centres est téléchargé en entier et trié **sur le téléphone**. Ni la position, ni le motif de la recherche ne sont envoyés au serveur. Seule une adresse tapée à la main part vers le géocodeur public de l'IGN (`data.geopf.fr`), sans référent ni motif.

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
docker login ghcr.io -u nberard   # une seule fois (voir « Image Docker » ci-dessous)
make deploy    # télécharge l'image et démarre Clear Soken (quelques secondes)
```

Vérifie : https://clearsoken.touplitoui.me (le certificat peut prendre une minute).

### Au quotidien

| Commande | Effet |
|---|---|
| `make deploy` | télécharge la dernière image (construite par GitHub Actions) et redémarre ; si ghcr.io est inaccessible, construit l'image sur le serveur |
| `make deploy TAG=sha-abc1234` | revient à la version d'un commit précis |
| `make update` | `git pull` (compose, `.env.example`) puis `make deploy` |
| `make build-local` | secours : construit l'image sur le serveur (plusieurs minutes) |
| `make restart` | après modification de `backend/data/resources.json` ou `centres-equipe.json` |
| `make centres` | met à jour l'annuaire des centres d'addictologie (FINESS) |
| `make logs` | journaux de l'appli |
| `make proxy` | après modification de `proxy/Caddyfile` ou `proxy/.env` |
| `make portal-update` | publie la dernière version du portal (clearmind.studio) |
| `make proxy-check` | vérifie la config Caddy avant de recharger (sans couper les sites) |
| `make qr` | QR code à afficher dans le service (`sudo apt install qrencode`) |

Pour ajouter un autre site plus tard : un nouveau bloc dans `proxy/Caddyfile`, le conteneur sur le réseau `proxy`, puis `make proxy`.

### Annuaire des centres d'addictologie

`make centres` télécharge le fichier FINESS (data.gouv.fr) et écrit `backend/data/centres.json` : tous les CSAPA, consultations jeunes consommateurs et CAARUD de France, avec leurs coordonnées (métropole et outre-mer). `make deploy` le génère la première fois ; relance `make centres` de temps en temps (FINESS est mis à jour tous les deux mois). Le fichier n'est pas versionné.

Les lieux que l'équipe recommande (consultation hospitalière, groupe de parole, SMR addictologie…) se mettent à la main dans `backend/data/centres-equipe.json`, puis `make restart`. Ils sont marqués « Conseillé par l'équipe » et remontent dans le classement :

```json
[{ "id": "chu-addicto", "nom": "Unité d'addictologie du CHU", "type": "autre", "adresse": "Bd de la Chantourne",
   "cp": "38700", "ville": "La Tronche", "tel": "04 76 00 00 00", "lat": 45.2, "lon": 5.75,
   "specialites": ["alcool"], "note": "Demander à l'équipe pour un rendez-vous rapide." }]
```

`type` : `csapa`, `cjc`, `caarud` ou `autre`. `specialites` (facultatif) : `alcool`, `cannabis`, `cocaine`, `opioides`, `tabac`, `jeux`, `autre`. Coordonnées : clic droit sur le lieu dans une carte.

### Image Docker (GitHub Actions → ghcr.io)

Le serveur ne compile rien. À chaque fusion dans `main`, GitHub Actions (`.github/workflows/image.yml`) lance les tests
(front et API), construit l'image et la publie sur GitHub Container Registry :

- `ghcr.io/nberard/clear-soken:latest` : dernière version de `main` ;
- `ghcr.io/nberard/clear-soken:sha-<commit>` : chaque version, pour revenir en arrière.

Sur une PR, l'image est construite (pour vérifier qu'elle compile) mais pas publiée.

**Une seule fois sur le serveur** : crée un jeton GitHub (Settings → Developer settings → Personal access tokens →
Tokens (classic), droit `read:packages` uniquement), puis `docker login ghcr.io -u nberard` avec ce jeton comme mot de
passe. Docker le garde dans `~/.docker/config.json`.

Secours sans GitHub Actions : `make build-local` sur le serveur, ou `make push` depuis ton PC (après `docker login ghcr.io`).

## À côté : tableau de bord santé perso (`mint-health/`)

Projet séparé, sans lien avec l'appli patients : synchro de **mes** données Google Health, Grafana et applet Linux Mint, publiés sur `https://health.touplitoui.me` derrière un mot de passe. Il n'entre pas dans l'image Docker de Clear Soken (`.dockerignore`) et le site Caddy n'est activé que par `make health-proxy`. Voir [`mint-health/README.md`](mint-health/README.md).

## À côté : Clearmind portal (site public)

La page publique `https://clearmind.studio` (dépôt [`kraken-portal`](https://github.com/nberard/kraken-portal) :
Instagram, Twitch, YouTube, et un bouton + QR code vers les rapports privés) est servie par le même Caddy,
directement depuis un clone du dépôt sur le serveur.

1. **DNS** : enregistrements **A** `clearmind.studio` et `www.clearmind.studio` vers l'IP du serveur (si le domaine
   pointe encore vers un autre hébergeur, le site y restera tant que le DNS n'est pas changé).
2. Dans `proxy/.env` : `PORTAL_HOST=clearmind.studio` et `PORTAL_DIR=/home/nico/dev/kraken-portal`.
3. `make portal-proxy` : clone le portal s'il n'est pas là, vérifie la config, recharge Caddy.
4. Mise à jour du contenu : `make portal-update` (simple `git pull`, sans redémarrage).

Le dossier `.git` et les fichiers de configuration du clone ne sont jamais servis.

## À côté : rapports Clearmind (site privé, perso)

Projet séparé, sans lien avec l'appli patients : les rapports d'activité produits par
[`clearmind-tools`](https://github.com/nberard/clearmind-tools) (`social_analytics/site_rapports.py`), consultables
sur `https://rapports.touplitoui.me/<lien secret>/`, sans mot de passe : seule l'adresse secrète ouvre le site. Le serveur ne reçoit **que les rapports** (HTML, PDF) :
les exports bruts restent sur le PC. Caddy sert simplement le dossier, sans journal d'accès et avec `noindex`.

```
PC : python site_rapports.py publier ──rsync/SSH──► serveur : /home/nico/clearmind-rapports ──► Caddy (lien secret) ──► rapports.touplitoui.me
```

### Mise en place (une fois)

1. **DNS** : enregistrement **A** `rapports.touplitoui.me` vers l'IP du serveur.
2. **Activer le site** : `git pull && make rapports-proxy`. La commande crée le lien secret (40 caractères
   aléatoires, dans `proxy/.env`), vérifie la config (`make proxy-check`) avant de recharger Caddy, puis **affiche le
   lien**. Toute autre adresse du sous-domaine répond 404.
3. **Sur le PC**, dans `clearmind-tools/social_analytics/.env` : `RAPPORTS_URL=<le lien affiché>` et
   `RAPPORTS_SERVEUR=nico@IP_DU_SERVEUR:/home/nico/clearmind-rapports`, puis `python site_rapports.py publier`.

| Commande | Effet |
|---|---|
| `make rapports-lien` | réaffiche le lien |
| `make rapports-qr` | QR code du lien (`qr-rapports.png` et dans le terminal) |
| `make rapports-nouveau-lien` | nouveau lien si l'ancien a circulé : l'ancien cesse aussitôt de marcher (mettre à jour `RAPPORTS_URL` sur le PC) |

Le lien donne accès à tout : ne le partage qu'avec qui doit lire les rapports (soignant). Il n'est transmis à aucun
site ouvert depuis un rapport (`Referrer-Policy: no-referrer`), n'apparaît dans aucun journal et le site n'est pas
indexé.

## Ma sortie (`/sortie/`)

Préparer une sortie de clinique, d'une semaine thérapeutique à plusieurs mois, **avec l'équipe soignante** :

1. **Le cadre** : date de sortie, attentes, durée totale, fréquence de changement de lieu.
2. **Les séjours** : pour chacun, ce qu'on y cherche (repos, sport, être entouré·e, nature, créer), le cadre, avec qui,
   le budget. L'appli prépare une **recherche Airbnb pré-remplie** (dates, budget, chambre chez l'habitant) : Airbnb
   n'ouvre pas la réservation aux applis tierces, c'est la personne qui réserve. Liens vers le CMP et les urgences
   psychiatriques proches de chaque lieu.
3. **Le filet de sécurité** : rendez-vous de suivi, traitement et ordonnance pour toute la durée, personne de
   confiance, signes d'alerte et ce qui aide, numéros d'urgence (3114, 15, 112).
4. **Le document pour le psychologue et le psychiatre** (`/sortie/export/`) : le plan, et en option l'humeur des
   30 derniers jours ; à imprimer ou à enregistrer en PDF. Il signale ce qui manque encore.

Comme le reste de l'appli, **tout reste sur le téléphone** : rien n'est envoyé au serveur. La logique est testée
sans navigateur : `cd frontend && npm test`.

## Prix des plans (`.env`)

Un seul prix de référence, par jour, dans `.env` à la racine (copie de `.env.example`). L'API calcule le
reste et le sert sur `/api/plans` ; la page `/offres/` l'affiche.

| Variable | Défaut | Rôle |
|---|---|---|
| `PRIX_JOUR_CENTIMES` | 2 | prix Premium par jour, en centimes |
| `ESSAI_JOURS` | 30 | essai gratuit de Premium |
| `REMISE_ANNUELLE_PCT` | 0 | remise sur le paiement annuel |
| `PRIX_PAQUET_CENTIMES` | 1300 | prix d'un paquet de cigarettes, pour la comparaison (humoristique) de `/offres/` |

Mois = jour × 365 / 12, an = jour × 365 − remise, arrondis au centime (2 → 0,61 €/mois, 7,30 €/an).
Free et Dev sont gratuits. Après un changement : `make deploy`. Aucun paiement n'est branché pour l'instant.

## Pistes V2

- Communauté d'anciens patients (groupes modérés, parrainage) : nécessite HDS, modération et protocole de crise
- Planning du service (ateliers, visites) saisi par l'équipe
- Annuaire géolocalisé par secteur (GEM, CMP, associations)
- Export PDF du journal d'humeur à montrer au psychiatre
- Notifications douces (rappel respiration, échelon du jour)

> Les ressources de l'annuaire sont des exemples nationaux. Elles doivent être validées par l'équipe soignante avant diffusion.
