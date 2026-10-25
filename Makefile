DOMAIN ?= clearsoken.touplitoui.me
IMAGE  ?= touplitoui/clear-soken

.PHONY: dev-api dev-web test proxy deploy update restart logs qr push health-deploy health-proxy health-logs

dev-api:          ## API Rust sur :8080
	cd backend && cargo run

dev-web:          ## PWA en dev sur :5173 (proxy /api -> :8080)
	cd frontend && npm run dev -- --host

test:
	cd frontend && npm run check
	cd backend && cargo test

# --- Serveur ---
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

health-proxy:     ## active https://$$HEALTH_HOST/health dans Caddy
	cp -n proxy/sites/health.caddy.example proxy/sites/health.caddy || true
	$(MAKE) proxy

health-logs:
	$(HEALTH_COMPOSE) logs -f --tail=100

# --- Optionnel : construire sur le PC et publier sur Docker Hub ---
push:
	docker build -t $(IMAGE):latest .
	docker push $(IMAGE):latest
