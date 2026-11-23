import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	compterPieces,
	groupePriorite,
	lireTitre,
	compterSorties,
	entreesTrouvees,
	extrait,
	filtrerSessions,
	type SessionClaude
} from '../src/lib/sessions-claude.ts';

const session = (id: string, extra: Partial<SessionClaude>): SessionClaude => ({
	id,
	titre: id,
	url: `https://claude.ai/code/${id}`,
	cree_le: '2026-11-01T10:00:00Z',
	maj_le: '2026-11-01T10:00:00Z',
	statut: 'terminée',
	depots: [],
	branches: [],
	entrees: [],
	sorties: { prs: [], artifacts: [], fichiers: [], commits: [] },
	...extra
});

const sessions = [
	session('session_music', {
		titre: 'Music video generation project',
		maj_le: '2026-11-14T12:00:00Z',
		statut: 'attend ma réponse',
		entrees: [
			{ le: '2026-11-11T15:48:00Z', texte: 'playlist reggae Spotify + collection Instagram', pieces: [] },
			{ le: '2026-11-11T18:31:00Z', texte: 'tunnel ssh vers OVH pour Airflow', pieces: [{ nom: 'capture.png', type: 'image' }] }
		]
	}),
	session('session_sante', {
		titre: 'clearsoken init',
		maj_le: '2026-10-26T10:00:00Z',
		entrees: [{ le: '2026-10-25T09:00:00Z', texte: 'le tableau de bord santé', pieces: [{ nom: 'note.m4a', type: 'son' }] }],
		sorties: {
			prs: [{ url: 'https://github.com/nberard/clear-soken/pull/10', titre: 'mint-health : siestes séparées' }],
			artifacts: [],
			fichiers: [{ nom: 'export.zip' }],
			commits: []
		}
	})
];

test('recherche dans les titres, messages et sorties, sans accents ni casse', () => {
	const f = { statuts: [], piece: '' as const };
	assert.deepEqual(filtrerSessions(sessions, { ...f, recherche: 'airflow ovh' }).map((s) => s.id), ['session_music']);
	assert.deepEqual(filtrerSessions(sessions, { ...f, recherche: 'MINT-HEALTH' }).map((s) => s.id), ['session_sante']);
	assert.deepEqual(filtrerSessions(sessions, { ...f, recherche: 'sante' }).map((s) => s.id), ['session_sante']);
	// Tous les mots doivent apparaître
	assert.equal(filtrerSessions(sessions, { ...f, recherche: 'airflow siestes' }).length, 0);
	// Sans recherche : les plus récentes d'abord
	assert.deepEqual(filtrerSessions(sessions, { ...f, recherche: '' }).map((s) => s.id), ['session_music', 'session_sante']);
});

test('filtres par statut et par type de pièce jointe', () => {
	assert.deepEqual(
		filtrerSessions(sessions, { recherche: '', statuts: ['attend ma réponse'], piece: '' }).map((s) => s.id),
		['session_music']
	);
	assert.deepEqual(filtrerSessions(sessions, { recherche: '', statuts: [], piece: 'son' }).map((s) => s.id), ['session_sante']);
	assert.equal(filtrerSessions(sessions, { recherche: '', statuts: [], piece: 'video' }).length, 0);
});

test('messages trouvés, comptes et extraits', () => {
	assert.equal(entreesTrouvees(sessions[0], 'spotify').length, 1);
	assert.equal(entreesTrouvees(sessions[0], '').length, 0);
	assert.deepEqual(compterPieces(sessions[0]), { image: 1 });
	assert.equal(compterSorties(sessions[1]), 2);
	const long = 'a '.repeat(200) + 'Spotify ' + 'b '.repeat(200);
	const e = extrait(long, 'spotify', 60);
	assert.ok(e.includes('Spotify') && e.startsWith('…') && e.endsWith('…'));
	assert.equal(extrait('court', 'x'), 'court');
});

test('titres rangés « NN - Projet - nom » et tri par priorité', () => {
	assert.deepEqual(lireTitre('02 - Insta - Clearsoken admin analytics dashboard'), { priorite: '02', projet: 'Insta', nom: 'Clearsoken admin analytics dashboard' });
	assert.deepEqual(lireTitre('00 - Admin sys linux'), { priorite: '00', projet: null, nom: 'Admin sys linux' });
	assert.deepEqual(lireTitre('zz - TechGit - REF.touplitoui.me'), { priorite: 'zz', projet: 'TechGit', nom: 'REF.touplitoui.me' });
	assert.deepEqual(lireTitre('MCP'), { priorite: null, projet: null, nom: 'MCP' });
	const ss = [
		session('session_a', { titre: 'zz - TechGit - vieux', maj_le: '2026-11-20T00:00:00Z' }),
		session('session_b', { titre: 'Sans préfixe', maj_le: '2026-11-21T00:00:00Z' }),
		session('session_c', { titre: '03 - Youtube - clip', maj_le: '2026-11-22T00:00:00Z' }),
		session('session_d', { titre: '00 - Linux - admin', maj_le: '2026-11-01T00:00:00Z' }),
		session('session_e', { titre: '03 - TechGit - portail', maj_le: '2026-11-23T00:00:00Z' })
	];
	const f = { recherche: '', statuts: [], piece: '' as const };
	assert.deepEqual(filtrerSessions(ss, { ...f, tri: 'priorite' }).map((s) => s.id), ['session_d', 'session_e', 'session_c', 'session_b', 'session_a']);
	assert.deepEqual(filtrerSessions(ss, { ...f, tri: 'recentes' }).map((s) => s.id), ['session_e', 'session_c', 'session_b', 'session_a', 'session_d']);
	assert.equal(groupePriorite(ss[3]), 'Priorité 00');
	assert.equal(groupePriorite(ss[0]), 'Rangées (zz)');
});
