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
	assert.deepEqual(top(pubs, 'likes_authentiques_estimes', 10).map((p) => p.publication_id), ['b', 'a', 'c', 'e']);
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
