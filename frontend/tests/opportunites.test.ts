import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	analyser,
	entrepriseDuRole,
	entrepriseEtPoste,
	filtrer,
	fraicheurDe,
	lieuxDe,
	regrouperDoublons,
	salaireDe,
	typeDe,
	zoneDe,
	type Mail
} from '../src/lib/opportunites.ts';

const maintenant = new Date('2026-11-25T12:00:00Z');
const mail = (extra: Partial<Mail>): Mail => ({ id: 'a1', le: '2026-11-20T10:00:00Z', sujet: '', expediteur: 'x@y.z', ...extra });

test('type de mail selon expéditeur et sujet', () => {
	assert.equal(typeDe(mail({ expediteur: 'jobalerts-noreply@linkedin.com', sujet: 'Scalian recrute' })), 'alerte');
	assert.equal(typeDe(mail({ expediteur: 'inmail-hit-reply@linkedin.com', sujet: 'Opportunité Infotel' })), 'recruteur');
	assert.equal(typeDe(mail({ expediteur: 'kevin@hiresweet.com', sujet: 'Senior Backend Engineer @WeWard' })), 'recruteur');
	assert.equal(typeDe(mail({ expediteur: 'service-candidat@email.francetravail.fr', sujet: 'Relevé de situation' })), 'demarche');
	assert.equal(typeDe(mail({ expediteur: 'sandra@exemple.fr', sujet: 'Suite à votre demande – Bilan de compétences' })), 'demarche');
	assert.equal(typeDe(mail({ expediteur: 'rh@exemple.fr', sujet: "Envie de rejoindre l'aventure ?", libelles: ['Taff/Perso/Opportunités'] })), 'recruteur');
	assert.equal(typeDe(mail({ expediteur: 'notification@slack.com', sujet: "You've got 1 unread message" })), 'autre');
});

test('entreprise et poste tirés des sujets LinkedIn', () => {
	assert.deepEqual(entrepriseEtPoste('EasyPicky recrute au poste de Développeur(se) full stack PHP Symfony'), {
		entreprise: 'EasyPicky',
		poste: 'Développeur(se) full stack PHP Symfony'
	});
	assert.deepEqual(entrepriseEtPoste("Offre d'emploi de Développeur Back-end Java - H/F chez Scalian – Recrute activement"), {
		entreprise: 'Scalian',
		poste: 'Développeur Back-end Java - H/F'
	});
	assert.equal(entrepriseEtPoste('Le poste de Engineer FullStack Senior de SEPTEO pourrait vous convenir').entreprise, 'SEPTEO');
	assert.equal(entrepriseEtPoste('Senior Software Engineer chez Swile').entreprise, 'Swile');
	assert.deepEqual(entrepriseEtPoste('Opportunité - Founding Engineer & Bras droit CTO @ Masterdoc'), {
		entreprise: 'Masterdoc',
		poste: 'Founding Engineer & Bras droit CTO'
	});
	assert.equal(entrepriseEtPoste('Opportunité - principal engineer - Collective.work').entreprise, 'Collective.work');
	assert.equal(entrepriseEtPoste('Opportunité Infotel').entreprise, 'Infotel');
	assert.equal(entrepriseEtPoste('Opportunité Staff Engineer Python / Back-end en CDI Free Iliad').entreprise, null);
	assert.equal(entrepriseEtPoste('Comment ça se passe chez Admo.tv ? Je recrute un Lead Dev PHP/Symfony (CDI)').entreprise, null);
	assert.equal(entrepriseEtPoste('De nouvelles opportunités disponibles chez Klanik à Montpellier').entreprise, 'Klanik');
	assert.equal(entrepriseEtPoste('Squad Lead Python en CDI chez Gandi (Hosting) - Opportunité Caraz').entreprise, 'Gandi (Hosting)');
	assert.equal(entrepriseDuRole('Senior Tech Recruiter @Free'), 'Free');
});

test('localisation et zone', () => {
	assert.deepEqual(lieuxDe('Senior Software Engineer Java – Montpellier – H/F'), ['Montpellier']);
	assert.deepEqual(lieuxDe('Next challenge at Voyage Privé – Full Remote SWE'), ['À distance']);
	assert.deepEqual(lieuxDe('Paris, en hybride'), ['Paris']);
	assert.equal(zoneDe(['Montpellier'], ['Nîmes', 'Montpellier']), 'proche');
	assert.equal(zoneDe(['Paris'], ['Nîmes']), 'loin');
	assert.equal(zoneDe(['Paris', 'À distance'], ['Nîmes']), 'à distance');
	assert.equal(zoneDe(['Paris'], []), 'inconnue');
	assert.equal(zoneDe([], ['Nîmes']), 'inconnue');
});

