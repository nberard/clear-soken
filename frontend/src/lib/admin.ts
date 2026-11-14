// Espace admin (stats Instagram) : tri, filtres et mise en forme, sans navigateur (testé par npm test).
// Les colonnes sont celles des marts dbt de clearmind-tools (mart_instagram_publications, …).

export type Publication = {
	publication_id: string;
	url: string | null;
	published_at: string | null;
	format: string;
	libelle_format: string;
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
	estimation?: 'likers analysés' | 'likes au-delà des vues' | null;
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
	{ id: 'likes_authentiques_estimes', label: 'Likes authentiques', aide: 'likes moins les faux estimés' },
	{ id: 'likes_faux_estimes', label: 'Likes faux', aide: 'estimés d’après les likers analysés' },
	{ id: 'part_likes_faux', label: '% de likes faux', aide: 'likers analysés, ou likes au-delà des vues' },
	{ id: 'likes_au_dela_des_vues', label: 'Likes au-delà des vues', aide: 'plus de likes que de vues, signe de likes achetés' },
	{ id: 'likes_payes', label: 'Likes payés', aide: 'apportés par les boosts' },
	{ id: 'likes_organiques', label: 'Likes organiques', aide: 'likes moins likes payés' },
	{ id: 'vues_organiques', label: 'Vues organiques', aide: 'vues moins vues payées' },
	{ id: 'vues_payees', label: 'Vues payées', aide: 'apportées par les boosts' },
	{ id: 'likes', label: 'Likes (total)', aide: 'comme dans l’appli Instagram' },
	{ id: 'engagement_authentique', label: 'Engagement authentique', aide: 'sans les commentaires suspects' }
] as const satisfies readonly { id: keyof Publication; label: string; aide: string }[];

export type Critere = (typeof CRITERES)[number]['id'];

export function estReel(p: Publication): boolean {
	return p.format === 'video_courte';
}

/** Top `n` des publications selon un critère, du plus grand au plus petit, valeurs absentes à la fin */
export function top(
	pubs: Publication[],
	critere: Critere,
	n: number,
	reelsSeulement = true,
	achetesSeulement = false,
	sansPeriodesAchat = false
): Publication[] {
	return pubs
		.filter((p) => !reelsSeulement || estReel(p))
		.filter((p) => !achetesSeulement || p.likes_superieurs_aux_vues)
		.filter((p) => !sansPeriodesAchat || !p.periode_achat)
		.toSorted((a, b) => {
			const va = a[critere];
			const vb = b[critere];
			if (va == null) return vb == null ? 0 : 1;
			if (vb == null) return -1;
			return vb - va;
		})
		.slice(0, n);
}

export type FiltreComptes = {
	niveau: Niveau | 'tous';
	population: 'tous' | 'abonnes' | 'likers' | 'suivis';
	recherche: string;
};

export function filtrerComptes(comptes: Compte[], f: FiltreComptes): Compte[] {
	const q = f.recherche.trim().toLowerCase().replace(/^@/, '');
	return comptes.filter(
		(c) =>
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
	return c === 'part_likes_faux' || c === 'engagement_authentique' ? pct(p[c], 1) : nombre(p[c]);
}
