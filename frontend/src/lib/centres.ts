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

export type TypeCentre = 'csapa' | 'cjc' | 'caarud' | 'hopital' | 'residentiel' | 'association' | 'autre';

/** Ce que la personne cherche : le type de lieu compte autant que la distance. */
export const BESOINS = [
	{ id: 'tout', label: 'Je ne sais pas', emoji: '🤷' },
	{ id: 'suivi', label: 'Un suivi (consultations)', emoji: '🗓️' },
	{ id: 'sevrage', label: 'Un sevrage à l’hôpital', emoji: '🏥' },
	{ id: 'sejour', label: 'Un séjour, une post-cure', emoji: '🏡' },
	{ id: 'groupe', label: 'Un groupe, une association', emoji: '🫂' },
	{ id: 'rdr', label: 'Consommer moins risqué', emoji: '🩹' }
] as const;

export type BesoinId = (typeof BESOINS)[number]['id'];

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
			'Centre de soins en addictologie : médecin, psychologue, infirmier, travailleur social. Gratuit, confidentiel, anonyme si tu veux. Pour toutes les addictions, et pour les proches. C’est souvent la porte d’entrée vers un sevrage ou une post-cure.'
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
	hopital: {
		label: 'Hôpital · addictologie',
		explication:
			'Service ou clinique d’addictologie : consultations, sevrage en hospitalisation de quelques jours à quelques semaines. On y entre le plus souvent sur demande d’un médecin ou d’un CSAPA.'
	},
	residentiel: {
		label: 'Séjour · post-cure',
		explication:
			'Lieu où l’on vit quelques semaines à quelques mois après le sevrage pour consolider l’arrêt : post-cure (soins médicaux et de réadaptation en addictologie), centre thérapeutique résidentiel, communauté thérapeutique. L’admission se prépare avec ton médecin ou un CSAPA (dossier, parfois liste d’attente) : ça vaut le coup d’aller un peu plus loin.'
	},
	association: {
		label: 'Association',
		explication:
			'Groupe d’entraide ou association d’anciens consommateurs : réunions gratuites, sans inscription, avec des personnes qui sont passées par là. Complète le soin, ne le remplace pas.'
	},
	autre: { label: 'Lieu d’aide', explication: 'Lieu conseillé pour un accompagnement en addictologie.' }
};

const DROGUES: string[] = ['cocaine', 'opioides'];

/** Le centre convient-il à ce qui est consommé ? 0 (non) à 3 (spécialisé). */
function adequationSubstance(c: Centre, choix: string[], jeune: boolean): number {
	const spe = c.specialites ?? [];
	if (c.type === 'caarud') {
		if (!choix.length || choix.some((s) => DROGUES.includes(s))) return 2;
		return choix.some((s) => s === 'cannabis' || s === 'autre') ? 1 : 0;
	}
	if (c.type === 'cjc') return jeune ? 3 : 1;
	if (spe.length && choix.length) return choix.some((s) => spe.includes(s)) ? 3 : c.type === 'association' ? 0 : 1;
	return 2;
}

// Adéquation de chaque type de lieu à chaque besoin (0 : pas proposé).
const PAR_BESOIN: Record<BesoinId, Record<TypeCentre, number>> = {
	tout: { csapa: 2, cjc: 2, caarud: 2, hopital: 2, residentiel: 1, association: 2, autre: 2 },
	suivi: { csapa: 3, cjc: 3, caarud: 1, hopital: 2, residentiel: 0, association: 1, autre: 2 },
	sevrage: { csapa: 1, cjc: 0, caarud: 0, hopital: 3, residentiel: 1, association: 0, autre: 2 },
	sejour: { csapa: 1, cjc: 0, caarud: 0, hopital: 1, residentiel: 3, association: 0, autre: 2 },
	groupe: { csapa: 1, cjc: 0, caarud: 1, hopital: 0, residentiel: 0, association: 3, autre: 2 },
	rdr: { csapa: 1, cjc: 0, caarud: 3, hopital: 0, residentiel: 0, association: 0, autre: 1 }
};

