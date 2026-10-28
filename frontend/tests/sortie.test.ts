// node --experimental-strip-types --test tests/   (aucune dépendance)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decouper, finSejour, lienAirbnb, manques, ajouterJours, PLAN_VIDE } from '../src/lib/sortie.ts';

let n = 0;
const uid = () => String(++n);

test('découpe 30 nuits en séjours de 7 nuits, le dernier raccourci', () => {
	const s = decouper('2026-11-02', 30, 7, uid);
	assert.deepEqual(s.map((x) => x.nuits), [7, 7, 7, 7, 2]);
	assert.equal(s[1].debut, '2026-11-09');
	assert.equal(finSejour(s.at(-1)!), '2026-12-02');
});

test('changement de mois et d’année', () => {
	assert.equal(ajouterJours('2026-12-28', 7), '2027-01-04');
	assert.equal(ajouterJours('2027-02-25', 7), '2027-03-04');
});

test('lien Airbnb : lieu, dates, budget, chambre chez l’habitant', () => {
	const [s] = decouper('2026-11-02', 7, 7, uid, { lieu: 'Annecy', budgetNuit: 60, entourage: 'habitant' });
	const u = new URL(lienAirbnb(s));
	assert.equal(u.hostname, 'www.airbnb.fr');
	assert.equal(decodeURIComponent(u.pathname), '/s/Annecy/homes');
	assert.equal(u.searchParams.get('checkin'), '2026-11-02');
	assert.equal(u.searchParams.get('checkout'), '2026-11-09');
	assert.equal(u.searchParams.get('price_max'), '60');
	assert.equal(u.searchParams.get('room_types[]'), 'Private room');
});

test('sans lieu, la recherche part du cadre choisi', () => {
	const [s] = decouper('2026-11-02', 7, 7, uid, { cadre: 'mer' });
	assert.equal(decodeURIComponent(new URL(lienAirbnb(s)).pathname), '/s/Bord de mer/homes');
});

test('le filet de sécurité est exigé avant l’export', () => {
	assert.ok(manques(PLAN_VIDE).length >= 4);
	const complet = {
		...PLAN_VIDE,
		sejours: decouper('2026-11-02', 7, 7, uid, { lieu: 'Annecy' }),
		rdv: [{ id: 'r', qui: 'Psychiatre', quand: '2026-11-05', comment: 'visio' }],
		confiance: { nom: 'Sam', tel: '0600000000' },
		ordonnance: true,
		signaux: 'je dors moins de 5 h',
		aides: 'marcher, appeler Sam'
	};
	assert.deepEqual(manques(complet), []);
});
