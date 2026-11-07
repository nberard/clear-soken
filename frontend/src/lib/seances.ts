// « Mes séances » : préparer ses séances (psy, psychiatre…) et en garder une trace.
// Tout reste sur le téléphone (voir storage.ts). La sauvegarde exportée est chiffrée avec un mot de passe que la
// personne choisit (AES-GCM, clé dérivée par PBKDF2) : le fichier est illisible sans lui, et ce mot de passe ne
// quitte jamais le téléphone. Le même chiffrement servira à une synchronisation (V2) où le serveur ne stockerait
// que des données illisibles — à condition d'un hébergement HDS et d'une AIPD (voir README).

export type Sujet = { id: string; texte: string; fait: boolean };

export type Seance = {
	id: string;
	date: string | null; // AAAA-MM-JJ, null pour une note sans date
	soignant: string; // « psychologue », un prénom… libre
	intitule: string; // pour les entrées sans date (« Jour 3 »)
	texte: string; // notes de la séance
	essayer: string; // à essayer d'ici la prochaine fois
	ressenti: number; // 0 = pas noté, 1 à 5
	themes: string[];
};

export type Prochaine = { date: string; soignant: string; sujets: Sujet[] };

export const PROCHAINE_VIDE: Prochaine = { date: '', soignant: '', sujets: [] };

export const RESSENTIS = [
	{ value: 1, label: 'Très dure' },
	{ value: 2, label: 'Difficile' },
	{ value: 3, label: 'Mitigée' },
	{ value: 4, label: 'Utile' },
	{ value: 5, label: 'Très utile' }
] as const;

export function nouvelleSeance(id: string, date: string | null = null): Seance {
	return { id, date, soignant: '', intitule: '', texte: '', essayer: '', ressenti: 0, themes: [] };
}

/** Plus récentes d'abord ; les notes sans date à la fin. */
export function trier(seances: Seance[]): Seance[] {
	return [...seances].sort((a, b) => (b.date ?? '0000').localeCompare(a.date ?? '0000'));
}

/** Démarre la séance prévue : les sujets non abordés deviennent le début des notes, ceux cochés disparaissent. */
export function demarrer(prochaine: Prochaine, id: string, aujourdhui: string): { seance: Seance; reste: Prochaine } {
	const ouverts = prochaine.sujets.filter((s) => !s.fait);
	const seance = nouvelleSeance(id, prochaine.date || aujourdhui);
	seance.soignant = prochaine.soignant;
	if (ouverts.length) seance.texte = 'Sujets prévus :\n' + ouverts.map((s) => '- ' + s.texte).join('\n') + '\n\n';
	return { seance, reste: { ...PROCHAINE_VIDE, soignant: prochaine.soignant } };
}

export function rechercher(seances: Seance[], q: string, theme: string | null): Seance[] {
	const t = q.trim().toLowerCase();
	return seances.filter(
		(s) =>
			(!theme || s.themes.includes(theme)) &&
			(!t || [s.texte, s.essayer, s.intitule, s.soignant, s.themes.join(' ')].join(' ').toLowerCase().includes(t))
	);
}

export function themes(seances: Seance[]): { theme: string; n: number }[] {
	const n = new Map<string, number>();
	seances.forEach((s) => s.themes.forEach((t) => n.set(t, (n.get(t) ?? 0) + 1)));
	return [...n].map(([theme, k]) => ({ theme, n: k })).sort((a, b) => a.theme.localeCompare(b.theme));
}

export function lireThemes(saisie: string): string[] {
	return [...new Set(saisie.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean))];
}

/** Séances par mois, du premier au dernier mois connus (mois sans séance inclus, à 0). */
export function parMois(seances: Seance[]): { mois: string; n: number }[] {
	const mois = seances.filter((s) => s.date).map((s) => s.date!.slice(0, 7)).sort();
	if (!mois.length) return [];
	const compte = new Map<string, number>();
	mois.forEach((m) => compte.set(m, (compte.get(m) ?? 0) + 1));
	const out: { mois: string; n: number }[] = [];
	let [y, m] = mois[0].split('-').map(Number);
	const [yf, mf] = mois[mois.length - 1].split('-').map(Number);
	while (y < yf || (y === yf && m <= mf)) {
		const k = `${y}-${String(m).padStart(2, '0')}`;
		out.push({ mois: k, n: compte.get(k) ?? 0 });
		if (++m > 12) { m = 1; y++; }
	}
	return out;
}

