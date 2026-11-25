// Espace admin : opportunités pro relevées dans Gmail par une session Claude (voir backend/src/opportunites.rs).
// Ici, sans navigateur (testé par npm test) : à partir du sujet, de l'expéditeur et d'un court extrait, on déduit
// le type de mail, le sérieux du lead, la localisation du poste et sa fraîcheur. Tout est recalculé à l'affichage :
// une règle corrigée ici s'applique à tout le relevé sans réimport.

export type Mail = {
	/** Identifiant du fil Gmail (hexadécimal) */
	id: string;
	/** Date du dernier message du fil (ISO) */
	le: string;
	sujet: string;
	expediteur: string;
	/** Nom affiché de l'expéditeur (le recruteur, pour les InMails LinkedIn) */
	nom?: string | null;
	/** Poste ou rôle de l'expéditeur, s'il est connu (« Senior Tech Recruiter @Free ») */
	role?: string | null;
	/** Court extrait ou résumé du contenu */
	extrait?: string | null;
	non_lu?: boolean;
	nb_messages?: number;
	/** Libellés Gmail (Taff, Taff/Perso/Opportunités…) */
	libelles?: string[];
};

export type Releve = {
	genere_le: string | null;
	mails: Mail[];
	/** Villes considérées comme proches de chez moi (gardées dans le relevé, jamais dans git) */
	zone_proche?: string[];
	/** Chiffres de la boîte au moment du relevé (non lus par libellé…) */
	stats?: Record<string, number>;
};

export type StatutSuivi = 'a_creuser' | 'contacte' | 'entretien' | 'ecarte' | 'archive';
export type Suivi = { statut: StatutSuivi; note?: string; le: string };

export const LIBELLES_STATUT: Record<StatutSuivi | 'nouveau', string> = {
	nouveau: 'Nouveau',
	a_creuser: 'À creuser',
	contacte: 'Contacté',
	entretien: 'Entretien',
	ecarte: 'Écarté',
	archive: 'Archivé'
};

export type Type = 'recruteur' | 'alerte' | 'demarche' | 'autre';
export type Serieux = 'sérieux' | 'à creuser' | 'vague';
export type Intermediaire = 'en direct' | 'cabinet' | 'ESN' | 'plateforme' | 'inconnu';
export type Fraicheur = 'frais' | 'tiède' | 'périmé';
export type Zone = 'proche' | 'à distance' | 'loin' | 'inconnue';

export type Opportunite = Mail & {
	type: Type;
	/** J'ai répondu (LinkedIn « Message ayant reçu une réponse », ou noté dans l'extrait) */
	echange: boolean;
	entreprise: string | null;
	poste: string | null;
	intermediaire: Intermediaire;
	serieux: Serieux;
	/** Pourquoi ce niveau de sérieux (indices trouvés) */
	indices: string[];
	salaire: string | null;
	lieux: string[];
	zone: Zone;
	age_jours: number;
	fraicheur: Fraicheur;
	/** Plus c'est haut, plus ça mérite d'être lu en premier */
	score: number;
};

const sansAccents = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// ---------------------------------------------------------------- type de mail

const ALERTES = [
	'jobalerts-noreply@linkedin.com',
	'jobs-noreply@linkedin.com',
	'jobs-listings@linkedin.com',
	'messages-noreply@linkedin.com',
	'no-reply@match.jobgether.com',
	'contact@hiresweet.com'
];
const DEMARCHES = ['francetravail.fr', 'data-bird.co', '360learning.com', 'conseillerformation.fr', 'apec.fr'];
/** Plateformes qui envoient des offres en masse sous un prénom (Collective.work…) */
const PLATEFORMES = ['gethorizonpro.com', 'collective.work', 'myhiring.org', 'jobgether.com', 'fantastic.jobs'];
const CABINETS = ['hiresweet', 'licornesociety', 'licorne society', 'caraz', 'skill-hunter', "work'in", 'marvinrecruiter', 'michael page', 'hays', 'robert walters', 'talent'];
const ESN = ['alten', 'astek', 'klanik', 'infotel', 'amiltone', 'amiltonien', 'conserto', 'capgemini', 'inetum', 'scalian', 'synanto', 'visian', 'nexton', 'sopra', 'cgi', 'meritis', 'steamulo', 'smile', 'randstad'];

