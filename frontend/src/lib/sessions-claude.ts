// Espace admin : index des sessions Claude Code (généré par une session Claude, scripts/sessions-claude-index.py).
// Recherche, filtres et mise en forme, sans navigateur (testé par npm test).

export type TypePiece = 'texte' | 'image' | 'son' | 'video' | 'document' | 'autre';

export type Piece = { nom: string; type: TypePiece };

/** Un de mes messages dans la session */
export type Entree = { le: string; texte: string; pieces: Piece[] };

export type Sorties = {
	prs: { url: string; titre?: string | null }[];
	artifacts: { titre: string; url: string }[];
	/** Fichiers envoyés par la session (images, zip, vidéos…) : nom et légende seulement */
	fichiers: { nom: string; legende?: string | null }[];
	commits: { depot?: string | null; sha: string; message: string }[];
};

export type Statut = 'en cours' | 'attend ma réponse' | 'terminée' | 'archivée' | 'en échec';

export type SessionClaude = {
	id: string;
	titre: string;
	url: string;
	cree_le: string;
	maj_le: string;
	statut: Statut;
	/** Ce que la session attend de moi, ou ce qu'elle vient de faire */
	a_faire?: string | null;
	dernier_resultat?: string | null;
	cout_usd?: number | null;
	depots: string[];
	branches: string[];
	entrees: Entree[];
	sorties: Sorties;
};

export type IndexClaude = { genere_le: string | null; sessions: SessionClaude[] };

export const STATUTS: Statut[] = ['attend ma réponse', 'en cours', 'terminée', 'en échec', 'archivée'];

export const ICONES: Record<TypePiece, string> = {
	texte: '📝',
	image: '🖼️',
	son: '🔊',
	video: '🎬',
	document: '📄',
	autre: '📎'
};

const sansAccents = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Tout le texte d'une session où chercher : titre, mes messages, pièces, sorties, dépôts */
function texteDe(s: SessionClaude): string {
	return sansAccents(
		[
			s.titre,
			s.a_faire,
			s.dernier_resultat,
			...s.depots,
			...s.branches,
			...s.entrees.flatMap((e) => [e.texte, ...e.pieces.map((p) => p.nom)]),
			...s.sorties.prs.flatMap((p) => [p.url, p.titre]),
			...s.sorties.artifacts.map((a) => a.titre),
			...s.sorties.fichiers.flatMap((f) => [f.nom, f.legende]),
			...s.sorties.commits.map((c) => c.message)
		]
			.filter(Boolean)
			.join('\n')
	);
}

export type Tri = 'priorite' | 'recentes';

export type Filtre = {
	recherche: string;
	statuts: Statut[];
	/** Seulement les sessions qui ont au moins une pièce de ce type dans mes messages */
	piece: TypePiece | '';
	/** Par priorité (préfixe 00, 01… puis sans préfixe, puis zz), sinon les plus récemment actives d'abord */
	tri?: Tri;
};

/** Titre rangé « NN - Projet - nom » (ou « NN - nom ») : NN = priorité (00 la plus haute, zz = rangée) */
export type TitreRange = { priorite: string | null; projet: string | null; nom: string };

export function lireTitre(titre: string): TitreRange {
	const m = /^\s*(\d{1,2}|zz)\s*-\s*(.+)$/i.exec(titre);
	if (!m) return { priorite: null, projet: null, nom: titre };
	const priorite = m[1].toLowerCase() === 'zz' ? 'zz' : m[1].padStart(2, '0');
	const reste = m[2];
	const i = reste.indexOf(' - ');
	// Un projet est un mot court (Insta, TechGit, Data…) avant un deuxième « - »
	if (i > 0 && i <= 20 && !/\s/.test(reste.slice(0, i).trim())) {
		return { priorite, projet: reste.slice(0, i).trim(), nom: reste.slice(i + 3).trim() };
	}
	return { priorite, projet: null, nom: reste.trim() };
}

/** Rang de tri : 00, 01… puis sans préfixe, puis zz */
function rang(s: SessionClaude): number {
	const p = lireTitre(s.titre).priorite;
	return p === null ? 100 : p === 'zz' ? 200 : Number(p);
}

/** Libellé du groupe de priorité d'une session (pour les intertitres) */
export function groupePriorite(s: SessionClaude): string {
	const p = lireTitre(s.titre).priorite;
	return p === null ? 'Sans priorité' : p === 'zz' ? 'Rangées (zz)' : `Priorité ${p}`;
}

/** Sessions qui correspondent au filtre, triées (par priorité ou par activité). Chaque mot doit apparaître. */
export function filtrerSessions(sessions: SessionClaude[], f: Filtre): SessionClaude[] {
	const mots = sansAccents(f.recherche).split(/\s+/).filter(Boolean);
	return sessions
		.filter((s) => !f.statuts.length || f.statuts.includes(s.statut))
		.filter((s) => !f.piece || s.entrees.some((e) => e.pieces.some((p) => p.type === f.piece)))
		.filter((s) => {
			if (!mots.length) return true;
			const t = texteDe(s);
			return mots.every((m) => t.includes(m));
		})
		.sort((a, b) => (f.tri === 'priorite' ? rang(a) - rang(b) : 0) || b.maj_le.localeCompare(a.maj_le));
}

/** Mes messages qui contiennent la recherche (pour montrer où j'en ai parlé) */
export function entreesTrouvees(s: SessionClaude, recherche: string): Entree[] {
	const mots = sansAccents(recherche).split(/\s+/).filter(Boolean);
	if (!mots.length) return [];
	return s.entrees.filter((e) => {
		const t = sansAccents([e.texte, ...e.pieces.map((p) => p.nom)].join(' '));
		return mots.some((m) => t.includes(m));
	});
}

/** Nombre de pièces par type dans mes messages */
export function compterPieces(s: SessionClaude): Partial<Record<TypePiece, number>> {
	const n: Partial<Record<TypePiece, number>> = {};
	for (const e of s.entrees ?? []) for (const p of e.pieces ?? []) n[p.type] = (n[p.type] ?? 0) + 1;
	return n;
}

export function compterSorties(s: SessionClaude): number {
	const o = s.sorties;
	return (o?.prs?.length ?? 0) + (o?.artifacts?.length ?? 0) + (o?.fichiers?.length ?? 0) + (o?.commits?.length ?? 0);
}

export function dateCourte(iso: string | null | undefined): string {
	if (!iso) return '';
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function dateHeure(iso: string | null | undefined): string {
	if (!iso) return '';
	const d = new Date(iso);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** Extrait court autour du premier mot cherché */
export function extrait(texte: string, recherche: string, longueur = 220): string {
	const plat = texte.replace(/\s+/g, ' ').trim();
	const mot = sansAccents(recherche).split(/\s+/).find(Boolean);
	if (plat.length <= longueur) return plat;
	const i = mot ? sansAccents(plat).indexOf(mot) : -1;
	const debut = i < 0 ? 0 : Math.max(0, i - Math.floor(longueur / 3));
	const morceau = plat.slice(debut, debut + longueur);
	return (debut > 0 ? '…' : '') + morceau + (debut + longueur < plat.length ? '…' : '');
}
