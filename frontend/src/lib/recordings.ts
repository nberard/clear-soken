// Mémos vocaux : stockés uniquement sur le téléphone, dans IndexedDB
// (localStorage est trop petit pour de l'audio). Rien n'est envoyé au serveur.

export type Recording = {
	id: string;
	at: string; // ISO
	title: string;
	duration: number; // secondes (mesurée pendant l'enregistrement : les webm n'ont pas de durée fiable)
	type: string; // type MIME
	blob: Blob;
};

export const VOICE_DB = 'clearsoken-voix';
const STORE = 'recordings';

function openDb(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(VOICE_DB, 1);
		req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

async function tx<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
	const db = await openDb();
	return new Promise<T>((resolve, reject) => {
		const t = db.transaction(STORE, mode);
		const req = run(t.objectStore(STORE));
		t.oncomplete = () => {
			db.close();
			resolve(req.result);
		};
		t.onerror = () => {
			db.close();
			reject(t.error);
		};
	});
}

export async function listRecordings(): Promise<Recording[]> {
	try {
		const all = await tx<Recording[]>('readonly', (s) => s.getAll());
		return all.sort((a, b) => b.at.localeCompare(a.at));
	} catch {
		return [];
	}
}

export function saveRecording(r: Recording): Promise<IDBValidKey> {
	return tx('readwrite', (s) => s.put(r));
}

export function deleteRecording(id: string): Promise<undefined> {
	return tx('readwrite', (s) => s.delete(id));
}

export function wipeRecordings(): void {
	try {
		indexedDB.deleteDatabase(VOICE_DB);
	} catch {
		/* rien à faire */
	}
}

export function fmtDuration(sec: number): string {
	const s = Math.max(0, Math.round(sec));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function fileExt(type: string): string {
	if (type.includes('mp4') || type.includes('aac')) return 'm4a';
	if (type.includes('ogg')) return 'ogg';
	return 'webm';
}