/** Fichier produit par clearmind-tools/keep.py (notes Google Keep découpées par séance) ou export non chiffré. */
export function depuisFichier(json: unknown, uid: () => string): Seance[] | null {
	const liste = Array.isArray(json) ? json : (json as { seances?: unknown })?.seances;
	if (!Array.isArray(liste)) return null;
	return liste
		.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
		.map((x) => ({
			...nouvelleSeance(typeof x.id === 'string' ? x.id : uid(), typeof x.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(x.date) ? x.date : null),
			soignant: typeof x.soignant === 'string' ? x.soignant : '',
			intitule: typeof x.intitule === 'string' && x.intitule !== 'Sans date' ? x.intitule : '',
			texte: typeof x.texte === 'string' ? x.texte : '',
			essayer: typeof x.essayer === 'string' ? x.essayer : '',
			ressenti: typeof x.ressenti === 'number' && x.ressenti >= 0 && x.ressenti <= 5 ? Math.round(x.ressenti) : 0,
			themes: Array.isArray(x.themes) ? x.themes.filter((t): t is string => typeof t === 'string') : []
		}));
}

/** Fusionne sans doublon (même date et même texte) : un import ne duplique pas ce qui est déjà là. */
export function fusionner(existantes: Seance[], nouvelles: Seance[]): Seance[] {
	const cle = (s: Seance) => `${s.date}|${s.texte.trim()}`;
	const vus = new Set(existantes.map(cle));
	return [...existantes, ...nouvelles.filter((s) => !vus.has(cle(s)))];
}

// --------------------------------------------------------------------------- sauvegarde chiffrée

export const FORMAT = 'clearsoken-seances';
const ITERATIONS = 310_000; // PBKDF2-SHA256, recommandation OWASP

export type Sauvegarde = { format: typeof FORMAT; v: 1; kdf: 'PBKDF2-SHA256'; iter: number; salt: string; iv: string; data: string };

const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u));
const deb64 = (s: string): Uint8Array<ArrayBuffer> => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

async function cle(motDePasse: string, salt: Uint8Array<ArrayBuffer>, iter: number): Promise<CryptoKey> {
	const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(motDePasse), 'PBKDF2', false, ['deriveKey']);
	return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations: iter }, base, { name: 'AES-GCM', length: 256 }, false, [
		'encrypt',
		'decrypt'
	]);
}

export async function chiffrer(contenu: unknown, motDePasse: string): Promise<Sauvegarde> {
	const salt = crypto.getRandomValues(new Uint8Array(16));
	const iv = crypto.getRandomValues(new Uint8Array(12));
	const k = await cle(motDePasse, salt, ITERATIONS);
	const data = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, k, new TextEncoder().encode(JSON.stringify(contenu))));
	return { format: FORMAT, v: 1, kdf: 'PBKDF2-SHA256', iter: ITERATIONS, salt: b64(salt), iv: b64(iv), data: b64(data) };
}

/** null si le mot de passe est faux (ou le fichier abîmé) : AES-GCM vérifie l'intégrité. */
export async function dechiffrer(s: Sauvegarde, motDePasse: string): Promise<unknown | null> {
	try {
		const k = await cle(motDePasse, deb64(s.salt), s.iter);
		const clair = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: deb64(s.iv) }, k, deb64(s.data));
		return JSON.parse(new TextDecoder().decode(clair));
	} catch {
		return null;
	}
}

export function estSauvegarde(x: unknown): x is Sauvegarde {
	return !!x && typeof x === 'object' && (x as Sauvegarde).format === FORMAT && typeof (x as Sauvegarde).data === 'string';
}
