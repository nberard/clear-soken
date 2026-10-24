DOMAIN ?= clearsoken.fr

.PHONY: dev-api dev-web build test qr deploy

dev-api:          ## API Rust sur :8080
	cd backend && cargo run

dev-web:          ## PWA en dev sur :5173 (proxy /api -> :8080)
	cd frontend && npm run dev -- --host

build:
	cd frontend && npm ci && npm run build
	cd backend && cargo build --release

test:
	cd frontend && npm run check
	cd backend && cargo test

qr:               ## QR code à imprimer pour le service (nécessite qrencode)
	qrencode -s 20 -m 2 -o qr-$(DOMAIN).png "https://$(DOMAIN)/"
	@echo "-> qr-$(DOMAIN).png"

deploy:           ## à lancer sur le serveur OVH
	DOMAIN=$(DOMAIN) docker compose up -d --build
