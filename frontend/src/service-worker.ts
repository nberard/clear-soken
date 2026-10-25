/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true"/>
/// <reference lib="esnext" />
/// <reference lib="webworker" />

// Hors-ligne : l'appli complète est mise en cache à l'installation.
// L'API (/api/*) passe par le réseau, avec repli sur la dernière réponse connue.
import { immutable, assets, prerendered } from '$app/manifest';
import { version } from '$app/env';

const sw = self as unknown as ServiceWorkerGlobalScope;
const CACHE = `clearsoken-${version}`;
const ASSETS = [...immutable, ...assets, ...prerendered].map((f) => '/' + f.path.replace(/^\//, ''));

sw.addEventListener('install', (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(ASSETS))
			.then(() => sw.skipWaiting())
	);
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => sw.clients.claim())
	);
});

sw.addEventListener('fetch', (event) => {
	const req = event.request;
	if (req.method !== 'GET') return;
	const url = new URL(req.url);
	if (url.origin !== sw.location.origin) return;
	// /health : tableau de bord perso (mint-health), hors de l'appli : jamais mis en cache
	if (url.pathname === '/health' || url.pathname.startsWith('/health/')) return;

	// Fichiers de l'appli : cache d'abord
	if (ASSETS.includes(url.pathname)) {
		event.respondWith(caches.match(url.pathname).then((r) => r ?? fetch(req)));
		return;
	}

	// Pages et API : réseau d'abord, cache en secours
	event.respondWith(
		(async () => {
			const cache = await caches.open(CACHE);
			try {
				const res = await fetch(req);
				if (res.ok) cache.put(req, res.clone());
				return res;
			} catch {
				const cached = (await cache.match(req)) ?? (await cache.match('/'));
				if (cached) return cached;
				throw new Error('offline');
			}
		})()
	);
});
