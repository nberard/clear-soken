import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
	compterNiveaux,
	filtrerComptes,
	pct,
	resumeAudience,
	top,
	valeurCritere,
	type Compte,
	type Publication
} from '../src/lib/admin.ts';

const pub = (id: string, format: string, extra: Partial<Publication>): Publication =>
	({
		publication_id: id, url: null, published_at: '2026-10-01T10:00:00Z', format, libelle_format: format,
		vues: 1000, likes: 100, commentaires: 3, partages: 1, enregistrements: 2, engagement_authentique: 0.1,
		part_commentaires_suspects: 0, boosts: 0, depense: 0, devise: null, likes_payes: 0, likes_organiques: 100,
		vues_payees: 0, vues_organiques: 1000, abonnements_payes: 0, cout_par_abonne: null, likers_releves: 0,
		likers_analyses: 0, likers_probablement_faux: 0, part_likes_faux: null, likes_faux_estimes: null,
		likes_authentiques_estimes: null, ...extra
	}) as Publication;

const pubs = [
	pub('a', 'video_courte', { likes_authentiques_estimes: 80, likes_faux_estimes: 20, part_likes_faux: 0.2 }),
	pub('b', 'video_courte', { likes_authentiques_estimes: 300, likes_faux_estimes: 5, part_likes_faux: 0.02 }),
	pub('c', 'video_courte', {}), // likers pas encore analysés
	pub('d', 'image', { likes_authentiques_estimes: 999 }),
	pub('e', 'video_courte', { likes_payes: 60, likes_organiques: 40 })
];

test('top des réels : tri décroissant, valeurs absentes à la fin, images exclues', () => {
	// c et e sans estimation des faux : classés sur leurs likes totaux (100), devant a (80 authentiques)
	assert.deepEqual(top(pubs, 'likes_authentiques_estimes', 10).map((p) => p.publication_id), ['b', 'c', 'e', 'a']);
	assert.deepEqual(top(pubs, 'likes_authentiques_estimes', 1, false).map((p) => p.publication_id), ['d']);
	assert.deepEqual(top(pubs, 'part_likes_faux', 2).map((p) => p.publication_id), ['a', 'b']);
	assert.equal(top(pubs, 'likes_payes', 1)[0].publication_id, 'e');
	const achetes = [...pubs, pub('f', 'video_courte', { likes_superieurs_aux_vues: true, likes_au_dela_des_vues: 900 })];
	assert.deepEqual(top(achetes, 'likes', 10, true, true).map((p) => p.publication_id), ['f']);
	assert.equal(top(achetes, 'likes_au_dela_des_vues', 1)[0].publication_id, 'f');
	const periodes = [...pubs, pub('g', 'video_courte', { periode_achat: true, likes_authentiques_estimes: 5000 })];
	assert.equal(top(periodes, 'likes_authentiques_estimes', 1)[0].publication_id, 'g');
	assert.equal(top(periodes, 'likes_authentiques_estimes', 1, true, false, true)[0].publication_id, 'b');
	assert.equal(pubs[0].publication_id, 'a'); // le tableau d'origine n'est pas modifié
});

test('valeurs affichées', () => {
	assert.equal(valeurCritere(pubs[0], 'part_likes_faux'), '20 %');
	assert.equal(valeurCritere(pubs[2], 'likes_faux_estimes'), '–');
	assert.equal(pct(null), '–');
});

const compte = (nom: string, pct_faux: number, niveau: Compte['niveau'], abonne: boolean, liker: boolean): Compte => ({
	compte_id: nom, nom_compte: nom, url: '', pct_faux, niveau, raisons: null, est_abonne: abonne, est_liker: liker,
	reels_likes: liker ? 1 : 0, abonnes: 0, abonnements: 0, publications: 0
});

