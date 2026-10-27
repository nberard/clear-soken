<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/state';
	import { uid } from '#lib/storage.ts';
	import {
		listRecordings,
		saveRecording,
		deleteRecording,
		fmtDuration,
		fileExt,
		type Recording
	} from '#lib/recordings.ts';

	// $state.raw : les objets restent « bruts » pour pouvoir être enregistrés dans IndexedDB.
	let recs: Recording[] = $state.raw([]);
	let recording = $state(false);
	let seconds = $state(0);
	let level = $state(0);
	let error = $state('');
	let fresh = $state(''); // id du dernier mémo, mis en valeur

	let mr: MediaRecorder | null = null;
	let stream: MediaStream | null = null;
	let ctx: AudioContext | null = null;
	let chunks: Blob[] = [];
	let raf = 0;
	let tick: ReturnType<typeof setInterval> | undefined;
	let startedAt = 0;
	let stoppedAt = 0;
	let wakeLock: { release(): Promise<void> } | null = null;

	onMount(async () => {
		recs = await listRecordings();
		// Raccourci de l'icône Android (appui long) : /voix/?go=1 démarre directement
		if (page.url.searchParams.has('go')) start();
	});

	function pickType(): string {
		const types = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus', 'audio/webm'];
		return types.find((t) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) ?? '';
	}

	async function start() {
		if (recording) return;
		error = '';
		stopPlayback();
		try {
			stream = await navigator.mediaDevices.getUserMedia({
				audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
			});
		} catch (e) {
			const name = (e as DOMException)?.name;
			error =
				name === 'NotAllowedError'
					? 'Le micro est bloqué. Autorise-le dans les réglages du navigateur, puis réessaie.'
					: 'Aucun micro trouvé sur cet appareil.';
			return;
		}

		const type = pickType();
		mr = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
		chunks = [];
		mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
		mr.onstop = finish;
		mr.start(1000);

		// Niveau sonore pour l'anneau qui « respire » avec la voix
		try {
			ctx = new AudioContext();
			await ctx.resume();
			const analyser = ctx.createAnalyser();
			analyser.fftSize = 512;
			ctx.createMediaStreamSource(stream).connect(analyser);
			const buf = new Uint8Array(analyser.fftSize);
			const loop = () => {
				analyser.getByteTimeDomainData(buf);
				let sum = 0;
				for (const v of buf) sum += ((v - 128) / 128) ** 2;
				const target = Math.min(1, Math.sqrt(sum / buf.length) * 5);
				level = level * 0.7 + target * 0.3;
				raf = requestAnimationFrame(loop);
			};
			loop();
		} catch {
			/* pas d'indicateur de niveau, l'enregistrement continue */
		}

		startedAt = Date.now();
		seconds = 0;
		tick = setInterval(() => (seconds = Math.floor((Date.now() - startedAt) / 1000)), 250);
		recording = true;
		navigator.vibrate?.(30);
		try {
			// Évite que l'écran se mette en veille et coupe le micro
			wakeLock = await (navigator as any).wakeLock?.request('screen');
		} catch {
			wakeLock = null;
		}
	}

	function stop() {
		if (!recording) return;
		stoppedAt = Date.now();
		recording = false;
		if (mr && mr.state !== 'inactive') mr.stop();
		release();
		navigator.vibrate?.([20, 40, 20]);
	}

	function release() {
		clearInterval(tick);
		cancelAnimationFrame(raf);
		level = 0;
		stream?.getTracks().forEach((t) => t.stop());
		stream = null;
		ctx?.close().catch(() => {});
		ctx = null;
		wakeLock?.release().catch(() => {});
		wakeLock = null;
	}

	async function finish() {
		const duration = (stoppedAt - startedAt) / 1000;
		if (duration < 0.8 || !chunks.length) return; // appui trop bref : on ignore
		const blob = new Blob(chunks, { type: mr?.mimeType || chunks[0].type || 'audio/webm' });
		const at = new Date();
		const rec: Recording = { id: uid(), at: at.toISOString(), title: defaultTitle(at), duration, type: blob.type, blob };
		try {
			await saveRecording(rec);
		} catch {
			error = 'Impossible d’enregistrer sur ce téléphone (mémoire pleine ?).';
			return;
		}
		recs = [rec, ...recs];
		fresh = rec.id;
	}

	function defaultTitle(d: Date): string {
		const day = d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'short' });
		const time = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
		return `${day.charAt(0).toUpperCase() + day.slice(1)} · ${time}`;
	}

	// ---------- Lecture ----------
	let audio: HTMLAudioElement | null = null;
	let playing = $state('');
	let progress = $state(0);
	const urls = new Map<string, string>();

	function urlFor(r: Recording): string {
		let u = urls.get(r.id);
		if (!u) {
			u = URL.createObjectURL(r.blob);
			urls.set(r.id, u);
		}
		return u;
	}

	function togglePlay(r: Recording) {
		if (playing === r.id) {
			stopPlayback();
			return;
		}
		stopPlayback();
		audio = new Audio(urlFor(r));
		audio.ontimeupdate = () => (progress = Math.min(1, (audio?.currentTime ?? 0) / r.duration));
		audio.onended = stopPlayback;
		audio.play().catch(stopPlayback);
		playing = r.id;
		progress = 0;
	}

	function stopPlayback() {
		audio?.pause();
		audio = null;
		playing = '';
		progress = 0;
	}

	// ---------- Actions ----------
	let editing = $state('');
	let draft = $state('');

	function startRename(r: Recording) {
		editing = r.id;
		draft = r.title;
	}

	async function commitRename(r: Recording) {
		if (editing !== r.id) return;
		editing = '';
		const title = draft.trim();
		if (!title || title === r.title) return;
		const updated = { ...r, title };
		recs = recs.map((x) => (x.id === r.id ? updated : x));
		await saveRecording(updated).catch(() => {});
	}

	async function remove(r: Recording) {
		if (!confirm(`Supprimer « ${r.title} » ?`)) return;
		if (playing === r.id) stopPlayback();
		await deleteRecording(r.id).catch(() => {});
		const u = urls.get(r.id);
		if (u) URL.revokeObjectURL(u);
		urls.delete(r.id);
		recs = recs.filter((x) => x.id !== r.id);
	}

	async function share(r: Recording) {
		const name = `${r.title.replace(/[^\p{L}\p{N} _-]+/gu, '').trim() || 'memo'}.${fileExt(r.type)}`;
		const file = new File([r.blob], name, { type: r.type });
		if (navigator.canShare?.({ files: [file] })) {
			try {
				await navigator.share({ files: [file], title: r.title });
			} catch {
				/* partage annulé */
			}
			return;
		}
		const a = document.createElement('a');
		a.href = urlFor(r);
		a.download = name;
		a.click();
	}

	onDestroy(() => {
		stop();
		stopPlayback();
		urls.forEach((u) => URL.revokeObjectURL(u));
	});
