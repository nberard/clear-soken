DOMAIN ?= clearsoken.touplitoui.me
IMAGE  ?= ghcr.io/nberard/clear-soken
TAG    ?= latest
export TAG

.PHONY: dev-api dev-web test proxy deploy update build-local restart logs qr push health-deploy health-proxy health-logs health-takeout rapports-proxy rapports-nouveau-lien rapports-lien rapports-qr proxy-check portal-proxy portal-update centres centres-auto

dev-api:          ## API Rust sur :8080
	cd backend && cargo run

dev-web:          ## PWA en dev sur :5173 (proxy /api -> :8080)
	cd frontend && npm run dev -- --host

test:
	cd frontend && npm run check
	cd backend && cargo test

# --- Serveur ---
proxy-check:      ## vérifie la config Caddy sans toucher au proxy en service
	cd proxy && docker compose run --rm --no-deps -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

proxy:            ## démarre/recharge le reverse proxy Caddy (80/443)
	cd proxy && docker compose up -d --force-recreate

deploy:           ## télécharge l'image construite par GitHub Actions et (re)démarre l'appli (TAG=sha-… pour une version précise)
	@[ -f .env ] || { cp .env.example .env && echo "-> .env créé depuis .env.example (prix des plans)"; }
	@if docker compose pull clearsoken; then \
	  docker compose up -d clearsoken; \
	elif [ "$(TAG)" != "latest" ]; then \
	  echo "-> image $(TAG) inaccessible : impossible de revenir à cette version sans ghcr.io"; exit 1; \
	else \
	  echo "-> image ghcr.io inaccessible (privée sans docker login ghcr.io -u nberard, ou réseau) : construction sur ce serveur"; \
	  docker compose up -d --build clearsoken; \
	fi
	@docker image prune -f >/dev/null
	@$(MAKE) -s centres-auto

update:           ## récupère la dernière version du dépôt (compose, .env.example) et redéploie
	git pull
	$(MAKE) deploy

build-local:      ## secours : construit l'image sur cette machine au lieu de la télécharger
	@[ -f .env ] || { cp .env.example .env && echo "-> .env créé depuis .env.example (prix des plans)"; }
	docker compose up -d --build clearsoken

CENTRES = backend/data/centres.json

centres:          ## (re)génère l'annuaire addictologie (CSAPA, post-cures, hôpitaux, CAARUD) depuis FINESS, puis redémarre
	@if command -v python3 >/dev/null; then python3 scripts/centres-finess.py; \
	  else docker run --rm -v "$(CURDIR):/w" -w /w python:3.12-slim python scripts/centres-finess.py; fi
	@if docker compose ps -q clearsoken 2>/dev/null | grep -q .; then docker compose restart clearsoken; fi

# Appelé par make deploy : régénère l'annuaire s'il manque, a plus de 30 jours ou si le script a changé.
# Un échec (data.gouv.fr injoignable) ne bloque pas le déploiement : l'ancien annuaire reste en place.
centres-auto:
	@if [ -z "$$(find $(CENTRES) -mtime -30 -newer scripts/centres-finess.py 2>/dev/null)" ]; then \
	  echo "-> mise à jour de l'annuaire des centres d'addictologie (FINESS)"; \
	  $(MAKE) -s centres || echo "-> annuaire non mis à jour (réessaie : make centres)"; \
	fi

restart:          ## après modification de backend/data/resources.json ou centres-equipe.json
	docker compose restart clearsoken

logs:
	docker compose logs -f --tail=100

qr:               ## QR code à imprimer pour le service (sudo apt install qrencode)
	qrencode -s 20 -m 2 -o qr-clearsoken.png "https://$(DOMAIN)/"
	@echo "-> qr-clearsoken.png"

# --- Tableau de bord santé perso (mint-health), voir mint-health/README.md ---
HEALTH_COMPOSE = cd mint-health && docker compose -f docker-compose.yml -f docker-compose.server.yml

health-deploy:    ## build + démarrage de la synchro Google Health et de Grafana
	$(HEALTH_COMPOSE) up -d --build

health-proxy:     ## active https://$$HEALTH_HOST dans Caddy (sous-domaine, ex. health.touplitoui.me)
	rm -f proxy/sites/health.routes   # ancien format (sous /health du domaine Clear Soken)
	cp proxy/sites/health.caddy.example proxy/sites/health.caddy   # toujours à jour avec le dépôt
	$(MAKE) proxy

# zsh ne remplace pas « ~ » après « = » : on le fait ici (sinon Docker crée un dossier « ~ » vide dans le dépôt)
TAKEOUT_DIR = $(abspath $(patsubst ~%,$(HOME)%,$(TAKEOUT)))

health-takeout:   ## importe l'historique Google Fit d'un export Takeout : make health-takeout TAKEOUT=~/takeout [ESSAI=1]
	@[ -n "$(TAKEOUT)" ] || { echo "Indique le dossier des zips : make health-takeout TAKEOUT=~/takeout"; exit 1; }
	@[ -d "$(TAKEOUT_DIR)" ] || { echo "Dossier introuvable : $(TAKEOUT_DIR)"; exit 1; }
	$(HEALTH_COMPOSE) run --rm --no-deps --user "$$(id -u):$$(id -g)" -v "$(TAKEOUT_DIR):/takeout:ro" sync python -m healthsync.takeout /takeout $(if $(ESSAI),--essai)

