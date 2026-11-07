// node --experimental-strip-types --test tests/   (aucune dépendance)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	chiffrer, dechiffrer, demarrer, depuisFichier, estSauvegarde, fusionner, lireThemes, nouvelleSeance, parMois,
	PROCHAINE_VIDE, rechercher, themes, trier, type Seance
} from '../src/lib/seances.ts';

let n = 0;
const uid = () => 'id' + ++n;
const s = (date: string | null, texte: string, extra: Partial<Seance> = {}): Seance => ({ ...nouvelleSeance(uid(), date), texte, ...extra });

test('les sujets non abordés commencent les notes de la séance, ceux cochés disparaissent', () => {
	const prochaine = { ...PROCHAINE_VIDE, date: '2026-11-14', soignant: 'Mme L.', sujets: [
		{ id: 'a', texte: 'Le sommeil', fait: false }, { id: 'b', texte: 'Déjà réglé', fait: true }] };
	const { seance, reste } = demarrer(prochaine, 'x', '2026-11-10');
	assert.equal(seance.date, '2026-11-14');
	assert.equal(seance.soignant, 'Mme L.');
	assert.match(seance.texte, /Le sommeil/);
	assert.doesNotMatch(seance.texte, /Déjà réglé/);
	assert.deepEqual(reste.sujets, []);
	assert.equal(reste.soignant, 'Mme L.');
});

test('sans date prévue, la séance prend la date du jour', () => {
	assert.equal(demarrer(PROCHAINE_VIDE, 'x', '2026-11-10').seance.date, '2026-11-10');
});

test('tri : plus récentes d’abord, sans date à la fin', () => {
	const t = trier([s(null, 'a'), s('2023-01-01', 'b'), s('2026-01-01', 'c')]);
	assert.deepEqual(t.map((x) => x.texte), ['c', 'b', 'a']);
});

test('recherche dans les notes, l’intitulé et les thèmes ; filtre par thème', () => {
	const liste = [s('2026-01-01', 'Parlé du travail', { themes: ['travail'] }), s('2026-02-01', 'Nuits courtes', { themes: ['sommeil'] })];
	assert.equal(rechercher(liste, 'TRAVAIL', null).length, 1);
	assert.equal(rechercher(liste, 'sommeil', null).length, 1);
	assert.equal(rechercher(liste, '', 'sommeil')[0].texte, 'Nuits courtes');
	assert.deepEqual(themes(liste).map((t) => t.theme), ['sommeil', 'travail']);
	assert.deepEqual(lireThemes(' Travail, famille,travail ,'), ['travail', 'famille']);
});

test('séances par mois, mois vides compris', () => {
	const m = parMois([s('2025-11-03', ''), s('2026-01-10', ''), s('2026-01-24', ''), s(null, '')]);
	assert.deepEqual(m, [{ mois: '2025-11', n: 1 }, { mois: '2025-12', n: 0 }, { mois: '2026-01', n: 2 }]);
});

test('import du fichier de keep.py (notes Google Keep découpées par séance)', () => {
	const keep = [
		{ date: '2023-05-29', note: 'notes psy', intitule: '', texte: 'parlé du travail' },
		{ date: null, note: 'notes psy', intitule: 'Sans date', texte: 'idées en vrac' },
		{ date: null, note: 'journal psy', intitule: 'Jour 1', texte: 'matin calme' },
		{ date: 'pas une date', texte: 'x' },
		'ligne invalide'
	];
	const out = depuisFichier(keep, uid)!;
	assert.equal(out.length, 4);
	assert.equal(out[0].date, '2023-05-29');
	assert.equal(out[1].intitule, '');
	assert.equal(out[2].intitule, 'Jour 1');
	assert.equal(out[3].date, null);
	assert.equal(depuisFichier({ pas: 'une liste' }, uid), null);
});

test('un import ne duplique pas les séances déjà présentes', () => {
	const a = s('2026-01-01', 'même texte');
	const b = { ...a, id: 'autre' };
	assert.equal(fusionner([a], [b, s('2026-02-01', 'nouvelle')]).length, 2);
});

test('sauvegarde chiffrée : relue avec le bon mot de passe, refusée avec un autre', async () => {
	const contenu = { seances: [s('2026-01-01', 'confidentiel')] };
	const sauv = await chiffrer(contenu, 'correct horse battery staple');
	assert.ok(estSauvegarde(sauv));
	assert.doesNotMatch(JSON.stringify(sauv), /confidentiel/);
	assert.deepEqual(await dechiffrer(sauv, 'correct horse battery staple'), contenu);
	assert.equal(await dechiffrer(sauv, 'mauvais'), null);
	const abime = { ...sauv, data: sauv.data.slice(0, -4) + 'AAAA' };
	assert.equal(await dechiffrer(abime, 'correct horse battery staple'), null);
});
