// Espace admin, onglet Stories : stories mesurées pendant leurs 24 h et stories à la une (marts dbt de
// clearmind-tools). Tri, synthèse et suggestions, sans navigateur (testé par npm test).

export type Story = {
	story_id: string;
	publiee_le: string | null;
	jour: string | null;
	heure: number | null;
	type_story: string | null;
	url: string | null;
	miniature: string | null;
	vues: number | null;
	portee: number | null;
	reponses: number | null;
	partages: number | null;
	abonnements: number | null;
	visites_profil: number | null;
	interactions: number | null;
	taps_avant: number | null;
	taps_arriere: number | null;
	sorties: number | null;
	/** sorties / portée */
	taux_sortie: number | null;
	/** Relevée moins de 20 h après sa publication : chiffres incomplets */
	chiffres_partiels: boolean | null;
	a_la_une: string | null;
	est_a_la_une: boolean | null;
};

export type AlaUne = {
	highlight_id: string;
	titre: string;
	couverture: string | null;
	cree_le: string | null;
	nb_stories: number;
	plus_ancienne: string | null;
	plus_recente: string | null;
	jours_depuis_ajout: number | null;
	stories_mesurees: number;
	vues: number | null;
	vues_moyenne: number | null;
	vues_max: number | null;
	reponses: number | null;
	partages: number | null;
	miniature_exemple: string | null;
};

export const CRITERES_STORY = [
	{ id: 'vues', label: 'Vues' },
	{ id: 'portee', label: 'Portée' },
	{ id: 'reponses', label: 'Réponses' },
	{ id: 'partages', label: 'Partages' },
	{ id: 'abonnements', label: 'Abonnements' },
	{ id: 'visites_profil', label: 'Visites du profil' },
	{ id: 'taux_sortie', label: 'Taux de sortie', aide: 'part des gens qui quittent les stories sur celle-ci' },
	{ id: 'publiee_le', label: 'Date' }
] as const satisfies readonly { id: keyof Story; label: string; aide?: string }[];
export type CritereStory = (typeof CRITERES_STORY)[number]['id'];

export type FiltreUne = 'toutes' | 'a_la_une' | 'pas_a_la_une';

function valeur(st: Story, c: CritereStory): number | null {
	if (c === 'publiee_le') return st.publiee_le ? new Date(st.publiee_le).getTime() : null;
	return st[c];
}

/** Stories triées (valeurs absentes à la fin), filtrées par présence à la une */
export function trierStories(stories: Story[], c: CritereStory, sens: 'desc' | 'asc', une: FiltreUne): Story[] {
	return stories
		.filter((s) => une === 'toutes' || (une === 'a_la_une' ? !!s.est_a_la_une : !s.est_a_la_une))
		.toSorted((a, b) => {
			const va = valeur(a, c);
			const vb = valeur(b, c);
			if (va == null) return vb == null ? 0 : 1;
			if (vb == null) return -1;
			return sens === 'desc' ? vb - va : va - vb;
		});
}

function moyenne(xs: number[]): number | null {
	return xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null;
}

export type Synthese = {
	nb: number;
	plus_ancienne: string | null;
	plus_recente: string | null;
	vues_moyenne: number | null;
	taux_sortie_moyen: number | null;
	plus_vue: Story | null;
	meilleure_heure: { heure: number; vues: number; nb: number } | null;
	par_type: { type: string; nb: number; vues_moyenne: number | null }[];
};

/** Synthèse des stories mesurées (les relevés partiels, moins de 20 h, ne comptent pas dans les moyennes) */
export function synthese(stories: Story[]): Synthese {
	const completes = stories.filter((s) => !s.chiffres_partiels);
	const dates = stories.map((s) => s.publiee_le).filter((d): d is string => !!d).sort();
	const vues = completes.map((s) => s.vues).filter((v): v is number => v != null);
	const heures = new Map<number, number[]>();
	for (const s of completes) {
		if (s.heure == null || s.vues == null) continue;
		heures.set(s.heure, [...(heures.get(s.heure) ?? []), s.vues]);
	}
	// meilleure heure : la plus forte moyenne de vues, parmi les heures avec au moins 3 stories
	const meilleure = [...heures.entries()]
		.filter(([, v]) => v.length >= 3)
		.map(([heure, v]) => ({ heure, vues: Math.round(moyenne(v)!), nb: v.length }))
		.sort((a, b) => b.vues - a.vues)[0] ?? null;
	const types = new Map<string, number[]>();
	for (const s of completes) types.set(s.type_story ?? 'autre', [...(types.get(s.type_story ?? 'autre') ?? []), s.vues ?? 0]);
	return {
		nb: stories.length,
		plus_ancienne: dates[0] ?? null,
		plus_recente: dates.at(-1) ?? null,
		vues_moyenne: moyenne(vues),
		taux_sortie_moyen: moyenne(completes.map((s) => s.taux_sortie).filter((v): v is number => v != null)),
		plus_vue: trierStories(stories, 'vues', 'desc', 'toutes')[0] ?? null,
		meilleure_heure: meilleure,
		par_type: [...types.entries()].map(([type, v]) => ({ type, nb: v.length, vues_moyenne: moyenne(v) }))
	};
}

/** Stories qui mériteraient d'aller à la une : pas encore à la une, relevé complet, vues ≥ 1,5 × la médiane */
export function aMettreALaUne(stories: Story[], n = 10): Story[] {
	const completes = stories.filter((s) => !s.chiffres_partiels && s.vues != null);
	const triees = completes.map((s) => s.vues!).sort((a, b) => a - b);
	if (triees.length < 5) return [];
	const mediane = triees[Math.floor(triees.length / 2)];
	return trierStories(completes.filter((s) => !s.est_a_la_une && s.vues! >= 1.5 * mediane), 'vues', 'desc', 'toutes').slice(0, n);
}

export const TRIS_UNE = [
	{ id: 'vues_moyenne', label: 'Vues moyennes' },
	{ id: 'nb_stories', label: 'Nombre de stories' },
	{ id: 'jours_depuis_ajout', label: 'Dernier ajout le plus ancien' },
	{ id: 'plus_ancienne', label: 'Story la plus ancienne' }
] as const;
export type TriUne = (typeof TRIS_UNE)[number]['id'];

export function trierALaUne(liste: AlaUne[], tri: TriUne): AlaUne[] {
	const v = (h: AlaUne) =>
		tri === 'plus_ancienne' ? (h.plus_ancienne ? -new Date(h.plus_ancienne).getTime() : null) : h[tri];
	return liste.toSorted((a, b) => {
		const va = v(a);
		const vb = v(b);
		if (va == null) return vb == null ? 0 : 1;
		if (vb == null) return -1;
		return vb - va;
	});
}
