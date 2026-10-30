# Mint Health — Google Health × Grafana dans la barre des tâches Linux Mint

```
 Google Health API ──OAuth──▶ sync (FastAPI, :8765) ──▶ PostgreSQL ──▶ Grafana (:3000)
 Google Fit / Health Connect ─(appli HC Webhook)─▲
                                   ▲                                     │  ▲
                                   │ /status, /auth, /sync          PNG  │  │ kiosque
                                   └──────── Applet Cinnamon ◀───────────┘  │
                                              └── fenêtre transparente ─────┘
```

- **sync** : connexion à ton compte Google (OAuth + PKCE), synchro toutes les 15 min des agrégats quotidiens (`dailyRollUp`) et des nuits de sommeil, stockage dans Postgres.
- **Health Connect** (option) : les données de Google Fit, Samsung Health, montres… arrivent depuis le téléphone Android via l'appli « HC Webhook ». Voir [Google Fit et Health Connect](#google-fit-et-health-connect-téléphone-android).
- **Grafana** : datasource et dashboard « Google Health » provisionnés automatiquement, panneaux transparents, consultation anonyme en lecture seule, embedding autorisé, rendu PNG.
- **Journal vocal** : un clic pour enregistrer un mémo depuis la barre des tâches (applet), le téléphone Android (page web à ajouter à l'écran d'accueil) ou le navigateur ; tout arrive au même endroit et apparaît dans Grafana. Voir [Journal vocal](#journal-vocal).
- **Applet Cinnamon** : pas du jour dans la barre, menu avec résumé + mini-graphique Grafana, bouton de connexion du compte, et dashboard complet dans une fenêtre sans bordure translucide ancrée au panneau.

Tout tourne en local et n'écoute que sur `127.0.0.1`.

> **Pourquoi la Google Health API ?** C'est l'API cloud qui remplace la Fitbit Web API (coupée le 2 novembre 2026) ; l'API Google Fit REST s'arrête fin 2026. Elle couvre les données Fitbit, Pixel Watch et Google Health.

## 1. Créer les identifiants Google (une seule fois)

1. [console.cloud.google.com](https://console.cloud.google.com) → nouveau projet (ex. `mint-health`).
2. **API et services → Bibliothèque** → active **Google Health API**.
3. **Écran de consentement OAuth** : type *Externe*, statut *Test*, ajoute ton adresse Gmail dans **Utilisateurs test**. Ajoute les scopes `googlehealth.activity_and_fitness.readonly`, `googlehealth.health_metrics_and_measurements.readonly`, `googlehealth.sleep.readonly`.
4. **Identifiants → Créer → ID client OAuth** : type **Application Web**, URI de redirection autorisée :
   `http://localhost:8765/auth/callback`
5. Copie l'ID client et le secret.

> En statut *Test*, Google fait expirer le jeton de rafraîchissement au bout de 7 jours : l'applet affiche alors « Compte non connecté », il suffit de recliquer sur « Connecter ». Pour un usage perso durable, passe l'app en production (une vérification Google peut être demandée pour les scopes santé).

## 2. Lancer les services

```bash
sudo apt install docker.io docker-compose-v2   # si Docker n'est pas installé
sudo usermod -aG docker $USER                   # puis déconnexion/reconnexion

cp .env.example .env
nano .env          # GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, les 3 mots de passe et RENDERER_TOKEN (openssl rand -hex 32)
docker compose up -d --build
```

Vérification : `curl localhost:8765/status` doit répondre `{"connected": false, ...}` et Grafana est sur <http://localhost:3000> (admin / `GRAFANA_ADMIN_PASSWORD`).

## 3. Installer l'applet

```bash
./install-applet.sh
```

Puis clic droit sur la barre des tâches → **Applets** → **Google Health** → **+**.
Clique sur l'icône cœur → **Connecter mon compte Google Health…** : le navigateur s'ouvre, tu acceptes, la synchro des 90 derniers jours démarre.

Dans le menu :

| Action | Effet |
|---|---|
| Tableau de bord (fenêtre transparente) | Ouvre/ferme Grafana en mode kiosque au-dessus du panneau (Échap pour fermer, F5 pour recharger) |
| Ouvrir Grafana dans le navigateur | Dashboard complet, éditable |
| Synchroniser maintenant | Force une synchro |
| Déconnecter le compte Google | Révoque le jeton côté Google et le supprime localement |

Réglages de l'applet (clic droit → Configurer) : valeur affichée dans la barre, panneau Grafana du mini-graphique (ID 10 = pas par jour, 11 = sommeil…), taille et opacité de la fenêtre, fermeture auto.

## Déployer sur le serveur OVH (`https://health.touplitoui.me/health`)

Le tableau de bord tourne à côté de Clear Soken, derrière le même Caddy, sur un sous-domaine à part et protégé par mot de passe. L'appli patients n'est pas touchée : ses conteneurs, son image Docker et son domaine restent séparés.

```
Internet ─► Caddy ─► health.touplitoui.me  (mot de passe)
                       ├─ /health/api/*  ─► mint-health-sync:8765
                       └─ /health/*      ─► mint-health-grafana:3000
```

1. **DNS** : `health.touplitoui.me` doit pointer vers l'IP du serveur (couvert par l'enregistrement joker `*` chez Namecheap).
2. **Google Cloud** : dans l'ID client OAuth, ajoute l'URI de redirection
   `https://health.touplitoui.me/health/api/auth/callback`,
   et `touplitoui.me` dans les **domaines autorisés** de l'écran de consentement.
3. **Mot de passe** du sous-domaine :
   ```bash
   docker run --rm caddy:2 caddy hash-password --plaintext 'ton-mot-de-passe'
   ```
   Dans `proxy/.env`, renseigne `HEALTH_HOST`, `HEALTH_AUTH_USER` et `HEALTH_AUTH_HASH='<hash>'` (avec les apostrophes).
4. **Services** : dans `mint-health/.env` (copié depuis `.env.example`), mets le même `HEALTH_HOST`, puis à la racine du dépôt :
   ```bash
   make health-deploy   # synchro + Postgres + Grafana
   make health-proxy    # active le sous-domaine dans Caddy (HTTPS automatique)
   ```
5. Ouvre `https://health.touplitoui.me/health/api/auth/start` pour connecter ton compte Google, puis `https://health.touplitoui.me/health/`.

**Applet sur ton PC** (clic droit → Configurer) : URL du service `https://health.touplitoui.me/health/api`, URL de Grafana `https://health.touplitoui.me/health`, et ton identifiant et mot de passe. Ils sont stockés dans un fichier privé (`~/.cache/google-health-applet/curl-auth.conf`, droits 600), jamais passés en argument de commande.

Sur le serveur, Grafana n'a ni formulaire de connexion ni authentification propre : c'est Caddy qui protège tout l'hôte. Les données restent sur ton serveur OVH ; pour un tableau de bord personnel ce n'est pas un hébergement HDS, mais il ne faut pas y mettre de données de patients.

## Google Fit et Health Connect (téléphone Android)

L'API Google Fit est fermée aux nouveaux projets depuis 2024 et s'arrête en 2026. On passe donc par **Health Connect**, le coffre santé d'Android dans lequel Google Fit (et Samsung Health, Withings, les montres…) écrit ses données. L'appli open source **HC Webhook** les envoie à ton serveur toutes les 15 min.

```
Google Fit ─▶ Health Connect ─▶ HC Webhook ──HTTPS + jeton──▶ health.touplitoui.me/health/api/ingest/health-connect
 (téléphone)                     (téléphone)                     └─▶ sync ─▶ PostgreSQL ─▶ Grafana / applet
```

Fonctionne avec le déploiement serveur (le téléphone doit joindre l'URL en HTTPS).

**Sur le serveur**

```bash
echo "HC_INGEST_TOKEN=$(openssl rand -hex 32)" >> mint-health/.env
grep HC_INGEST_TOKEN mint-health/.env        # note la valeur pour le téléphone
make health-deploy && make health-proxy
```

**Sur le téléphone**

1. **Google Fit** → Profil → ⚙️ → **Synchroniser Fit avec Santé Connect** : activé.
2. Installe **HC Webhook** depuis le Play Store (« Health Connect Webhook », `com.hcwebhook.app`) et accorde-lui l'accès en lecture aux types voulus (pas, distance, calories, fréquence cardiaque, sommeil, poids…).
3. **Webhooks → Ajouter** :
   - URL : `https://health.touplitoui.me/health/api/ingest/health-connect`
   - Format : **JSON**
   - En-tête personnalisé : `x-api-key` = la valeur de `HC_INGEST_TOKEN`
   - Touche **Test** : la réponse doit être `200`.
4. **Réglages** :
   - *Payload timestamps* : **Local time** (les jours sont calculés dans ton fuseau `TZ`).
   - Pas, distance, calories : résolution **Daily** ou **N minutes** avec **Count overlapping apps once** activé, pour ne pas compter deux fois les pas d'une montre et du téléphone.
   - Synchro : toutes les 15 min.

**Ce qui est importé**

| Health Connect | Métrique (même nom que Google Health) |
|---|---|
| `steps` | `steps.countSum` |
| `distance` | `distance.millimetersSum` |
| `total_calories` / `active_calories` | `total-calories.kcalSum` / `active-calories.kcalSum` |
| `heart_rate` | `heart-rate.beatsPerMinuteAvg` / `Max` / `Min` |
| `resting_heart_rate` | `daily-resting-heart-rate.beatsPerMinute` |
| `heart_rate_variability` | `daily-heart-rate-variability.rmssdMillis` |
| `weight` | `weight.kilograms` |
| `exercise` | `exercise.minutesSum` |
| `sleep` | table `sleep_sessions` (phases profond / léger / paradoxal) |

Les autres types sont ignorés (listés dans la réponse sous `ignored_types`). Les modifications et suppressions faites dans Health Connect sont prises en compte.

**Plusieurs sources** : si Google Health et Health Connect donnent tous deux une valeur pour le même jour, le tableau de bord et l'applet affichent celle de la première source de `SOURCE_PRIORITY` (par défaut `google-health,health-connect`). Les nuits qui se chevauchent sont dédoublonnées de la même façon. Pour n'utiliser que Google Fit, mets `SOURCE_PRIORITY=health-connect,google-health`, ou ne connecte pas Google Health.

### Historique ancien : import Google Takeout

Pour remplir le passé (avant la première synchro), exporte **Fit** avec [Google Takeout](https://takeout.google.com)
(format CSV), dépose les zips sur le serveur (ex. `~/takeout`), puis :

```bash
make health-takeout TAKEOUT=~/takeout ESSAI=1   # ce qui serait importé, sans rien écrire
make health-takeout TAKEOUT=~/takeout           # import
```

L'import lit `Fit/Métriques d'activité quotidiennes` directement dans les zips (rien à décompresser) : pas, distance,
calories, fréquence cardiaque moyenne / max / min et poids, jour par jour. Les valeurs ont la source `takeout`, absente
de `SOURCE_PRIORITY` donc toujours dernière : elles ne remplacent jamais celles de Google Health ou de Health Connect,
elles comblent seulement les jours vides. On peut relancer l'import sans risque (les valeurs sont mises à jour).

## Journal vocal

Dire une idée, une humeur, un rappel… en un geste, sur les trois plateformes. Les mémos arrivent tous dans le service de synchro et s'affichent dans Grafana.

```
 Applet Mint ──┐                                       ┌─▶ Grafana : minutes par jour, derniers mémos (lien « Écouter »)
 Téléphone ────┼──▶ sync /memos ──▶ fichiers audio ────┤
 Navigateur ───┘     (FastAPI)      + table voice_memos └─▶ page /memos/app : réécouter, renommer, supprimer
```

### Sur le PC (applet « Journal vocal »)

```bash
./install-applet.sh journal-vocal
```

Puis clic droit sur la barre des tâches → **Applets** → **Journal vocal** → **+**.

| Geste | Effet |
|---|---|
| **Clic** sur le micro ou **Super+Alt+R** | Démarre l'enregistrement : point rouge et minuteur dans la barre |
| **Clic** à nouveau | Arrête, garde le mémo dans `Musique/Journal vocal` et l'envoie au journal |
| **Clic droit** | Derniers mémos (lecture), dossier, journal complet |

Réglages (clic droit → Configurer) : raccourci clavier, dossier, arrêt automatique (30 min), adresse du service et identifiants (les mêmes que pour l'applet Google Health).
Si le service est injoignable, le mémo reste dans le dossier (⏳ dans le menu) et part tout seul plus tard.
L'enregistrement utilise GStreamer (Opus/Ogg), installé par le script s'il manque.

### Sur le téléphone Android

1. Ouvre `https://health.touplitoui.me/health/api/memos/app` dans Chrome (identifiant et mot de passe du serveur).
2. Menu ⋮ → **Ajouter à l'écran d'accueil**. L'icône « Journal vocal » s'ouvre comme une appli.
3. Touche le gros bouton pour parler, touche à nouveau pour terminer. Un appui long sur l'icône propose **Enregistrer** directement.

Sans réseau, le mémo est gardé sur le téléphone et envoyé dès que la connexion revient.
En local (sans serveur), la même page est sur <http://localhost:8765/memos/app>.

### Dans Grafana

Rangée **Journal vocal** du dashboard : minutes enregistrées par jour et par appareil, et la liste des derniers mémos. Clique sur un titre pour l'écouter. La liste déroulante **Journal vocal** en haut du dashboard indique où les écouter : `/health/api` sur le serveur, `http://localhost:8765` en local.

### API

| Requête | Effet |
|---|---|
| `POST /memos?device=mint&duration=12.5&title=…` | Corps = fichier audio brut (`Content-Type: audio/ogg`, `audio/webm`, `audio/mp4`…), 100 Mo max |
| `GET /memos?limit=50` | Liste, du plus récent au plus ancien |
| `GET /memos/{id}/audio` | Le fichier audio |
| `PATCH /memos/{id}` `{"title": "…"}` | Renommer |
| `DELETE /memos/{id}` | Supprimer (fichier compris) |

Exemple : `curl -X POST -H 'Content-Type: audio/ogg' --data-binary @memo.ogg 'localhost:8765/memos?device=web'`

**Sur le serveur**, après la mise à jour : `make health-deploy && make health-proxy` (la configuration Caddy ajoute les routes `/memos`).

## Données et dashboard

| Table | Contenu |
|---|---|
| `daily_metrics(day, metric, value, source)` | Un point par jour, par champ numérique et par source (`google-health`, `health-connect`), nommé `<type>.<champ>` (ex. `steps.countSum`) |
| `sleep_sessions` | Une ligne par nuit : début, fin, minutes endormi / éveillé / profond / léger / paradoxal, source |
| `hc_records` | Enregistrements bruts reçus de Health Connect (pour recalculer les jours) |
| vues `daily_best`, `sleep_best` | Une seule source par jour et par métrique, selon `SOURCE_PRIORITY` : c'est ce que lisent le dashboard et l'applet |
| `sync_log` | Journal de chaque synchro (30 jours) |
| `voice_memos` | Un mémo vocal par ligne : date, durée, titre, appareil (`mint`, `android`, `web`). L'audio est dans le volume Docker `memos` |

Les types synchronisés sont dans `ROLLUP_TYPES` (`.env`). Un type non disponible pour ton appareil ou ton compte est ignoré et apparaît en ✗ dans le panneau **Journal de synchro** : retire-le de la liste ou corrige son identifiant (voir l'[index des types de données](https://developers.google.com/health/data-types)). Le panneau **Toutes les métriques** liste les noms exacts reçus, pratique pour créer tes propres panneaux :

```sql
SELECT day::timestamptz AS time, value FROM daily_best
WHERE metric = 'steps.countSum' AND $__timeFilter(day::timestamptz)
```

Grafana se connecte avec le rôle `grafana_ro` (lecture seule). Le dashboard est modifiable dans l'interface ; pour versionner tes changements, exporte le JSON dans `grafana/dashboards/google-health.json`.

## Commandes utiles

```bash
docker compose logs -f sync                       # suivre la synchro
curl -X POST 'localhost:8765/sync?full=true'      # re-télécharger tout l'historique (BACKFILL_DAYS)
docker compose down                               # arrêter (les données restent)
docker compose down -v                            # tout effacer, jeton Google et mémos vocaux compris
```

## Dépannage

- **« Service de synchro injoignable »** : `docker compose ps` puis `docker compose logs sync`.
- **« Graphique indisponible »** : le conteneur `renderer` démarre lentement la première fois ; sinon `docker compose logs renderer`.
- **Erreur `redirect_uri_mismatch`** : l'URI dans Google Cloud doit être exactement `http://localhost:8765/auth/callback`.
- **Fenêtre opaque au lieu de translucide** : le compositeur de Cinnamon doit être actif (il l'est par défaut).
- **HC Webhook : erreur 401** : l'en-tête `x-api-key` ne correspond pas à `HC_INGEST_TOKEN` ; **503** : `HC_INGEST_TOKEN` est vide dans `mint-health/.env`.
- **Pas en double avec Health Connect** : active *Count overlapping apps once* dans HC Webhook, ou choisis la résolution *Daily*.
- **Applet qui ne se met pas à jour après modification** : Alt+F2 → `r` → Entrée.

## Sécurité

Le jeton Google est stocké dans le volume Docker `tokens` (fichier en `600`), les ports sont liés à `127.0.0.1` et Grafana n'autorise l'accès anonyme qu'en lecture. Ne publie pas ces ports sur le réseau sans ajouter une authentification.

Sur le serveur, tout `health.touplitoui.me` est derrière le mot de passe de Caddy, y compris le journal vocal (`/health/api/memos`), sauf `/health/api/ingest/*` (POST uniquement, 20 Mo max) : le téléphone s'y authentifie avec `HC_INGEST_TOKEN`, comparé en temps constant. Garde ce jeton secret ; pour le changer, modifie `.env`, relance `make health-deploy` et mets à jour l'en-tête dans l'appli.
