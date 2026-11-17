// Espace admin (stats Instagram) : tri, filtres et mise en forme, sans navigateur (testé par npm test).
// Les colonnes sont celles des marts dbt de clearmind-tools (mart_instagram_publications, …).

export type Publication = {
	publication_id: string;
	url: string | null;
	published_at: string | null;
	format: string;
	libelle_format: string;
	/** Légende de la publication (titre : sa première ligne) */
	texte?: string | null;
	/** Lien d'aperçu signé par Instagram (expire au bout de quelques jours, renouvelé à chaque collecte) */
	miniature?: string | null;
	vues: number | null;
	likes: number | null;
	commentaires: number | null;
	partages: number | null;
	enregistrements: number | null;
	engagement_authentique: number | null;
	part_commentaires_suspects: number | null;
	boosts: number;
	depense: number;
	devise: string | null;
	/** Vide : boost connu seulement par ses reçus e-mail (likes payés inconnus) */
	likes_payes: number | null;
	likes_organiques: number;
	vues_payees: number | null;
	vues_organiques: number;
	abonnements_payes: number | null;
	cout_par_abonne: number | null;
	likers_releves: number;
	likers_analyses: number;
	likers_probablement_faux: number;
	part_likes_faux: number | null;
	likes_faux_estimes: number | null;
	likes_authentiques_estimes: number | null;
	/** Plus de likes que de vues (organiques + payées) : signe de likes achetés */
	likes_superieurs_aux_vues?: boolean | null;
	likes_au_dela_des_vues?: number | null;
	/** D'où vient l'estimation des faux likes */
	estimation?: 'likers analysés' | 'likes au-delà des vues' | 'ratio likes/vues' | null;
	/** Assez de likers analysés (30 et plus) pour que leur part de faux compte */
	echantillon_suffisant?: boolean | null;
	/** Fourchette à 95 % de la part de faux parmi les likers analysés */
	part_likes_faux_bas?: number | null;
	part_likes_faux_haut?: number | null;
	/** Likes / vues de la publication, et la médiane des réels hors périodes d'achat */
	ratio_likes_vues?: number | null;
	ratio_reference?: number | null;
	/** Période d'achat : likes au-delà du ratio normal (90e centile des réels hors achat) */
	likes_au_dela_du_ratio?: number | null;
	/** Publiée pendant une période d'achat de likes / d'abonnés (PERIODES_ACHAT côté clearmind-tools) */
	periode_achat?: boolean | null;
};

export type Compte = {
	compte_id: string;
	nom_compte: string;
	url: string;
	pct_faux: number;
	niveau: Niveau;
	raisons: string | null;
	est_abonne: boolean;
	/** Un compte que je suis (pour faire le ménage) */
	est_suivi?: boolean | null;
	est_liker: boolean;
	/** Lien de la photo de profil (renouvelé à chaque collecte, expire en quelques jours) */
	photo?: string | null;
	/** false : le compte n'a pas de photo (avatar gris d'Instagram) */
	a_une_photo?: boolean | null;
	reels_likes: number;
	abonnes: number | null;
	abonnements: number | null;
	publications: number | null;
};

export type Qualite = {
	population: 'abonnes' | 'likers' | 'suivis';
	comptes_analyses: number;
	proba_faux_moyenne: number | null;
	probablement_faux: number;
	a_verifier: number;
	plutot_reels: number;
	abonnes_total: number | null;
	abonnes_faux_estimes: number | null;
};

export type Pays = { pays: string; abonnes: number; part: number | null; pays_attendu: boolean };

export type Niveau = 'probablement faux' | 'à vérifier' | 'plutôt réel';
export const NIVEAUX: Niveau[] = ['probablement faux', 'à vérifier', 'plutôt réel'];

