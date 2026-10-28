// Toutes les données personnelles restent sur le téléphone (localStorage).
// Rien n'est envoyé au serveur : pas de compte, pas de données de santé hébergées.

import { wipeRecordings } from './recordings.ts';

const PREFIX = 'clearsoken:';

export function load<T>(key: string, fallback: T): T {
	try {
		const raw = localStorage.getItem(PREFIX + key);
		return raw ? (JSON.parse(raw) as T) : fallback;
	} catch {
		return fallback;
	}
}

export function save<T>(key: string, value: T): void {
	try {
		localStorage.setItem(PREFIX + key, JSON.stringify(value));
	} catch {
		// Stockage indisponible (navigation privée, quota) : on continue sans sauvegarde.
	}
}

export function wipeAll(): void {
	wipeRecordings();
	try {
		Object.keys(localStorage)
			.filter((k) => k.startsWith(PREFIX))
			.forEach((k) => localStorage.removeItem(k));
	} catch {
		/* rien à faire */
	}
}

export type MoodEntry = { id: string; at: string; mood: number; note: string };
export type Step = { id: string; label: string; level: number; doneAt: string | null };

export const MOODS = [
	{ value: 1, emoji: '🌧️', label: 'Très difficile' },
	{ value: 2, emoji: '🌥️', label: 'Pas facile' },
	{ value: 3, emoji: '⛅', label: 'Entre les deux' },
	{ value: 4, emoji: '🌤️', label: 'Plutôt bien' },
	{ value: 5, emoji: '☀️', label: 'Bien' }
] as const;

export const DEFAULT_STEPS: Step[] = [
	{ id: 's1', level: 1, label: 'Boire un verre d’eau et ouvrir la fenêtre', doneAt: null },
	{ id: 's2', level: 1, label: 'Faire un exercice de respiration', doneAt: null },
	{ id: 's3', level: 2, label: 'Dire bonjour à une personne du service', doneAt: null },
	{ id: 's4', level: 2, label: 'Participer à un atelier', doneAt: null },
	{ id: 's5', level: 3, label: 'Envoyer un message à un proche', doneAt: null },
	{ id: 's6', level: 3, label: 'Faire une courte sortie accompagnée', doneAt: null },
	{ id: 's7', level: 4, label: 'Repérer une association ou un GEM près de chez moi', doneAt: null },
	{ id: 's8', level: 4, label: 'Noter mes rendez-vous après la sortie', doneAt: null }
];

export function uid(): string {
	return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}
