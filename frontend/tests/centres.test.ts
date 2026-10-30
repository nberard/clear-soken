// node --experimental-strip-types --test tests/   (aucune dépendance)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adequation, associationsPour, classer, distanceKm, formatKm, lignesPour, type Centre } from '../src/lib/centres.ts';

const base = { adresse: '1 rue A', cp: '38000', ville: 'Grenoble' };
const grenoble = { lat: 45.188, lon: 5.724 };
const csapa: Centre = { ...base, id: 'csapa', nom: 'CSAPA', type: 'csapa', lat: 45.205, lon: 5.735 };
const alcool: Centre = { ...base, id: 'alcool', nom: 'CSAPA alcool', type: 'csapa', specialites: ['alcool'], lat: 45.22, lon: 5.75 };
const caarud: Centre = { ...base, id: 'caarud', nom: 'CAARUD', type: 'caarud', lat: 45.189, lon: 5.725 };
const cjc: Centre = { ...base, id: 'cjc', nom: 'CJC', type: 'cjc', lat: 45.2, lon: 5.74 };
const lyon: Centre = { ...base, id: 'lyon', nom: 'CSAPA Lyon', type: 'csapa', lat: 45.76, lon: 4.84 };

test('distance Grenoble – Lyon ≈ 95 km', () => {
	assert.ok(Math.abs(distanceKm(grenoble, lyon) - 95) < 5);
});

test('un CAARUD n’est pas proposé pour l’alcool seul, mais l’est pour la cocaïne', () => {
	assert.equal(adequation(caarud, ['alcool'], false), 0);
	assert.equal(adequation(caarud, ['cocaine'], false), 2);
	const ids = classer([csapa, caarud], grenoble, ['alcool'], false).map((r) => r.centre.id);
	assert.deepEqual(ids, ['csapa']);
});

test('un centre spécialisé alcool passe devant un généraliste un peu plus proche', () => {
	const r = classer([csapa, alcool, lyon], grenoble, ['alcool'], false);
	assert.equal(r[0].centre.id, 'alcool');
	assert.ok(r[0].raisons.includes('Spécialisé alcool'));
	assert.equal(r.at(-1)!.centre.id, 'lyon');
});

test('la consultation jeunes est mise en avant pour les moins de 25 ans', () => {
	assert.equal(classer([csapa, cjc], grenoble, ['cannabis'], true)[0].centre.id, 'cjc');
	assert.equal(classer([csapa, cjc], grenoble, ['cannabis'], false)[0].centre.id, 'csapa');
});

test('conseillé par l’équipe : bonus et raison affichée', () => {
	const equipe = { ...lyon, id: 'eq', equipe: true, lat: 45.215, lon: 5.745 };
	const r = classer([csapa, equipe], grenoble, [], false);
	assert.equal(r[0].centre.id, 'eq');
	assert.equal(r[0].raisons[0], 'Conseillé par l’équipe');
});

test('distances lisibles et lignes d’écoute selon le choix', () => {
	assert.equal(formatKm(0.34), '300 m');
	assert.equal(formatKm(2.345), '2,3 km');
	assert.equal(formatKm(42.6), '43 km');
	assert.deepEqual(lignesPour(['jeux']).map((l) => l.id), ['joueurs']);
	assert.ok(lignesPour(['cannabis']).some((l) => l.id === 'cannabis'));
});

const hopital: Centre = { ...base, id: 'hopital', nom: 'Service addictologie', type: 'hopital', lat: 45.21, lon: 5.74 };
const postcure: Centre = { ...base, id: 'postcure', nom: 'Post-cure', type: 'residentiel', lat: 45.9, lon: 6.1 }; // ~85 km
const asso: Centre = { ...base, id: 'asso', nom: 'Groupe AA Grenoble', type: 'association', specialites: ['alcool'], lat: 45.2, lon: 5.73, equipe: true };

test('séjour : la post-cure passe devant le CSAPA tout proche, même à 85 km', () => {
	const r = classer([csapa, alcool, hopital, postcure, caarud], grenoble, ['alcool'], false, 'sejour');
	assert.equal(r[0].centre.id, 'postcure');
	assert.ok(r[0].raisons.includes('Hébergement sur place'));
	assert.ok(!r.some((x) => x.centre.id === 'caarud'));
});

test('sevrage : l’hôpital d’abord ; suivi : pas de post-cure', () => {
	assert.equal(classer([csapa, hopital, postcure], grenoble, ['alcool'], false, 'sevrage')[0].centre.id, 'hopital');
	assert.ok(!classer([csapa, postcure], grenoble, ['alcool'], false, 'suivi').some((x) => x.centre.id === 'postcure'));
});

test('groupe : l’association locale ; une association alcool n’est pas proposée pour la cocaïne', () => {
	assert.equal(classer([csapa, asso], grenoble, ['alcool'], false, 'groupe')[0].centre.id, 'asso');
	assert.equal(adequation(asso, ['cocaine'], false, 'groupe'), 0);
	assert.equal(classer([csapa, caarud], grenoble, ['cocaine'], false, 'rdr')[0].centre.id, 'caarud');
});

test('associations nationales selon ce qui est consommé', () => {
	assert.ok(associationsPour(['alcool']).some((a) => a.id === 'aa'));
	assert.deepEqual(associationsPour(['cocaine']).map((a) => a.id), ['na']);
	assert.deepEqual(associationsPour(['tabac']), []);
});