export function typeDe(m: Mail): Type {
	const exp = m.expediteur.toLowerCase();
	const sujet = sansAccents(m.sujet);
	if (DEMARCHES.some((d) => exp.endsWith(d)) || sujet.includes('bilan de competences')) return 'demarche';
	if (ALERTES.includes(exp)) return 'alerte';
	if (exp.endsWith('hit-reply@linkedin.com') || m.libelles?.some((l) => /opportunit/i.test(l))) return 'recruteur';
	if (/opportunit|recrut|poste|cdi|engineer|developpeu|lead|cto|freelance|mission|rejoindre/.test(sujet)) return 'recruteur';
	return 'autre';
}

// ---------------------------------------------------------------- entreprise et poste (sujets LinkedIn)

const MOTIFS_SUJET: [RegExp, 'ep' | 'pe'][] = [
	[/^(.+?) recrute au poste de (.+)$/i, 'ep'],
	[/^(.+?) recrute pour le poste suivant ?: (.+)$/i, 'ep'],
	[/^(.+?) recrute ?: (.+)$/i, 'ep'],
	[/^offre d'emploi de (.+?) chez (.+?)(?: – .*)?$/i, 'pe'],
	[/^le poste de (.+?) (?:de|chez) (.+?) pourrait vous convenir.*$/i, 'pe'],
	[/^une offre d'emploi de (.+?) chez (.+?)(?:et \d+ autres?.*| pourrait.*)$/i, 'pe'],
	[/^(.+?) chez (.+)$/i, 'pe'],
	[/^(?:opportunit[ée] ?[-–:]? ?)?(.+?) ?@ ?(.+)$/i, 'pe']
];

/** « Klanik à Montpellier » → « Klanik », « Gandi (Hosting) - Opportunité Caraz » → « Gandi (Hosting) » */
const nettoyerEntreprise = (e: string) => e.replace(/ [-–] opportunit[ée].*$/i, '').replace(/ à [A-ZÀ-Ý][\p{L}-]+$/u, '').trim();

export function entrepriseEtPoste(sujet: string): { entreprise: string | null; poste: string | null } {
	const s = sujet.replace(/^message ayant reçu une réponse ?: ?/i, '').replace(/\s+/g, ' ').trim();
	for (const [re, ordre] of MOTIFS_SUJET) {
		const r = s.match(re);
		if (!r) continue;
		const [a, b] = [r[1].trim(), r[2].replace(/ [–-] (recrute activement|\d+ anciens?.*|faites partie.*|\d+ relations?)$/i, '').trim()];
		const [entreprise, poste] = ordre === 'ep' ? [a, b] : [b, a];
		// « Comment ça se passe chez Admo.tv ? Je recrute… » : une question, pas un poste
		if (/\?/.test(entreprise + poste)) continue;
		return { entreprise: nettoyerEntreprise(entreprise), poste };
	}
	const opp = s.match(/^opportunit[ée] ?[-–:]? ?(.+)$/i);
	if (opp) {
		const parts = opp[1].split(/ [-–] /);
		if (parts.length > 1) return { poste: parts.slice(0, -1).join(' – '), entreprise: nettoyerEntreprise(parts.at(-1)!) };
		// « Opportunité Infotel » : un nom court est l'entreprise ; une phrase longue reste sans entreprise
		if (parts[0].split(' ').length <= 3) return { poste: null, entreprise: parts[0] };
	}
	return { entreprise: null, poste: null };
}

/** « Senior Tech Recruiter @Free », « Recruitment @Infotel » : l'entreprise du recruteur interne */
export function entrepriseDuRole(role: string | null | undefined): string | null {
	return role?.match(/@ ?([\p{L}\d.&' -]+?)\s*$/u)?.[1].trim() ?? null;
}

// ---------------------------------------------------------------- localisation

const LIEUX: [RegExp, string][] = [
	[/\bnimes\b/, 'Nîmes'],
	[/\bmontpellier\b/, 'Montpellier'],
	[/\bavignon\b/, 'Avignon'],
	[/\bales\b/, 'Alès'],
	[/\barles\b/, 'Arles'],
	[/\bmarseille\b/, 'Marseille'],
	[/\baix[- ]en[- ]provence\b/, 'Aix-en-Provence'],
	[/\btoulouse\b/, 'Toulouse'],
	[/\blyon\b/, 'Lyon'],
	[/\bparis\b|ile-de-france/, 'Paris'],
	[/\bbordeaux\b/, 'Bordeaux'],
	[/\bnantes\b/, 'Nantes'],
	[/\blille\b/, 'Lille'],
	[/\bbruxelles\b|\bbrussels\b/, 'Bruxelles'],
	[/full remote|a distance|\bremote\b|100 ?% teletravail/, 'À distance']
];

export function lieuxDe(texte: string): string[] {
	const t = sansAccents(texte);
	return LIEUX.filter(([re]) => re.test(t)).map(([, nom]) => nom);
}

export function zoneDe(lieux: string[], zoneProche: string[]): Zone {
	if (!lieux.length) return 'inconnue';
	const proches = zoneProche.map(sansAccents);
	if (lieux.some((l) => proches.includes(sansAccents(l)))) return 'proche';
	if (lieux.includes('À distance')) return 'à distance';
	return proches.length ? 'loin' : 'inconnue';
}

// ---------------------------------------------------------------- sérieux du lead

export function salaireDe(texte: string): string | null {
	const plage = texte.match(/\b(\d{2,3}) ?(?:k|000)? ?(?:€|eur)? ?(?:à|-|–|\/) ?(\d{2,3}) ?(?:k|000)\b/i);
	if (plage && +plage[1] < +plage[2]) return `${plage[1]}–${plage[2]} k€`;
	const seul = texte.match(/\b(\d{2,3}) ?(?:k|000) ?(?:€|eur)/i) ?? texte.match(/\b(\d{2,3}) ?k\b/i);
	return seul ? `${seul[1]} k€` : null;
}

export function intermediaireDe(m: Mail): Intermediaire {
	const tout = sansAccents([m.expediteur, m.nom, m.role, m.sujet, m.extrait].filter(Boolean).join(' '));
	if (PLATEFORMES.some((p) => tout.includes(p)) || ALERTES.includes(m.expediteur.toLowerCase())) return 'plateforme';
	if (ESN.some((e) => new RegExp(`\\b${e}\\b`).test(tout))) return 'ESN';
	if (CABINETS.some((c) => tout.includes(c))) return 'cabinet';
	if (/recruit(?:er|ment) @|talent acquisition|\bdrh\b|rh chez|cto|founder|fondat/.test(tout)) return 'en direct';
	return 'inconnu';
}

export function serieuxDe(m: Mail, type: Type, intermediaire: Intermediaire): { serieux: Serieux; indices: string[] } {
	const texte = sansAccents(`${m.sujet} ${m.extrait ?? ''}`);
	const indices: string[] = [];
	let points = 0;
	if (salaireDe(`${m.sujet} ${m.extrait ?? ''}`)) (points++, indices.push('salaire annoncé'));
	if (/client final|\bcdi\b|founding|bras droit|engineering manager|tech lead|lead dev|staff|principal/.test(texte))
		(points++, indices.push('poste précis'));
	if (/stack|python|rust|java|php|symfony|node|typescript|dbt|bigquery|spring|react|vue|elixir|ruby/.test(texte))
		(points++, indices.push('stack détaillée'));
	if (/relance|je reviens vers toi|je reviens vers vous/.test(texte) || (m.nb_messages ?? 1) > 1) (points++, indices.push('relance'));
	if (/plusieurs de mes clients|differentes opportunites|nos clients|nos activites|nouvelle mission|un profil comme le votre/.test(texte))
		(points -= 2, indices.push('approche générique'));
	if (intermediaire === 'ESN') (points--, indices.push('ESN / régie'));
	if (intermediaire === 'plateforme') (points--, indices.push('envoi de masse'));
	if (intermediaire === 'en direct') (points++, indices.push('recruteur interne'));
	if (type === 'alerte') return { serieux: 'vague', indices: ['alerte automatique'] };
	return { serieux: points >= 3 ? 'sérieux' : points >= 1 ? 'à creuser' : 'vague', indices };
}

// ---------------------------------------------------------------- fraîcheur

/** Seuils en jours : un contact direct reste valable plus longtemps qu'une annonce LinkedIn */
export const SEUILS: Record<Type, [number, number]> = {
	recruteur: [21, 60],
	alerte: [10, 30],
	demarche: [30, 90],
	autre: [30, 90]
};

export function ageJours(le: string, maintenant: Date): number {
	const t = Date.parse(le);
	return Number.isNaN(t) ? 9999 : Math.max(0, Math.floor((maintenant.getTime() - t) / 86_400_000));
}

export function fraicheurDe(type: Type, age: number): Fraicheur {
	const [frais, tiede] = SEUILS[type];
	return age <= frais ? 'frais' : age <= tiede ? 'tiède' : 'périmé';
}

// ---------------------------------------------------------------- tout ensemble

export function analyser(m: Mail, maintenant: Date, zoneProche: string[] = []): Opportunite {
	const type = typeDe(m);
	const lu = entrepriseEtPoste(m.sujet);
	const { poste } = lu;
	const entreprise = lu.entreprise ?? entrepriseDuRole(m.role);
	const intermediaire = type === 'demarche' ? 'inconnu' : intermediaireDe(m);
	const { serieux, indices } = type === 'recruteur' || type === 'alerte' ? serieuxDe(m, type, intermediaire) : { serieux: 'vague' as Serieux, indices: [] };
	const texte = `${m.sujet} ${m.role ?? ''} ${m.extrait ?? ''}`;
	const lieux = lieuxDe(texte);
	const zone = zoneDe(lieux, zoneProche);
	const age_jours = ageJours(m.le, maintenant);
	const fraicheur = fraicheurDe(type, age_jours);
	// Un échange = j'ai répondu (une relance du recruteur n'en est pas un)
	const echange = /^message ayant reçu une réponse/i.test(m.sujet) || /j'ai répondu/i.test(m.extrait ?? '');
	const score =
		{ recruteur: 30, alerte: 10, demarche: 5, autre: 0 }[type] +
		{ sérieux: 25, 'à creuser': 12, vague: 0 }[serieux] +
		// La fraîcheur pèse plus que le sérieux : un bon lead de 6 mois est sans doute pourvu
		{ frais: 35, tiède: 20, périmé: 0 }[fraicheur] +
		{ proche: 10, 'à distance': 8, inconnue: 3, loin: 0 }[zone] +
		(m.non_lu ? 2 : 0);
	return { ...m, type, echange, entreprise, poste, intermediaire, serieux, indices, salaire: salaireDe(texte), lieux, zone, age_jours, fraicheur, score };
}

export type Filtres = {
	recherche: string;
	types: Type[];
	serieux: Serieux[];
	fraicheurs: Fraicheur[];
	zones: Zone[];
	/** Statuts de suivi à montrer ('nouveau' = pas encore de suivi) ; vide = tous sauf écarté et archivé */
	statuts: (StatutSuivi | 'nouveau')[];
};

export const statutDe = (o: Opportunite, suivi: Record<string, Suivi>): StatutSuivi | 'nouveau' => suivi[o.id]?.statut ?? 'nouveau';

export function filtrer(ops: Opportunite[], f: Filtres, suivi: Record<string, Suivi>): Opportunite[] {
	const q = sansAccents(f.recherche.trim());
	return ops
		.filter((o) => !f.types.length || f.types.includes(o.type))
		.filter((o) => !f.serieux.length || f.serieux.includes(o.serieux))
		.filter((o) => !f.fraicheurs.length || f.fraicheurs.includes(o.fraicheur))
		.filter((o) => !f.zones.length || f.zones.includes(o.zone))
		.filter((o) => {
			const s = statutDe(o, suivi);
			return f.statuts.length ? f.statuts.includes(s) : s !== 'ecarte' && s !== 'archive';
		})
		.filter((o) => !q || sansAccents([o.sujet, o.nom, o.entreprise, o.extrait, o.expediteur, suivi[o.id]?.note].filter(Boolean).join(' ')).includes(q))
		.sort((a, b) => b.score - a.score || a.age_jours - b.age_jours);
}

/** Même offre reçue plusieurs fois (LinkedIn renvoie une annonce sous 3 ou 4 sujets, un recruteur relance) : une seule
 * carte par entreprise et poste, la mieux classée, avec le nombre de mails regroupés. */
export function regrouperDoublons<T extends Opportunite>(ops: T[]): (T & { doublons: number })[] {
	const vus = new Map<string, T & { doublons: number }>();
	const resultat: (T & { doublons: number })[] = [];
	for (const o of ops) {
		const cle = o.entreprise && (o.poste || o.type === 'recruteur') ? sansAccents(`${o.type}|${o.entreprise}|${o.poste ?? ''}`) : o.id;
		const deja = vus.get(cle);
		if (deja) deja.doublons++;
		else {
			const avec = { ...o, doublons: 0 };
			vus.set(cle, avec);
			resultat.push(avec);
		}
	}
	return resultat;
}

export function compter<T extends string>(ops: Opportunite[], cle: (o: Opportunite) => T): Record<T, number> {
	const r = {} as Record<T, number>;
	for (const o of ops) r[cle(o)] = (r[cle(o)] ?? 0) + 1;
	return r;
}

export const lienGmail = (id: string) => `https://mail.google.com/mail/u/0/#all/${id}`;

export function ageLisible(j: number): string {
	if (j === 0) return "aujourd'hui";
	if (j === 1) return 'hier';
	if (j < 30) return `il y a ${j} j`;
	if (j < 365) return `il y a ${Math.round(j / 30)} mois`;
	return `il y a ${Math.round(j / 365)} an${j >= 730 ? 's' : ''}`;
}
