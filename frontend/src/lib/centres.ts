// « Trouver un centre » : le lieu d'addictologie le plus adapté autour de moi ou de mon futur chez-moi.
// L'annuaire (/api/centres) est public ; le tri se fait sur le téléphone : ni la position ni le motif
// de la recherche ne sont envoyés au serveur de Clear Soken.

export const SUBSTANCES = [
	{ id: 'alcool', label: 'Alcool', emoji: '🍷' },
	{ id: 'cannabis', label: 'Cannabis (THC)', emoji: '🌿' },
	{ id: 'cocaine', label: 'Cocaïne, crack', emoji: '❄️' },
	{ id: 'opioides', label: 'Héroïne, opioïdes', emoji: '💊' },
	{ id: 'tabac', label: 'Tabac', emoji: '🚬' },
	{ id: 'jeux', label: 'Jeux d’argent', emoji: '🎲' },
	{ id: 'autre', label: 'Autre (écrans, chemsex…)', emoji: '🧩' }
] as const;

export type SubstanceId = (typeof SUBSTANCES)[number]['id'];

export type TypeCentre = 'csapa' | 'cjc' | 'caarud' | 'autre';

export type Centre = {
	id: string;
	nom: string;
	type: TypeCentre;
	specialites?: string[]; // vide ou absent : toutes les addictions
	adresse: string;
	cp: string;
	ville: string;
	tel?: string | null;
	url?: string | null;
	note?: string | null;
	lat: number;
	lon: number;
	equipe?: boolean; // conseillé par l'équipe soignante (backend/data/centres-equipe.json)
};

export const TYPES: Record<TypeCentre, { label: string; explication: string }> = {
	csapa: {
		label: 'CSAPA',
		explication:
			'Centre de soins en addictologie : médecin, psychologue, infirmier, travailleur social. Gratuit, confidentiel, anonyme si tu veux. Pour toutes les addictions, et pour les proches.'
	},
	cjc: {
		label: 'Consultation jeunes',
		explication: 'Consultation jeunes consommateurs (CJC) : pour les moins de 25 ans et leurs proches. Gratuit et confidentiel.'
	},
	caarud: {
		label: 'CAARUD',
		explication:
			'Accueil sans rendez-vous et sans jugement pour les personnes qui consomment des drogues : matériel stérile, réduction des risques, douche, café, orientation vers le soin.'
	},
	autre: { label: 'Lieu d’aide', explication: 'Lieu conseillé pour un accompagnement en addictologie.' }
};

const DROGUES: string[] = ['cocaine', 'opioides'];

/** Adéquation d'un centre à la demande : 0 (pas adapté), 1 (possible), 2 (adapté), 3 (très adapté). */
export function adequation(c: Centre, choix: string[], jeune: boolean): number {
	const spe = c.specialites ?? [];
	let fit: number;
	if (c.type === 'caarud') {
		if (!choix.length || choix.some((s) => DROGUES.includes(s))) fit = 2;
		else if (choix.some((s) => s === 'cannabis' || s === 'autre')) fit = 1;
		else fit = 0;
	} else if (c.type === 'cjc') {
		fit = jeune ? 3 : 1;
	} else if (spe.length && choix.length) {
		fit = choix.some((s) => spe.includes(s)) ? 3 : 1;
	} else {
		fit = 2;
	}
	if (fit > 0 && c.equipe) fit = Math.min(3, fit + 1);
	return fit;
}

/** Distance à vol d'oiseau en km (formule de haversine). */
export function distanceKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
	const rad = (d: number) => (d * Math.PI) / 180;
	const dLat = rad(b.lat - a.lat);
	const dLon = rad(b.lon - a.lon);
	const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
	return 2 * 6371 * Math.asin(Math.sqrt(h));
}

export type Resultat = { centre: Centre; km: number; fit: number; raisons: string[] };

// Un centre très adapté peut être un peu plus loin qu'un centre généraliste : sa distance compte pour moitié.
const POIDS = [0, 0.5, 1, 2];

/** Centres classés du plus adapté au moins adapté (adéquation et distance). */
export function classer(
	centres: Centre[],
	origine: { lat: number; lon: number },
	choix: string[],
	jeune: boolean
): Resultat[] {
	return centres
		.map((centre) => {
			const fit = adequation(centre, choix, jeune);
			return { centre, fit, km: distanceKm(origine, centre), raisons: raisons(centre, choix, jeune, fit) };
		})
		.filter((r) => r.fit > 0)
		.sort((a, b) => a.km / POIDS[a.fit] - b.km / POIDS[b.fit] || a.km - b.km);
}