test('filtre des comptes', () => {
	const comptes = [
		compte('user84729301', 97, 'probablement faux', true, false),
		compte('julie_photo', 8, 'plutôt réel', true, true),
		compte('lea.b', 45, 'à vérifier', false, true)
	];
	const tous = { niveau: 'tous', population: 'tous', recherche: '' } as const;
	assert.equal(filtrerComptes(comptes, tous).length, 3);
	assert.deepEqual(filtrerComptes(comptes, { ...tous, niveau: 'probablement faux' }).map((c) => c.nom_compte), ['user84729301']);
	assert.deepEqual(filtrerComptes(comptes, { ...tous, population: 'likers' }).map((c) => c.nom_compte), ['julie_photo', 'lea.b']);
	assert.deepEqual(filtrerComptes(comptes, { ...tous, recherche: '@JULIE' }).map((c) => c.nom_compte), ['julie_photo']);
	const suivis = [...comptes, { ...compte('bot123456', 92, 'probablement faux', false, false), est_suivi: true }];
	assert.deepEqual(filtrerComptes(suivis, { ...tous, population: 'suivis' }).map((c) => c.nom_compte), ['bot123456']);
	// Un verdict retire le compte de la liste, sauf si on affiche les comptes traités
	const v = { bot123456: { verdict: 'retire' as const, nom_compte: 'bot123456', le: '2026-11-17' } };
	assert.deepEqual(filtrerComptes(suivis, { ...tous, population: 'suivis' }, v), []);
	assert.equal(filtrerComptes(suivis, { ...tous, population: 'suivis', traites: true }, v).length, 1);
	assert.deepEqual(compterNiveaux(comptes), { 'probablement faux': 1, 'à vérifier': 1, 'plutôt réel': 1 });
});

test('audience hors du marché visé', () => {
	const r = resumeAudience([
		{ pays: 'FR', abonnes: 600, part: 0.6, pays_attendu: true },
		{ pays: 'IN', abonnes: 300, part: 0.3, pays_attendu: false },
		{ pays: 'BR', abonnes: 100, part: 0.1, pays_attendu: false }
	]);
	assert.equal(r.horsMarche, 0.4);
	assert.deepEqual(r.inattendus.map((p) => p.pays), ['IN', 'BR']);
	assert.equal(resumeAudience([]).horsMarche, null);
});

test('titre et description : première ligne de la légende, puis le reste', async () => {
	const { titre, description } = await import('../src/lib/admin.ts');
	const p = pub('t', 'video_courte', { texte: '\n  Coucher de soleil à Biarritz 🌅\nAvec la team\n\n#surf #océan' });
	assert.equal(titre(p), 'Coucher de soleil à Biarritz 🌅');
	assert.equal(description(p), 'Avec la team #surf #océan');
	const sans = pub('u', 'video_courte', { texte: null, libelle_format: 'Réel' });
	assert.match(titre(sans), /^Réel du /);
	assert.equal(description(sans), '');
	assert.equal(titre(pub('v', 'image', { texte: 'x'.repeat(200) }), 20).length, 20);
});

test('recherche dans la légende : tous les mots, sans accents ni casse', async () => {
	const { rechercherPublications } = await import('../src/lib/admin.ts');
	const liste = [
		pub('1', 'video_courte', { texte: 'Session surf à Biarritz\n#océan' }),
		pub('2', 'video_courte', { texte: 'Recette de crêpes' }),
		pub('3', 'video_courte', { texte: null })
	];
	assert.deepEqual(rechercherPublications(liste, 'OCEAN').map((p) => p.publication_id), ['1']);
	assert.deepEqual(rechercherPublications(liste, 'surf biarritz').map((p) => p.publication_id), ['1']);
	assert.deepEqual(rechercherPublications(liste, 'surf crepes').map((p) => p.publication_id), []);
	assert.equal(rechercherPublications(liste, '  ').length, 3);
});

test('tri sur deux niveaux, chacun croissant ou décroissant ; valeurs absentes à la fin', async () => {
	const { top, valeurCritere } = await import('../src/lib/admin.ts');
	const liste = [
		pub('1', 'video_courte', { likes: 100, vues: 500, published_at: '2026-01-01T00:00:00Z' }),
		pub('2', 'video_courte', { likes: 300, vues: 900, published_at: '2026-03-01T00:00:00Z' }),
		pub('3', 'video_courte', { likes: 100, vues: 800, published_at: '2026-02-01T00:00:00Z' }),
		pub('4', 'video_courte', { likes: null, vues: 50, published_at: null })
	];
	const ids = (l: Publication[]) => l.map((p) => p.publication_id);
	// likes décroissants, égalité 1/3 départagée par les vues décroissantes
	assert.deepEqual(ids(top(liste, [{ critere: 'likes', sens: 'desc' }, { critere: 'vues', sens: 'desc' }], 10)), ['2', '3', '1', '4']);
	// likes croissants, puis vues croissantes : sans likes toujours à la fin
	assert.deepEqual(ids(top(liste, [{ critere: 'likes', sens: 'asc' }, { critere: 'vues', sens: 'asc' }], 10)), ['1', '3', '2', '4']);
	// date : plus récente d'abord, sans date à la fin
	assert.deepEqual(ids(top(liste, [{ critere: 'published_at', sens: 'desc' }], 10)), ['2', '3', '1', '4']);
	assert.match(valeurCritere(liste[0], 'published_at'), /2026/);
});

