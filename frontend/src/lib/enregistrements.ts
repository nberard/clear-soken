// Espace admin, onglet Enregistrements : publications enregistrées et collections (compte principal, lecture seule).
// Filtres et tri sans navigateur (testés par npm test).

export type Enregistrement = {
	media_pk: string;
	url: string | null;
	auteur: string | null;
	publiee_le: string | null;
	type_publication: string | null;
	texte: string | null;
	miniature: string | null;
	likes: number | null;
	vues: number | null;
	/** Rang dans « Tout » : 0 = enregistrée le plus récemment */
	position_enregistrement: number | null;
	nb_collections: number;
	/** Noms des collections, séparés par « · » */
	collections: string | null;
	rangee_nulle_part: boolean;
	dans_plusieurs: boolean;
};

export type Collection = {
	collection_id: string;
	nom: string;
	type_collection: string;
	publications: number;
	auteurs: number | null;
	plus_ancienne: string | null;
	plus_recente: string | null;
	part_reels: number | null;
	doublons: number;
	rangees_nulle_part: number;
	releve_le: string | null;
};

export type FiltreEnr = {
	/** '' = toutes ; '__aucune__' = rangées nulle part ; sinon le nom d'une collection */
	collection: string;
	dansPlusieurs: boolean;
	type: string;
	recherche: string;
};

export const TRIS_ENR = [
	{ id: 'enregistrement', label: 'Enregistrées récemment' },
	{ id: 'publiee_le', label: 'Date de publication' },
	{ id: 'vues', label: 'Vues' },
	{ id: 'likes', label: 'Likes' },
	{ id: 'auteur', label: 'Auteur (A → Z)' }
] as const;
export type TriEnr = (typeof TRIS_ENR)[number]['id'];

export function nomsCollections(e: Enregistrement): string[] {
	return (e.collections ?? '').split(' · ').map((s) => s.trim()).filter(Boolean);
}

export function filtrerEnregistrements(liste: Enregistrement[], f: FiltreEnr): Enregistrement[] {
	const q = f.recherche.trim().toLowerCase().replace(/^@/, '');
	return liste.filter(
		(e) =>
			(!f.collection || (f.collection === '__aucune__' ? e.rangee_nulle_part : nomsCollections(e).includes(f.collection))) &&
			(!f.dansPlusieurs || e.dans_plusieurs) &&
			(!f.type || e.type_publication === f.type) &&
			(!q || (e.auteur ?? '').toLowerCase().includes(q) || (e.texte ?? '').toLowerCase().includes(q))
	);
}

export function trierEnregistrements(liste: Enregistrement[], tri: TriEnr): Enregistrement[] {
	const cle = (e: Enregistrement): number | string | null =>
		tri === 'enregistrement' ? e.position_enregistrement
		: tri === 'publiee_le' ? (e.publiee_le ? -new Date(e.publiee_le).getTime() : null)
		: tri === 'auteur' ? (e.auteur ?? '').toLowerCase() || null
		: e[tri] == null ? null : -(e[tri] as number);
	return liste.toSorted((a, b) => {
		const va = cle(a);
		const vb = cle(b);
		if (va == null) return vb == null ? 0 : 1;
		if (vb == null) return -1;
		return va < vb ? -1 : va > vb ? 1 : 0;
	});
}

/** Auteurs les plus enregistrés (pour repérer qui tu enregistres le plus) */
export function topAuteurs(liste: Enregistrement[], n = 10): { auteur: string; nb: number }[] {
	const compte = new Map<string, number>();
	for (const e of liste) if (e.auteur) compte.set(e.auteur, (compte.get(e.auteur) ?? 0) + 1);
	return [...compte.entries()].map(([auteur, nb]) => ({ auteur, nb })).sort((a, b) => b.nb - a.nb).slice(0, n);
}