/** Critères du top des publications. `vide` : valeur absente (réel sans liker analysé…) toujours classée à la fin */
export const CRITERES = [
	{ id: 'likes_authentiques_estimes', label: 'Likes authentiques', aide: 'likes moins les faux estimés (sans estimation fiable : les likes totaux)' },
	{ id: 'likes_faux_estimes', label: 'Likes faux', aide: 'estimés d’après les likers analysés' },
	{ id: 'part_likes_faux', label: '% de likes faux', aide: 'au moins 30 likers analysés, likes au-delà des vues ou ratio likes/vues' },
	{ id: 'likes_au_dela_des_vues', label: 'Likes au-delà des vues', aide: 'plus de likes que de vues, signe de likes achetés' },
	{ id: 'likes_au_dela_du_ratio', label: 'Likes au-delà du ratio normal', aide: 'période d’achat : likes en trop par rapport aux vues, comparé aux réels hors achat' },
	{ id: 'likes_payes', label: 'Likes payés', aide: 'apportés par les boosts' },
	{ id: 'likes_organiques', label: 'Likes organiques', aide: 'likes moins likes payés' },
	{ id: 'vues_organiques', label: 'Vues organiques', aide: 'vues moins vues payées' },
	{ id: 'vues_payees', label: 'Vues payées', aide: 'apportées par les boosts' },
	{ id: 'likes', label: 'Likes (total)', aide: 'comme dans l’appli Instagram' },
	{ id: 'vues', label: 'Vues (total)', aide: 'comme dans l’appli Instagram' },
	{ id: 'commentaires', label: 'Commentaires', aide: 'nombre annoncé par Instagram' },
	{ id: 'partages', label: 'Partages', aide: 'envois de la publication' },
	{ id: 'enregistrements', label: 'Enregistrements', aide: 'ajouts aux collections' },
	{ id: 'engagement_authentique', label: 'Engagement authentique', aide: 'sans les commentaires suspects' },
	{ id: 'published_at', label: 'Date de publication', aide: 'jour de mise en ligne' },
	// Critères qui forment des groupes : utiles en 1er niveau, le 2e classe à l'intérieur de chaque groupe
	{ id: 'tranche_vues', label: 'Vues (tranches)', aide: 'regroupe par audience : moins de 1 k, 1 k – 10 k, 10 k – 100 k…', groupe: true },
	{ id: 'tranche_likes', label: 'Likes (tranches)', aide: 'regroupe par nombre de likes : moins de 1 k, 1 k – 10 k…', groupe: true },
	{ id: 'mois', label: 'Mois de publication', aide: 'regroupe par mois', groupe: true },
	{ id: 'periode_achat', label: 'Période d’achat', aide: 'publiées pendant une période d’achat d’un côté, le reste de l’autre', groupe: true },
	{ id: 'boosts', label: 'Boosts', aide: 'nombre de boosts payés (0 = pas boostée)', groupe: true }
] as const satisfies readonly {
	id: keyof Publication | 'mois' | 'tranche_vues' | 'tranche_likes';
	label: string;
	aide: string;
	groupe?: boolean;
}[];

const TRANCHES = ['moins de 1 k', '1 k – 10 k', '10 k – 100 k', '100 k – 1 M', '1 M et plus'];

/** Tranche d'un nombre : 0 = moins de 1 000, 1 = 1 000 à 9 999… jusqu'à 4 = un million et plus */
export function tranche(n: number | null | undefined): number | null {
	if (n == null) return null;
	return n < 1000 ? 0 : Math.min(TRANCHES.length - 1, Math.floor(Math.log10(n)) - 2);
}

export type Critere = (typeof CRITERES)[number]['id'];

export function estReel(p: Publication): boolean {
	return p.format === 'video_courte';
}

/** Un niveau de tri : décroissant (du plus grand au plus petit, ou du plus récent) ou croissant */
export type Sens = 'desc' | 'asc';
export type Tri = { critere: Critere; sens: Sens };

/** Valeur numérique d'un critère (la date devient un horodatage) ; null si absente */
export function valeur(p: Publication, c: Critere): number | null {
	if (c === 'mois') {
		const d = p.published_at ? new Date(p.published_at) : null;
		return d && !Number.isNaN(d.getTime()) ? d.getFullYear() * 12 + d.getMonth() : null;
	}
	if (c === 'tranche_vues') return tranche(p.vues);
	if (c === 'tranche_likes') return tranche(p.likes);
	if (c === 'periode_achat') return p.periode_achat == null ? null : Number(p.periode_achat);
	if (c === 'published_at') {
		const t = p.published_at ? Date.parse(p.published_at) : NaN;
		return Number.isNaN(t) ? null : t;
	}
	// Sans estimation fiable des faux likes, on classe sur les likes totaux plutôt qu'en fin de liste
	if (c === 'likes_authentiques_estimes') return p.likes_authentiques_estimes ?? p.likes ?? null;
	return p[c] ?? null;
}

/** « 4 à 43 % » : fourchette à 95 % de la part de faux parmi les likers analysés, '' sans liker analysé */
export function fourchette(p: Publication): string {
	if (p.part_likes_faux_bas == null || p.part_likes_faux_haut == null) return '';
	const r = (x: number) => Math.round(x * 100);
	return `${r(p.part_likes_faux_bas)} à ${r(p.part_likes_faux_haut)} %`;
}

