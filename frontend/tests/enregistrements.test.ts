import { test } from 'node:test';
import assert from 'node:assert/strict';
import { filtrerEnregistrements, topAuteurs, trierEnregistrements, type Enregistrement } from '../src/lib/enregistrements.ts';

const e = (id: string, extra: Partial<Enregistrement>): Enregistrement =>
	({ media_pk: id, url: null, auteur: 'a', publiee_le: '2025-01-01', type_publication: 'reel', texte: '', miniature: null,
		likes: 1, vues: 10, position_enregistrement: 0, nb_collections: 1, collections: 'Voyages', rangee_nulle_part: false,
		dans_plusieurs: false, ...extra }) as Enregistrement;

const liste = [
	e('1', { auteur: 'chef_lea', texte: 'Tarte aux pommes', collections: 'Recettes · Voyages', nb_collections: 2, dans_plusieurs: true, position_enregistrement: 2, vues: 500 }),
	e('2', { auteur: 'geek', collections: null, nb_collections: 0, rangee_nulle_part: true, position_enregistrement: 0, type_publication: 'photo', vues: null }),
	e('3', { auteur: 'chef_lea', collections: 'Recettes', position_enregistrement: 1, vues: 9000, publiee_le: '2026-05-01' })
];
const tous = { collection: '', dansPlusieurs: false, type: '', recherche: '' };

test('filtres : collection, rangées nulle part, plusieurs collections, type, recherche', () => {
	assert.deepEqual(filtrerEnregistrements(liste, { ...tous, collection: 'Recettes' }).map((x) => x.media_pk), ['1', '3']);
	assert.deepEqual(filtrerEnregistrements(liste, { ...tous, collection: '__aucune__' }).map((x) => x.media_pk), ['2']);
	assert.deepEqual(filtrerEnregistrements(liste, { ...tous, dansPlusieurs: true }).map((x) => x.media_pk), ['1']);
	assert.deepEqual(filtrerEnregistrements(liste, { ...tous, type: 'photo' }).map((x) => x.media_pk), ['2']);
	assert.deepEqual(filtrerEnregistrements(liste, { ...tous, recherche: 'POMMES' }).map((x) => x.media_pk), ['1']);
	assert.deepEqual(filtrerEnregistrements(liste, { ...tous, recherche: '@chef' }).map((x) => x.media_pk), ['1', '3']);
});

test('tris et auteurs les plus enregistrés', () => {
	assert.deepEqual(trierEnregistrements(liste, 'enregistrement').map((x) => x.media_pk), ['2', '3', '1']);
	assert.deepEqual(trierEnregistrements(liste, 'vues').map((x) => x.media_pk), ['3', '1', '2']);
	assert.equal(trierEnregistrements(liste, 'publiee_le')[0].media_pk, '3');
	assert.deepEqual(topAuteurs(liste)[0], { auteur: 'chef_lea', nb: 2 });
});
