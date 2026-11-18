import { test } from 'node:test';
import assert from 'node:assert/strict';
import { aMettreALaUne, synthese, trierALaUne, trierStories, type AlaUne, type Story } from '../src/lib/stories.ts';

const st = (id: string, vues: number | null, extra: Partial<Story> = {}): Story =>
	({
		story_id: id, publiee_le: '2026-11-10T20:00:00Z', jour: '2026-11-10', heure: 20, type_story: 'video', url: null,
		miniature: null, vues, portee: vues, reponses: 1, partages: 0, abonnements: 0, visites_profil: 2, interactions: 3,
		taps_avant: 10, taps_arriere: 1, sorties: 5, taux_sortie: 0.05, chiffres_partiels: false, a_la_une: null,
		est_a_la_une: false, ...extra
	}) as Story;

const stories = [
	st('a', 100), st('b', 120), st('c', 110), st('d', 900), st('e', 90, { est_a_la_une: true, a_la_une: 'Voyages' }),
	st('f', 1000, { est_a_la_une: true, a_la_une: 'Voyages' }), st('g', 5000, { chiffres_partiels: true }), st('h', null)
];

test('tri des stories : valeurs absentes à la fin, filtre à la une', () => {
	assert.deepEqual(trierStories(stories, 'vues', 'desc', 'toutes').map((s) => s.story_id), ['g', 'f', 'd', 'b', 'c', 'a', 'e', 'h']);
	assert.deepEqual(trierStories(stories, 'vues', 'desc', 'a_la_une').map((s) => s.story_id), ['f', 'e']);
	assert.equal(trierStories(stories, 'vues', 'asc', 'pas_a_la_une')[0].story_id, 'a');
});

test('synthèse : les relevés partiels ne comptent pas dans les moyennes', () => {
	const r = synthese(stories);
	assert.equal(r.nb, 8);
	assert.equal(Math.round(r.vues_moyenne!), Math.round((100 + 120 + 110 + 900 + 90 + 1000) / 6));
	assert.equal(r.meilleure_heure?.heure, 20);
	assert.equal(r.plus_vue?.story_id, 'g');
});

test('à mettre à la une : très vues, pas encore à la une, relevé complet', () => {
	assert.deepEqual(aMettreALaUne(stories).map((s) => s.story_id), ['d']);
	assert.deepEqual(aMettreALaUne(stories.slice(0, 3)), []); // trop peu de stories pour une médiane
});

test('tri des stories à la une', () => {
	const h = (id: string, extra: Partial<AlaUne>): AlaUne =>
		({ highlight_id: id, titre: id, couverture: null, cree_le: null, nb_stories: 3, plus_ancienne: '2025-01-01',
			plus_recente: '2026-01-01', jours_depuis_ajout: 300, stories_mesurees: 0, vues: null, vues_moyenne: null,
			vues_max: null, reponses: null, partages: null, miniature_exemple: null, ...extra }) as AlaUne;
	const liste = [h('a', { vues_moyenne: 500 }), h('b', {}), h('c', { vues_moyenne: 900, jours_depuis_ajout: 10 })];
	assert.deepEqual(trierALaUne(liste, 'vues_moyenne').map((x) => x.highlight_id), ['c', 'a', 'b']);
	assert.equal(trierALaUne(liste, 'jours_depuis_ajout')[2].highlight_id, 'c');
});