test('faux likes : fourchette affichée, et sans estimation fiable on classe sur les likes totaux', async () => {
	const { fourchette, top, valeurCritere } = await import('../src/lib/admin.ts');
	const petit = pub('p', 'video_courte', { likes: 19751, likes_authentiques_estimes: null, part_likes_faux_bas: 0.04, part_likes_faux_haut: 0.426 });
	const fiable = pub('f', 'video_courte', { likes: 20000, likes_authentiques_estimes: 15000 });
	assert.equal(fourchette(petit), '4 à 43 %');
	assert.equal(fourchette(fiable), '');
	assert.equal(valeurCritere(petit, 'likes_authentiques_estimes'), (19751).toLocaleString('fr-FR'));
	// 19 751 likes sans estimation passent devant 15 000 likes authentiques estimés
	assert.deepEqual(top([fiable, petit], 'likes_authentiques_estimes', 10).map((p) => p.publication_id), ['p', 'f']);
});

test('tri par groupe : mois puis likes, le 2e niveau classe à l’intérieur de chaque mois', async () => {
	const { top, valeurCritere } = await import('../src/lib/admin.ts');
	const liste = [
		pub('mai-petit', 'video_courte', { published_at: '2025-05-03T10:00:00Z', likes: 10 }),
		pub('juin', 'video_courte', { published_at: '2025-06-20T10:00:00Z', likes: 5 }),
		pub('mai-grand', 'video_courte', { published_at: '2025-05-28T10:00:00Z', likes: 900 })
	];
	const tri = [{ critere: 'mois', sens: 'desc' }, { critere: 'likes', sens: 'desc' }] as const;
	assert.deepEqual(top(liste, [...tri], 10).map((p) => p.publication_id), ['juin', 'mai-grand', 'mai-petit']);
	assert.equal(valeurCritere(liste[0], 'mois'), 'mai 2025');
	const achat = [pub('a', 'video_courte', { periode_achat: false, likes: 1 }), pub('b', 'video_courte', { periode_achat: true, likes: 2 })];
	assert.deepEqual(top(achat, [{ critere: 'periode_achat', sens: 'asc' }], 10).map((p) => p.publication_id), ['a', 'b']);
});

test('tranches de vues : on groupe par audience, puis on classe par likes dans chaque tranche', async () => {
	const { top, tranche, valeurCritere } = await import('../src/lib/admin.ts');
	assert.deepEqual([999, 1000, 70668, 100000, 5_000_000].map(tranche), [0, 1, 2, 3, 4]);
	const liste = [
		pub('a', 'video_courte', { vues: 70668, likes: 1133 }),
		pub('b', 'video_courte', { vues: 12000, likes: 2000 }),
		pub('c', 'video_courte', { vues: 1056, likes: 58 }),
		pub('d', 'video_courte', { vues: 3000, likes: 300 })
	];
	const ids = top(liste, [{ critere: 'tranche_vues', sens: 'desc' }, { critere: 'likes', sens: 'desc' }], 10).map((p) => p.publication_id);
	assert.deepEqual(ids, ['b', 'a', 'd', 'c']);  // 10 k – 100 k : b (2 000 likes) devant a (1 133) ; puis 1 k – 10 k
	assert.equal(valeurCritere(liste[0], 'tranche_vues'), '10 k – 100 k vues');
});

test('deux critères chiffrés : le 1er regroupe par tranches, le 2e classe dans chaque tranche', async () => {
	const { top, libelleGroupe } = await import('../src/lib/admin.ts');
	const liste = [
		pub('vieux-gros', 'video_courte', { likes_authentiques_estimes: 46000, published_at: '2025-05-05T10:00:00Z' }),
		pub('recent-gros', 'video_courte', { likes_authentiques_estimes: 33000, published_at: '2025-05-22T10:00:00Z' }),
		pub('petit', 'video_courte', { likes_authentiques_estimes: 800, published_at: '2024-01-01T10:00:00Z' })
	];
	// likes authentiques ↓ puis date ↓ : dans la tranche 10 k – 100 k, le plus récent d'abord (même s'il a moins de likes)
	const ids = top(liste, [{ critere: 'likes_authentiques_estimes', sens: 'desc' }, { critere: 'published_at', sens: 'desc' }], 10)
		.map((p) => p.publication_id);
	assert.deepEqual(ids, ['recent-gros', 'vieux-gros', 'petit']);
	assert.equal(libelleGroupe(liste[0], 'likes_authentiques_estimes'), '10 k – 100 k · likes authentiques');
	assert.equal(libelleGroupe(pub('x', 'video_courte', { part_likes_faux: 0.15 }), 'part_likes_faux'), '10 à 20 % · % de likes faux');
});