function raisons(c: Centre, choix: string[], jeune: boolean, fit: number): string[] {
	const r: string[] = [];
	if (c.equipe) r.push('Conseillé par l’équipe');
	const spe = (c.specialites ?? []).filter((s) => choix.includes(s));
	if (spe.length) r.push('Spécialisé ' + spe.map(nomSubstance).join(', ').toLowerCase());
	else if (c.type === 'csapa' && !c.specialites?.length) r.push('Toutes les addictions');
	if (c.type === 'cjc' && jeune) r.push('Pour les moins de 25 ans');
	if (c.type === 'caarud') r.push('Sans rendez-vous');
	if (fit === 1 && c.type !== 'caarud') r.push('Moins ciblé sur ta demande');
	r.push('Gratuit');
	return r;
}

export function nomSubstance(id: string): string {
	return SUBSTANCES.find((s) => s.id === id)?.label ?? id;
}

export function formatKm(km: number): string {
	if (km < 1) return `${Math.max(100, Math.round(km * 10) * 100)} m`;
	return km < 10 ? `${km.toFixed(1).replace('.', ',')} km` : `${Math.round(km)} km`;
}

/** Lien d'itinéraire (ouvre l'appli de cartes du téléphone). */
export function lienItineraire(c: Centre): string {
	return `https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lon}`;
}

/** Lignes nationales gratuites et anonymes, utiles même sans centre proche. */
export const LIGNES = [
	{ id: 'drogues', nom: 'Drogues Info Service', tel: '0 800 23 13 13', pour: ['cannabis', 'cocaine', 'opioides', 'autre'], url: 'https://www.drogues-info-service.fr' },
	{ id: 'alcool', nom: 'Alcool Info Service', tel: '0 980 980 930', pour: ['alcool'], url: 'https://www.alcool-info-service.fr' },
	{ id: 'cannabis', nom: 'Écoute Cannabis', tel: '0 980 980 940', pour: ['cannabis'], url: 'https://www.drogues-info-service.fr' },
	{ id: 'joueurs', nom: 'Joueurs Info Service', tel: '09 74 75 13 13', pour: ['jeux'], url: 'https://www.joueurs-info-service.fr' },
	{ id: 'tabac', nom: 'Tabac Info Service', tel: '39 89', pour: ['tabac'], url: 'https://www.tabac-info-service.fr' }
] as const;

export function lignesPour(choix: string[]) {
	if (!choix.length) return LIGNES.filter((l) => l.id === 'drogues' || l.id === 'alcool');
	return LIGNES.filter((l) => l.pour.some((s) => choix.includes(s)));
}

/** Annuaire officiel (Santé publique France), en secours si l'annuaire local est vide ou loin. */
export function lienAnnuaireOfficiel(choix: string[]): string {
	if (choix.length && choix.every((s) => s === 'alcool')) return 'https://www.alcool-info-service.fr/Adresses-utiles';
	if (choix.length && choix.every((s) => s === 'jeux')) return 'https://www.joueurs-info-service.fr/Adresses-utiles';
	return 'https://www.drogues-info-service.fr/Adresses-utiles';
}

export type Lieu = { label: string; lat: number; lon: number };

/**
 * Situe une adresse, une ville ou un code postal avec le géocodeur public de l'IGN (Géoplateforme, ex-BAN).
 * Seul le texte tapé est envoyé, sans référent ni motif de recherche.
 */
export async function chercherLieu(texte: string, signal?: AbortSignal): Promise<Lieu[]> {
	const q = texte.trim();
	if (q.length < 3) return [];
	const url = `https://data.geopf.fr/geocodage/search?limit=5&q=${encodeURIComponent(q)}`;
	const res = await fetch(url, { signal, referrerPolicy: 'no-referrer', credentials: 'omit' });
	if (!res.ok) throw new Error(String(res.status));
	const json = (await res.json()) as {
		features?: { geometry: { coordinates: [number, number] }; properties: { label: string; context?: string } }[];
	};
	return (json.features ?? []).map((f) => ({
		label: f.properties.context ? `${f.properties.label} (${f.properties.context.split(',')[0].trim()})` : f.properties.label,
		lon: f.geometry.coordinates[0],
		lat: f.geometry.coordinates[1]
	}));
}
