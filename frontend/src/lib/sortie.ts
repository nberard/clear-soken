// « Ma sortie » : préparer une sortie de clinique en séjours (une semaine thérapeutique ou plusieurs mois),
// avec un filet de sécurité et un export pour le psychologue et le psychiatre.
// Tout reste sur le téléphone (voir storage.ts). Airbnb n'offre pas de réservation par API :
// l'appli prépare des recherches pré-remplies, la personne réserve elle-même.

export const ENVIES = [
	{ id: 'repos', label: 'Repos', emoji: '😴', idees: ['Heures de coucher et de lever fixes', 'Une sieste courte au plus', 'Écrans coupés une heure avant de dormir'] },
	{ id: 'sport', label: 'Sport', emoji: '🏃', idees: ['Une marche ou un footing chaque matin', 'Un cours d’essai dans un club près du séjour', 'Noter son énergie avant et après'] },
	{ id: 'entoure', label: 'Être entouré·e', emoji: '🤝', idees: ['Un appel à un proche par jour', 'Un GEM ou une association près du séjour', 'Une activité de groupe (atelier, expérience Airbnb)'] },
	{ id: 'nature', label: 'Nature', emoji: '🌿', idees: ['Une sortie dehors chaque jour', 'Un repérage des sentiers proches', 'Un moment sans téléphone'] },
	{ id: 'creer', label: 'Créer', emoji: '🎨', idees: ['Un temps de création chaque jour', 'Un atelier ou un cours sur place', 'Garder une trace : photos, carnet'] }
] as const;

export const CADRES = [
	{ id: 'mer', label: 'Bord de mer', recherche: 'Bord de mer' },
	{ id: 'montagne', label: 'Montagne', recherche: 'Montagne' },
	{ id: 'campagne', label: 'Campagne', recherche: 'Campagne' },
	{ id: 'ville', label: 'Ville', recherche: 'Centre-ville' },
	{ id: 'proche', label: 'Près de chez moi', recherche: '' }
] as const;

export const ENTOURAGES = [
	{ id: 'seul', label: 'Seul·e' },
	{ id: 'proche', label: 'Avec un proche' },
	{ id: 'habitant', label: 'Chez l’habitant (chambre privée)' }
] as const;

export type Sejour = {
	id: string;
	debut: string; // AAAA-MM-JJ
	nuits: number;
	lieu: string;
	cadre: string;
	envies: string[];
	entourage: string;
	budgetNuit: number | null;
	lien: string; // annonce réservée
	reserve: boolean;
	notes: string;
};

export type Rdv = { id: string; qui: string; quand: string; comment: string };

export type PlanSortie = {
	sortieLe: string;
	objectifs: string;
	sejours: Sejour[];
	rdv: Rdv[];
	traitement: string;
	ordonnance: boolean;
	confiance: { nom: string; tel: string };
	signaux: string; // mes signes que ça ne va pas
	aides: string; // ce qui m'aide dans ces moments
};

export const PLAN_VIDE: PlanSortie = {
	sortieLe: '',
	objectifs: '',
	sejours: [],
	rdv: [],
	traitement: '',
	ordonnance: false,
	confiance: { nom: '', tel: '' },
	signaux: '',
	aides: ''
};

export function ajouterJours(iso: string, jours: number): string {
	const [a, m, j] = iso.split('-').map(Number);
	const d = new Date(Date.UTC(a, m - 1, j + jours));
	return d.toISOString().slice(0, 10);
}

/** Découpe une durée totale en séjours successifs (le dernier est raccourci si besoin). */
export function decouper(debut: string, nuitsTotal: number, nuitsParSejour: number, uid: () => string, modele?: Partial<Sejour>): Sejour[] {
	const out: Sejour[] = [];
	let jour = debut;
	let reste = nuitsTotal;
	while (reste > 0) {
		const nuits = Math.min(nuitsParSejour, reste);
		out.push({
			id: uid(),
			debut: jour,
			nuits,
			lieu: '',
			cadre: 'campagne',
			envies: ['repos'],
			entourage: 'seul',
			budgetNuit: null,
			lien: '',
			reserve: false,
			notes: '',
			...modele
		});
		jour = ajouterJours(jour, nuits);
		reste -= nuits;
	}
	return out;
}

export function finSejour(s: Sejour): string {
	return ajouterJours(s.debut, s.nuits);
}

/** Recherche Airbnb pré-remplie (lieu ou cadre, dates, budget, chambre chez l'habitant). */
export function lienAirbnb(s: Sejour): string {
	const cadre = CADRES.find((c) => c.id === s.cadre);
	const ou = s.lieu.trim() || cadre?.recherche || 'France';
	const p = new URLSearchParams({ checkin: s.debut, checkout: finSejour(s), adults: s.entourage === 'proche' ? '2' : '1' });
	if (s.budgetNuit) p.set('price_max', String(s.budgetNuit));
	if (s.entourage === 'habitant') p.append('room_types[]', 'Private room');
	return `https://www.airbnb.fr/s/${encodeURIComponent(ou)}/homes?${p.toString()}`;
}

/** Recherche d'aide près du séjour (urgences, CMP), pour l'avoir sous la main avant de partir. */
export function lienAide(s: Sejour, quoi: 'urgences' | 'cmp'): string {
	const ou = s.lieu.trim();
	const q = quoi === 'urgences' ? 'urgences psychiatriques' : 'CMP centre médico-psychologique';
	return `https://www.google.com/maps/search/${encodeURIComponent(ou ? `${q} ${ou}` : q)}`;
}

export function idees(s: Sejour): string[] {
	return ENVIES.filter((e) => s.envies.includes(e.id)).flatMap((e) => e.idees);
}

/** Ce qui manque encore au plan avant de le montrer à l'équipe soignante. */
export function manques(p: PlanSortie): string[] {
	const m: string[] = [];
	if (!p.sejours.length) m.push('au moins un séjour');
	if (p.sejours.some((s) => !s.lieu.trim() && s.cadre !== 'proche')) m.push('le lieu de chaque séjour');
	if (!p.rdv.length) m.push('un rendez-vous de suivi (psychiatre ou psychologue)');
	if (!p.confiance.nom.trim() || !p.confiance.tel.trim()) m.push('une personne de confiance joignable');
	if (!p.ordonnance) m.push('l’ordonnance et le traitement pour toute la durée');
	if (!p.signaux.trim() || !p.aides.trim()) m.push('mes signes d’alerte et ce qui m’aide');
	return m;
}
