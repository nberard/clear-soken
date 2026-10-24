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
Dockerfile, docker-compose.yml, Caddyfile   déploiement (HTTPS automatique)
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

1. Faire pointer le domaine (ex. `clearsoken.fr`) vers l'IP du serveur, et ouvrir les ports 80 et 443.
2. Sur le serveur : `git clone …`, puis `make deploy DOMAIN=clearsoken.fr` (Docker requis).
3. Générer le QR code à afficher : `make qr DOMAIN=clearsoken.fr`.

## Pistes V2

- Communauté d'anciens patients (groupes modérés, parrainage) : nécessite HDS, modération et protocole de crise
- Planning du service (ateliers, visites) saisi par l'équipe
- Annuaire géolocalisé par secteur (GEM, CMP, associations)
- Export PDF du journal d'humeur à montrer au psychiatre
- Notifications douces (rappel respiration, échelon du jour)

> Les ressources de l'annuaire sont des exemples nationaux. Elles doivent être validées par l'équipe soignante avant diffusion.