/** Adéquation d'un lieu à la demande : 0 (pas adapté), 1 (possible), 2 (adapté), 3 (très adapté). */
export function adequation(c: Centre, choix: string[], jeune: boolean, besoin: BesoinId = 'tout'): number {
	const sub = adequationSubstance(c, choix, jeune);
	const bes = PAR_BESOIN[besoin][c.type] ?? 1;
	if (!sub || !bes) return 0;
	let fit = besoin === 'tout' ? Math.min(sub, bes + 1) : Math.max(1, Math.min(3, bes + (sub === 3 ? 1 : 0) - (sub === 1 ? 1 : 0)));
	if (c.equipe) fit = Math.min(3, fit + 1);
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

// Un lieu très adapté peut être plus loin qu'un lieu généraliste : sa distance compte pour moitié.
// Pour un séjour, on part de toute façon quelques semaines : la distance compte encore moins.
const POIDS = [0, 0.5, 1, 2];

/** Lieux classés du plus adapté au moins adapté (adéquation et distance). */
export function classer(
	centres: Centre[],
	origine: { lat: number; lon: number },
	choix: string[],
	jeune: boolean,
	besoin: BesoinId = 'tout'
): Resultat[] {
	// Besoin précis : les lieux dont le type y répond passent d'abord, tant qu'ils restent à une distance raisonnable.
	const portee = besoin === 'sejour' ? 300 : 50;
	const groupe = (r: Resultat) =>
		besoin !== 'tout' && r.fit >= 2 && PAR_BESOIN[besoin][r.centre.type] >= 2 && r.km <= portee ? 0 : 1;
	const poids = (r: Resultat) => POIDS[r.fit] * (besoin === 'sejour' && r.centre.type === 'residentiel' ? 3 : 1);
	return centres
		.map((centre) => {
			const fit = adequation(centre, choix, jeune, besoin);
			return { centre, fit, km: distanceKm(origine, centre), raisons: raisons(centre, choix, jeune, fit) };
		})
		.filter((r) => r.fit > 0)
		.sort((a, b) => groupe(a) - groupe(b) || a.km / poids(a) - b.km / poids(b) || a.km - b.km);
}

function raisons(c: Centre, choix: string[], jeune: boolean, fit: number): string[] {
	const r: string[] = [];
	if (c.equipe) r.push('Conseillé par l’équipe');
	const spe = (c.specialites ?? []).filter((s) => choix.includes(s));
	if (spe.length) r.push('Spécialisé ' + spe.map(nomSubstance).join(', ').toLowerCase());
	else if (c.type === 'csapa' && !c.specialites?.length) r.push('Toutes les addictions');
	if (c.type === 'cjc' && jeune) r.push('Pour les moins de 25 ans');
	if (c.type === 'caarud') r.push('Sans rendez-vous');
	if (c.type === 'residentiel') r.push('Hébergement sur place');
	if (c.type === 'hopital' || c.type === 'residentiel') r.push('Sur orientation médicale');
	if (fit === 1 && c.type !== 'caarud') r.push('Moins ciblé sur ta demande');
	if (c.type !== 'hopital' && c.type !== 'residentiel') r.push('Gratuit');
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

/**
 * Associations nationales d'entraide, avec leur page pour trouver une réunion près de chez soi.
 * Les groupes locaux connus de l'équipe vont dans backend/data/centres-equipe.json (type « association »).
 */
export const ASSOCIATIONS = [
	{ id: 'aa', nom: 'Alcooliques Anonymes', pour: ['alcool'], tel: '09 69 39 40 20', url: 'https://www.alcooliques-anonymes.fr', quoi: 'Réunions gratuites et anonymes, partout en France, aussi en ligne.' },
	{ id: 'vie-libre', nom: 'Vie Libre', pour: ['alcool'], tel: null, url: 'https://www.vielibre.org', quoi: 'Mouvement d’anciens buveurs : permanences et groupes de parole, aussi pour l’entourage.' },
	{ id: 'croix-bleue', nom: 'Croix Bleue', pour: ['alcool'], tel: null, url: 'https://www.croixbleue.fr', quoi: 'Groupes d’entraide pour les personnes en difficulté avec l’alcool et leurs proches.' },
	{ id: 'alcool-assistance', nom: 'Alcool Assistance', pour: ['alcool'], tel: null, url: 'https://www.alcoolassistance.net', quoi: 'Réunions d’entraide et accompagnement, partout en France.' },
	{ id: 'na', nom: 'Narcotiques Anonymes', pour: ['cannabis', 'cocaine', 'opioides', 'autre'], tel: null, url: 'https://www.narcotiquesanonymes.org', quoi: 'Réunions gratuites et anonymes pour toute dépendance aux drogues, aussi en ligne.' }
] as const;

export function associationsPour(choix: string[]) {
	if (!choix.length) return ASSOCIATIONS.filter((a) => a.id === 'aa' || a.id === 'na');
	return ASSOCIATIONS.filter((a) => (a.pour as readonly string[]).some((s) => choix.includes(s)));
}

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
