DOMAIN ?= clearsoken.touplitoui.me
IMAGE  ?= touplitoui/clear-soken

.PHONY: dev-api dev-web test proxy deploy update restart logs qr push health-deploy health-proxy health-logs rapports-proxy rapports-qr proxy-check portal-proxy portal-update

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

deploy:           ## build + démarrage de l'appli
	docker compose up -d --build

update:           ## récupère la dernière version et redéploie
	git pull
	docker compose up -d --build

restart:          ## après modification de backend/data/resources.json
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

health-logs:
	$(HEALTH_COMPOSE) logs -f --tail=100

# --- Rapports Clearmind (site privé), voir README ---
RAPPORTS_HOST ?= rapports.touplitoui.me

rapports-proxy:   ## active https://$$RAPPORTS_HOST (site privé des rapports Clearmind) dans Caddy
	@d=$$(sed -n 's/^RAPPORTS_DIR=//p' proxy/.env); mkdir -p "$${d:-proxy/rapports}"
	@grep -Eq "^RAPPORTS_AUTH_HASH='\$$2[aby]\$$[0-9]{2}\$$.{53}'" proxy/.env || { \
	  echo "RAPPORTS_AUTH_HASH invalide dans proxy/.env : colle le hash bcrypt complet (60 caractères, commence par \$$2a\$$)"; \
	  echo "entre apostrophes, sur une seule ligne. Pour le créer :"; \
	  echo "  docker run --rm caddy:2 caddy hash-password --plaintext 'ton-mot-de-passe'"; exit 1; }
	cp proxy/sites/rapports.caddy.example proxy/sites/rapports.caddy
	$(MAKE) proxy-check || { rm -f proxy/sites/rapports.caddy; echo "-> config rapports retirée, Caddy inchangé"; exit 1; }
	$(MAKE) proxy

rapports-qr:      ## QR code vers le site des rapports (sudo apt install qrencode)
	qrencode -s 20 -m 2 -o qr-rapports.png "https://$(RAPPORTS_HOST)/"
	@echo "-> qr-rapports.png"

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

# --- Optionnel : construire sur le PC et publier sur Docker Hub ---
push:
	docker build -t $(IMAGE):latest .
	docker push $(IMAGE):latest