test('salaire', () => {
	assert.equal(salaireDe('Salaire jusqu’à 90-100K selon profil'), '90–100 k€');
	assert.equal(salaireDe('Rémunération : 55 000 € à 70 000 €'), '55–70 k€');
	assert.equal(salaireDe('70/90K+bspce'), '70–90 k€');
	assert.equal(salaireDe('de 42K€ à 48K€ (53k pour les plus sénior)'), '42–48 k€');
	assert.equal(salaireDe('17M Users, 30M utilisateurs'), null);
	assert.equal(salaireDe('rien ici'), null);
});

test('fraîcheur selon le type', () => {
	assert.equal(fraicheurDe('alerte', 5), 'frais');
	assert.equal(fraicheurDe('alerte', 20), 'tiède');
	assert.equal(fraicheurDe('alerte', 45), 'périmé');
	assert.equal(fraicheurDe('recruteur', 45), 'tiède');
	assert.equal(fraicheurDe('recruteur', 120), 'périmé');
});

test('un contact précis et récent passe devant une approche générique d’ESN', () => {
	const precis = analyser(
		mail({
			id: 'b1',
			expediteur: 'kevin@hiresweet.com',
			sujet: 'Senior Backend Engineer @WeWard',
			extrait: 'Python à grande échelle, 30M d’utilisateurs. Paris, hybride. Salaire jusqu’à 90-100K. Je reviens vers toi.',
			nb_messages: 2
		}),
		maintenant,
		['Nîmes']
	);
	assert.equal(precis.type, 'recruteur');
	assert.equal(precis.serieux, 'sérieux');
	assert.equal(precis.intermediaire, 'cabinet');
	assert.equal(precis.entreprise, 'WeWard');
	assert.equal(precis.fraicheur, 'frais');
	assert.equal(precis.zone, 'loin');

	const vague = analyser(
		mail({
			id: 'b2',
			le: '2026-07-10T13:19:12Z',
			expediteur: 'inmail-hit-reply@linkedin.com',
			sujet: 'Nouvelle opportunité avec Alten Bruxelles',
			extrait: 'Je recrute pour différentes opportunités chez plusieurs de mes clients grand compte.'
		}),
		maintenant,
		['Nîmes']
	);
	assert.equal(vague.serieux, 'vague');
	assert.equal(vague.intermediaire, 'ESN');
	assert.equal(vague.fraicheur, 'périmé');
	assert.ok(precis.score > vague.score);

	const tries = filtrer([vague, precis], { recherche: '', types: [], serieux: [], fraicheurs: [], zones: [], statuts: [] }, {});
	assert.deepEqual(tries.map((o) => o.id), ['b2', 'b1'].reverse());
	// Écarté : masqué par défaut, visible si on le demande
	const suivi = { b1: { statut: 'ecarte' as const, le: '2026-11-25' } };
	assert.deepEqual(filtrer([vague, precis], { recherche: '', types: [], serieux: [], fraicheurs: [], zones: [], statuts: [] }, suivi).map((o) => o.id), ['b2']);
	assert.deepEqual(filtrer([vague, precis], { recherche: 'weward', types: [], serieux: [], fraicheurs: [], zones: [], statuts: ['ecarte'] }, suivi).map((o) => o.id), ['b1']);
});

test('les mails en double pour la même offre sont regroupées', () => {
	const a = (id: string, sujet: string) => analyser(mail({ id, expediteur: 'jobalerts-noreply@linkedin.com', sujet }), maintenant);
	const groupes = regrouperDoublons([
		a('c1', 'Scalian recrute au poste de Développeur Back-end Java - H/F'),
		a('c2', "Offre d'emploi de Développeur Back-end Java - H/F chez Scalian – Recrute activement"),
		a('c3', 'SEPTEO recrute au poste de Engineer FullStack Senior')
	]);
	assert.equal(groupes.length, 2);
	assert.equal(groupes[0].doublons, 1);
	const r = (id: string) => analyser(mail({ id, expediteur: 'inmail-hit-reply@linkedin.com', sujet: 'De nouvelles opportunités disponibles chez Klanik à Montpellier' }), maintenant);
	assert.equal(regrouperDoublons([r('d1'), r('d2'), r('d3')]).length, 1);
});
