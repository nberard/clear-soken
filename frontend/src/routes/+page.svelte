<script lang="ts">
	import { onMount } from 'svelte';
	import InstallHint from '#lib/components/InstallHint.svelte';
	import { load, MOODS, DEFAULT_STEPS, type MoodEntry, type Step } from '#lib/storage.ts';

	let lastMood: MoodEntry | null = $state(null);
	let done = $state(0);
	let total = $state(DEFAULT_STEPS.length);

	onMount(() => {
		lastMood = load<MoodEntry[]>('moods', [])[0] ?? null;
		const steps = load<Step[]>('steps', DEFAULT_STEPS);
		done = steps.filter((s) => s.doneAt).length;
		total = steps.length;
	});

	const hour = new Date().getHours();
	const hello = hour < 12 ? 'Bonjour' : hour < 18 ? 'Bon après-midi' : 'Bonsoir';
</script>

<h1>{hello} 🌱</h1>
<p class="lead">Un pas après l’autre, à ton rythme.</p>

<InstallHint />

<a class="card tile" href="/humeur/">
	<span class="big" aria-hidden="true">{lastMood ? MOODS[lastMood.mood - 1].emoji : '🌤️'}</span>
	<span>
		<strong>Comment tu te sens ?</strong>
		<span class="muted">{lastMood ? 'Dernière note : ' + MOODS[lastMood.mood - 1].label : 'Noter mon humeur du jour'}</span>
	</span>
</a>

<a class="card tile" href="/respirer/">
	<span class="big" aria-hidden="true">🫧</span>
	<span>
		<strong>Respirer 2 minutes</strong>
		<span class="muted">Cohérence cardiaque guidée</span>
	</span>
</a>

<a class="card tile" href="/voix/">
	<span class="big" aria-hidden="true">🎙️</span>
	<span>
		<strong>Le dire à voix haute</strong>
		<span class="muted">Un mémo vocal, en un geste</span>
	</span>
</a>

<a class="card tile" href="/echelons/">
	<span class="big" aria-hidden="true">🪜</span>
	<span>
		<strong>Mes échelons</strong>
		<span class="muted">{done} / {total} petits pas franchis</span>
	</span>
</a>

<a class="card tile" href="/ressources/">
	<span class="big" aria-hidden="true">🤝</span>
	<span>
		<strong>Après la clinique</strong>
		<span class="muted">Associations, GEM, lieux d’écoute</span>
	</span>
</a>

<p class="muted privacy">🔒 Tes notes et mémos restent sur ton téléphone. Rien n’est envoyé.</p>

<style>
	.tile {
		display: flex;
		gap: 1rem;
		align-items: center;
		color: inherit;
		text-decoration: none;
	}
	.tile > span:last-child { display: flex; flex-direction: column; }
	.big { font-size: 2rem; }
	.privacy { text-align: center; margin-top: 1.5rem; }
</style>