health-logs:
	$(HEALTH_COMPOSE) logs -f --tail=100

# --- Rapports Clearmind (site privé), voir README ---
RAPPORTS_HOST ?= rapports.touplitoui.me

rapports-proxy:   ## active le site des rapports (lien secret, sans mot de passe) dans Caddy et affiche le lien
	@d=$$(sed -n 's/^RAPPORTS_DIR=//p' proxy/.env); mkdir -p "$${d:-proxy/rapports}"
	@grep -Eq '^RAPPORTS_SECRET=[A-Za-z0-9]{32,}$$' proxy/.env || $(MAKE) -s rapports-nouveau-lien NO_RELOAD=1
	cp proxy/sites/rapports.caddy.example proxy/sites/rapports.caddy
	$(MAKE) proxy-check || { rm -f proxy/sites/rapports.caddy; echo "-> config rapports retirée, Caddy inchangé"; exit 1; }
	$(MAKE) proxy
	@$(MAKE) -s rapports-lien

rapports-nouveau-lien: ## crée un nouveau lien secret (l'ancien cesse de marcher) et recharge Caddy
	@s=$$(openssl rand -hex 20); \
	  if grep -q '^RAPPORTS_SECRET=' proxy/.env; then sed -i "s/^RAPPORTS_SECRET=.*/RAPPORTS_SECRET=$$s/" proxy/.env; \
	  else echo "RAPPORTS_SECRET=$$s" >> proxy/.env; fi; \
	  sed -i '/^RAPPORTS_AUTH_\(USER\|HASH\)=/d' proxy/.env; \
	  echo "-> nouveau lien secret enregistré dans proxy/.env"
	@[ -n "$(NO_RELOAD)" ] || $(MAKE) rapports-proxy   # recopie la config (lien secret), la vérifie et recharge

rapports-lien:    ## affiche le lien secret des rapports (à mettre dans RAPPORTS_URL côté PC)
	@grep -Eq '^RAPPORTS_SECRET=[A-Za-z0-9]{32,}$$' proxy/.env || { \
	  echo "Pas de lien secret valide dans proxy/.env : lance make rapports-nouveau-lien (crée le lien et recharge Caddy)"; exit 1; }
	@h=$$(sed -n 's/^RAPPORTS_HOST=//p' proxy/.env); s=$$(sed -n 's/^RAPPORTS_SECRET=//p' proxy/.env); \
	  echo; echo "  Lien des rapports : https://$${h:-$(RAPPORTS_HOST)}/$$s/"; \
	  echo "  Sur le PC, dans social_analytics/.env : RAPPORTS_URL=https://$${h:-$(RAPPORTS_HOST)}/$$s/"; \
	  echo "  Ne le partage qu'avec qui doit lire les rapports. QR code : make rapports-qr"; echo

rapports-qr:      ## QR code du lien secret (sudo apt install qrencode) — à garder pour soi
	@grep -Eq '^RAPPORTS_SECRET=[A-Za-z0-9]{32,}$$' proxy/.env || { \
	  echo "Pas de lien secret valide dans proxy/.env : lance make rapports-nouveau-lien (crée le lien et recharge Caddy)"; exit 1; }
	@h=$$(sed -n 's/^RAPPORTS_HOST=//p' proxy/.env); s=$$(sed -n 's/^RAPPORTS_SECRET=//p' proxy/.env); \
	  qrencode -s 20 -m 2 -o qr-rapports.png "https://$${h:-$(RAPPORTS_HOST)}/$$s/" && echo "-> qr-rapports.png"; \
	  qrencode -t ANSIUTF8 "https://$${h:-$(RAPPORTS_HOST)}/$$s/"

# --- Clearmind portal (site public, nberard/kraken-portal), voir README ---
portal-proxy:     ## active https://$$PORTAL_HOST (clone kraken-portal dans PORTAL_DIR si absent)
	@d=$$(sed -n 's/^PORTAL_DIR=//p' proxy/.env); \
	  [ -n "$$d" ] || { echo "Ajoute PORTAL_DIR=/home/nico/dev/kraken-portal dans proxy/.env"; exit 1; }; \
	  [ -d "$$d/.git" ] || git clone https://github.com/nberard/kraken-portal "$$d"
	cp proxy/sites/portal.caddy.example proxy/sites/portal.caddy
	$(MAKE) proxy-check || { rm -f proxy/sites/portal.caddy; echo "-> config portal retirée, Caddy inchangé"; exit 1; }
	$(MAKE) proxy

portal-update:    ## récupère la dernière version du portal (aucun redémarrage nécessaire)
	@d=$$(sed -n 's/^PORTAL_DIR=//p' proxy/.env); git -C "$$d" pull --ff-only

# --- Secours : construire sur le PC et publier sur ghcr.io (d'habitude, GitHub Actions s'en charge) ---
push:
	docker build --platform linux/amd64 -t $(IMAGE):latest .
	docker push $(IMAGE):latest