/** Tri sur plusieurs niveaux : le 2e départage les égalités du 1er. Valeurs absentes toujours à la fin. */
const POURCENTAGES: readonly string[] = ['part_likes_faux', 'engagement_authentique'];
const estCritereGroupe = (c: Critere) => CRITERES.some((x) => x.id === c && 'groupe' in x && x.groupe);

/** Groupe d'une publication pour un critère : le critère lui-même s'il forme déjà des groupes (mois, boosts…),
 *  sinon des tranches (nombres : moins de 1 k, 1 k – 10 k… ; pourcentages : par 10 points ; date : par mois) */
export function groupe(p: Publication, c: Critere): number | null {
	if (estCritereGroupe(c)) return valeur(p, c);
	if (c === 'published_at') return valeur(p, 'mois');
	const v = valeur(p, c);
	if (v == null) return null;
	return POURCENTAGES.includes(c) ? Math.min(9, Math.floor(v * 10)) : tranche(v);
}

/** Titre du groupe : « 10 k – 100 k likes authentiques », « 10 à 20 % de likes faux », « mai 2025 », « Pas boostées »… */
export function libelleGroupe(p: Publication, c: Critere): string {
	const g = groupe(p, c);
	const nom = CRITERES.find((x) => x.id === c)!.label.replace(/ \(.*\)$/, '').toLowerCase();
	if (c === 'periode_achat') return p.periode_achat ? 'Pendant une période d’achat' : 'Hors périodes d’achat';
	if (c === 'boosts') return p.boosts ? `Boostées ×${p.boosts}` : 'Pas boostées';
	if (c === 'mois' || c === 'published_at') return valeurCritere(p, 'mois');
	if (c === 'tranche_vues' || c === 'tranche_likes') return valeurCritere(p, c);
	if (g == null) return `Sans ${nom}`;
	if (POURCENTAGES.includes(c)) return `${g * 10} à ${g * 10 + 10} % · ${nom}`;
	return `${TRANCHES[g]} · ${nom}`;
}

/** Tri sur un ou deux niveaux. Avec deux niveaux, le 1er forme des groupes (tranches, mois) et le 2e classe
 *  à l'intérieur de chaque groupe : deux nombres ne sont jamais exactement égaux, sinon le 2e ne servirait à rien. */
export function trier(pubs: Publication[], tris: Tri[]): Publication[] {
	return pubs.toSorted((a, b) => {
		for (const [i, { critere, sens }] of tris.entries()) {
			const parGroupe = i === 0 && tris.length > 1;
			const va = parGroupe ? groupe(a, critere) : valeur(a, critere);
			const vb = parGroupe ? groupe(b, critere) : valeur(b, critere);
			if (va == null && vb == null) continue;
			if (va == null) return 1;
			if (vb == null) return -1;
			if (va !== vb) return sens === 'desc' ? vb - va : va - vb;
		}
		return 0;
	});
}

/** Top `n` des publications selon un critère (décroissant) ou plusieurs niveaux de tri, valeurs absentes à la fin */
export function top(
	pubs: Publication[],
	tri: Critere | Tri[],
	n: number,
	reelsSeulement = true,
	achetesSeulement = false,
	sansPeriodesAchat = false
): Publication[] {
	const tris: Tri[] = typeof tri === 'string' ? [{ critere: tri, sens: 'desc' }] : tri;
	return trier(
		pubs
			.filter((p) => !reelsSeulement || estReel(p))
			.filter((p) => !achetesSeulement || p.likes_superieurs_aux_vues)
			.filter((p) => !sansPeriodesAchat || !p.periode_achat),
		tris
	).slice(0, n);
}

const sansAccents = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

/** Titre d'une publication : première ligne non vide de sa légende ; sinon « Réel du 3 oct. 2026 » */
export function titre(p: Publication, max = 90): string {
	const ligne = (p.texte ?? '').split('\n').map((l) => l.trim()).find(Boolean);
	if (!ligne) return `${p.libelle_format} du ${date(p.published_at)}`;
	return ligne.length > max ? ligne.slice(0, max - 1).trimEnd() + '…' : ligne;
}

/** Description : la légende sans sa première ligne (vide si la légende tient sur une ligne) */
export function description(p: Publication): string {
	const lignes = (p.texte ?? '').split('\n').map((l) => l.trim());
	const i = lignes.findIndex(Boolean);
	return i < 0 ? '' : lignes.slice(i + 1).filter(Boolean).join(' ');
}