</script>

<h1>Ma voix</h1>
<p class="lead">Parfois c’est plus simple de le dire que de l’écrire.</p>

<div class="card recorder" class:on={recording}>
	<button
		class="mic"
		class:on={recording}
		style:--lvl={level}
		onclick={() => (recording ? stop() : start())}
		aria-label={recording ? 'Arrêter l’enregistrement' : 'Commencer un enregistrement'}
		aria-pressed={recording}
	>
		{#if recording}
			<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="3" /></svg>
		{:else}
			<svg viewBox="0 0 24 24" aria-hidden="true">
				<rect x="9" y="3" width="6" height="11" rx="3" />
				<path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
			</svg>
		{/if}
	</button>

	{#if recording}
		<p class="time" aria-live="off">{fmtDuration(seconds)}</p>
		<p class="muted">Je t’écoute… touche pour terminer</p>
	{:else}
		<p class="hint">Touche le micro pour parler</p>
		<p class="muted">Tu peux t’arrêter quand tu veux.</p>
	{/if}

	{#if error}<p class="error" role="alert">{error}</p>{/if}
</div>

{#if recs.length}
	<h2>Mes mémos</h2>
	<ul class="list">
		{#each recs as r (r.id)}
			<li class="card item" class:fresh={fresh === r.id}>
				<button
					class="play"
					class:on={playing === r.id}
					onclick={() => togglePlay(r)}
					aria-label={playing === r.id ? 'Pause' : 'Écouter ' + r.title}
				>
					{#if playing === r.id}
						<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1.5" /><rect x="14" y="5" width="4" height="14" rx="1.5" /></svg>
					{:else}
						<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" /></svg>
					{/if}
				</button>

				<div class="body">
					{#if editing === r.id}
						<!-- svelte-ignore a11y_autofocus -->
						<input
							bind:value={draft}
							autofocus
							maxlength="80"
							aria-label="Nom du mémo"
							onblur={() => commitRename(r)}
							onkeydown={(e) => {
								if (e.key === 'Enter') (e.currentTarget as HTMLInputElement).blur();
								if (e.key === 'Escape') editing = '';
							}}
						/>
					{:else}
						<button class="title" onclick={() => startRename(r)} aria-label="Renommer {r.title}">{r.title}</button>
					{/if}
					<div class="bar" aria-hidden="true">
						<span style:width="{playing === r.id ? progress * 100 : 0}%"></span>
					</div>
					<span class="muted">
						{playing === r.id ? fmtDuration(progress * r.duration) + ' / ' : ''}{fmtDuration(r.duration)}
					</span>
				</div>

				<div class="actions">
					<button class="icon" onclick={() => share(r)} aria-label="Partager {r.title}">
						<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 15V4m0 0L8 8m4-4 4 4M6 12v6a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>
					</button>
					<button class="icon" onclick={() => remove(r)} aria-label="Supprimer {r.title}">
						<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2m-7 0 .8 12a1 1 0 0 0 1 1h4.4a1 1 0 0 0 1-1L17 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" /></svg>
					</button>
				</div>
			</li>
		{/each}
	</ul>
{/if}

<p class="muted privacy">🔒 Tes mémos restent sur ton téléphone. Tu choisis avec qui les partager.</p>

<style>
	.recorder {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: 2rem 1rem 1.5rem;
		gap: 0.25rem;
	}
	.recorder.on { background: var(--accent-soft); border-color: transparent; }

	.mic {
		--lvl: 0;
		--halo: color-mix(in srgb, var(--primary) 22%, transparent);
		width: 132px;
		height: 132px;
		margin: 0.5rem 0 1.4rem;
		border: none;
		border-radius: 50%;
		background: var(--primary);
		color: #fff;
		display: grid;
		place-items: center;
		cursor: pointer;
		box-shadow: 0 0 0 0 var(--halo);
		animation: invite 3s ease-in-out infinite;
		transition: background 0.2s, transform 0.15s;
		touch-action: manipulation;
	}
	.mic:active { transform: scale(0.95); }
	.mic svg { width: 52px; height: 52px; fill: currentColor; }
	.mic.on {
		--halo: color-mix(in srgb, var(--accent) 30%, transparent);
		background: var(--accent);
		animation: none;
		/* le halo grandit avec la voix */
		box-shadow: 0 0 0 calc(8px + var(--lvl) * 34px) var(--halo);
		transition: background 0.2s, box-shadow 0.08s linear;
	}
	@keyframes invite {
		0%, 100% { box-shadow: 0 0 0 0 var(--halo); }
		50% { box-shadow: 0 0 0 14px var(--halo); }
	}

	.time { font-size: 2rem; font-weight: 800; font-variant-numeric: tabular-nums; margin: 0; }
	.hint { font-size: 1.15rem; font-weight: 700; margin: 0; }
	.error { color: var(--danger); font-weight: 600; margin-top: 0.6rem; }

	.list { list-style: none; padding: 0; margin: 0; }
	.item {
		display: flex;
		align-items: center;
		gap: 0.8rem;
		padding: 0.8rem;
	}
	.item.fresh { animation: pop 0.5s ease-out; border-color: var(--primary); }
	@keyframes pop { from { transform: scale(0.96); opacity: 0; } }

	.play {
		flex: none;
		width: 48px;
		height: 48px;
		border-radius: 50%;
		border: none;
		background: var(--primary-soft);
		color: var(--primary);
		display: grid;
		place-items: center;
		cursor: pointer;
	}
	.play.on { background: var(--primary); color: #fff; }
	.play svg { width: 22px; height: 22px; fill: currentColor; }

	.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 0.25rem; }
	.title {
		all: unset;
		font-weight: 700;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		cursor: text;
	}
	.body input { padding: 0.3rem 0.5rem; font-weight: 700; }
	.bar { height: 4px; border-radius: 2px; background: var(--surface-soft); overflow: hidden; }
	.bar span { display: block; height: 100%; background: var(--primary); transition: width 0.25s linear; }

	.actions { display: flex; gap: 0.1rem; }
	.icon {
		width: 40px;
		height: 40px;
		border: none;
		border-radius: 50%;
		background: none;
		color: var(--text-soft);
		display: grid;
		place-items: center;
		cursor: pointer;
	}
	.icon svg { width: 22px; height: 22px; }

	.privacy { text-align: center; margin-top: 1.5rem; }
</style>
