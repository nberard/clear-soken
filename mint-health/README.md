# Mint Health — Google Health × Grafana dans la barre des tâches Linux Mint

```
 Google Health API ──OAuth──▶ sync (FastAPI, :8765) ──▶ PostgreSQL ──▶ Grafana (:3000)
                                   ▲                                     │  ▲
                                   │ /status, /auth, /sync          PNG  │  │ kiosque
                                   └──────── Applet Cinnamon ◀───────────┘  │
                                              └── fenêtre transparente ─────┘
```

- **sync** : connexion à ton compte Google (OAuth + PKCE), synchro toutes les 15 min des agrégats quotidiens (`dailyRollUp`) et des nuits de sommeil, stockage dans Postgres.
- **Grafana** : datasource et dashboard « Google Health » provisionnés automatiquement, panneaux transparents, consultation anonyme en lecture seule, embedding autorisé, rendu PNG.
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
nano .env          # GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, et change les 3 mots de passe
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

## Déployer sur le serveur OVH (`https://clearsoken.touplitoui.me/health`)

Le tableau de bord tourne à côté de Clear Soken, derrière le même Caddy, sous le chemin `/health` du même domaine et protégé par mot de passe. Pas de DNS supplémentaire. L'appli patients n'est pas touchée : ses conteneurs et son image Docker restent séparés, et seul `/health` demande un mot de passe.

```
Internet ─► Caddy ─► clearsoken.touplitoui.me
                       ├─ /health/api/*  ─► mint-health-sync:8765      (mot de passe)
                       ├─ /health/*      ─► mint-health-grafana:3000   (mot de passe)
                       └─ tout le reste  ─► clearsoken:8080            (appli patients, public)
```

1. **Google Cloud** : dans l'ID client OAuth, ajoute l'URI de redirection
   `https://clearsoken.touplitoui.me/health/api/auth/callback`,
   et `touplitoui.me` dans les **domaines autorisés** de l'écran de consentement.
2. **Mot de passe** de `/health` :
   ```bash
   docker run --rm caddy:2 caddy hash-password --plaintext 'ton-mot-de-passe'
   ```
   Dans `proxy/.env`, renseigne `HEALTH_AUTH_USER` et `HEALTH_AUTH_HASH='<hash>'` (avec les apostrophes).
3. **Services** : dans `mint-health/.env` (copié depuis `.env.example`), laisse `HEALTH_HOST=clearsoken.touplitoui.me`, puis à la racine du dépôt :
   ```bash
   make health-deploy   # synchro + Postgres + Grafana
   make health-proxy    # active /health dans Caddy
   ```
4. Ouvre `https://clearsoken.touplitoui.me/health/api/auth/start` pour connecter ton compte Google, puis `https://clearsoken.touplitoui.me/health/`.

**Applet sur ton PC** (clic droit → Configurer) : URL du service `https://clearsoken.touplitoui.me/health/api`, URL de Grafana `https://clearsoken.touplitoui.me/health`, et ton identifiant et mot de passe. Ils sont stockés dans un fichier privé (`~/.cache/google-health-applet/curl-auth.conf`, droits 600), jamais passés en argument de commande.

Sur le serveur, Grafana n'a ni formulaire de connexion ni authentification propre : c'est Caddy qui protège `/health`. Les données restent sur ton serveur OVH ; pour un tableau de bord personnel ce n'est pas un hébergement HDS, mais il ne faut pas y mettre de données de patients.

## Données et dashboard

| Table | Contenu |
|---|---|
| `daily_metrics(day, metric, value)` | Un point par jour et par champ numérique renvoyé par `dailyRollUp`, nommé `<type>.<champ>` (ex. `steps.countSum`) |
| `sleep_sessions` | Une ligne par nuit : début, fin, minutes endormi / éveillé / profond / léger / paradoxal |
| `sync_log` | Journal de chaque synchro (30 jours) |

Les types synchronisés sont dans `ROLLUP_TYPES` (`.env`). Un type non disponible pour ton appareil ou ton compte est ignoré et apparaît en ✗ dans le panneau **Journal de synchro** : retire-le de la liste ou corrige son identifiant (voir l'[index des types de données](https://developers.google.com/health/data-types)). Le panneau **Toutes les métriques** liste les noms exacts reçus, pratique pour créer tes propres panneaux :

```sql
SELECT day::timestamptz AS time, value FROM daily_metrics
WHERE metric = 'steps.countSum' AND $__timeFilter(day::timestamptz)
```

Grafana se connecte avec le rôle `grafana_ro` (lecture seule). Le dashboard est modifiable dans l'interface ; pour versionner tes changements, exporte le JSON dans `grafana/dashboards/google-health.json`.

## Commandes utiles

```bash
docker compose logs -f sync                       # suivre la synchro
curl -X POST 'localhost:8765/sync?full=true'      # re-télécharger tout l'historique (BACKFILL_DAYS)
docker compose down                               # arrêter (les données restent)
docker compose down -v                            # tout effacer, jeton Google compris
```

## Dépannage

- **« Service de synchro injoignable »** : `docker compose ps` puis `docker compose logs sync`.
- **« Graphique indisponible »** : le conteneur `renderer` démarre lentement la première fois ; sinon `docker compose logs renderer`.
- **Erreur `redirect_uri_mismatch`** : l'URI dans Google Cloud doit être exactement `http://localhost:8765/auth/callback`.
- **Fenêtre opaque au lieu de translucide** : le compositeur de Cinnamon doit être actif (il l'est par défaut).
- **Applet qui ne se met pas à jour après modification** : Alt+F2 → `r` → Entrée.

## Sécurité

Le jeton Google est stocké dans le volume Docker `tokens` (fichier en `600`), les ports sont liés à `127.0.0.1` et Grafana n'autorise l'accès anonyme qu'en lecture. Ne publie pas ces ports sur le réseau sans ajouter une authentification.