/** Publications dont la légende (titre et description) contient tous les mots cherchés, sans accents ni casse */
export function rechercherPublications(pubs: Publication[], recherche: string): Publication[] {
	const mots = sansAccents(recherche).split(/\s+/).filter(Boolean);
	if (!mots.length) return pubs;
	return pubs.filter((p) => {
		const texte = sansAccents(p.texte ?? '');
		return mots.every((m) => texte.includes(m));
	});
}

export type FiltreComptes = {
	niveau: Niveau | 'tous';
	population: 'tous' | 'abonnes' | 'likers' | 'suivis';
	recherche: string;
	/** Afficher aussi les comptes déjà traités (un verdict posé) */
	traites?: boolean;
};

/** Verdict posé à la main : vrai, faux, ou retiré (je ne le suis plus). L'emporte sur le pourcentage. */
export type Verdict = 'vrai' | 'faux' | 'retire';
export type Verdicts = Record<string, { verdict: Verdict; nom_compte: string; le: string }>;
export const LIBELLES_VERDICT: Record<Verdict, string> = { vrai: 'Vrai compte', faux: 'Faux', retire: 'Je ne le suis plus' };

export function filtrerComptes(comptes: Compte[], f: FiltreComptes, verdicts: Verdicts = {}): Compte[] {
	const q = f.recherche.trim().toLowerCase().replace(/^@/, '');
	return comptes.filter(
		(c) =>
			(f.traites || !verdicts[c.compte_id]) &&
			(f.niveau === 'tous' || c.niveau === f.niveau) &&
			(f.population === 'tous' ||
				(f.population === 'abonnes' ? c.est_abonne : f.population === 'suivis' ? !!c.est_suivi : c.est_liker)) &&
			(!q || c.nom_compte.toLowerCase().includes(q))
	);
}

export function compterNiveaux(comptes: Compte[]): Record<Niveau, number> {
	const out: Record<Niveau, number> = { 'probablement faux': 0, 'à vérifier': 0, 'plutôt réel': 0 };
	for (const c of comptes) out[c.niveau] = (out[c.niveau] ?? 0) + 1;
	return out;
}

/** Part des abonnés hors des pays attendus (marché visé), et les 3 plus gros pays inattendus */
export function resumeAudience(pays: Pays[]): { horsMarche: number | null; inattendus: Pays[] } {
	const total = pays.reduce((s, p) => s + p.abonnes, 0);
	if (!total) return { horsMarche: null, inattendus: [] };
	const hors = pays.filter((p) => !p.pays_attendu);
	return {
		horsMarche: hors.reduce((s, p) => s + p.abonnes, 0) / total,
		inattendus: hors.toSorted((a, b) => b.abonnes - a.abonnes).slice(0, 3)
	};
}

// --- mise en forme ---

export function nombre(n: number | null | undefined): string {
	return n == null ? '–' : Math.round(n).toLocaleString('fr-FR');
}

export function pct(x: number | null | undefined, decimales = 0): string {
	return x == null ? '–' : `${(x * 100).toLocaleString('fr-FR', { maximumFractionDigits: decimales })} %`;
}

export function argent(montant: number | null | undefined, devise: string | null): string {
	if (montant == null) return '–';
	try {
		return montant.toLocaleString('fr-FR', { style: 'currency', currency: devise || 'EUR' });
	} catch {
		return `${montant.toFixed(2)} ${devise ?? ''}`.trim();
	}
}

export function date(iso: string | null): string {
	if (!iso) return '–';
	const d = new Date(iso);
	return Number.isNaN(d.getTime()) ? '–' : d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function nomPays(code: string): string {
	try {
		return new Intl.DisplayNames(['fr'], { type: 'region' }).of(code.toUpperCase()) ?? code;
	} catch {
		return code;
	}
}

/** Valeur d'un critère pour l'affichage (pourcentage ou nombre) */
export function valeurCritere(p: Publication, c: Critere): string {
	if (c === 'published_at') return date(p.published_at);
	if (c === 'mois') {
		const d = p.published_at ? new Date(p.published_at) : null;
		return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' }) : '–';
	}
	if (c === 'periode_achat') return p.periode_achat == null ? '–' : p.periode_achat ? 'oui' : 'non';
	if (c === 'tranche_vues' || c === 'tranche_likes') {
		const t = valeur(p, c);
		return t == null ? '–' : `${TRANCHES[t]} ${c === 'tranche_vues' ? 'vues' : 'likes'}`;
	}
	if (c === 'likes_authentiques_estimes' && p.likes_authentiques_estimes == null) return nombre(p.likes);
	return c === 'part_likes_faux' || c === 'engagement_authentique' ? pct(p[c], 1) : nombre(p[c]);
}
