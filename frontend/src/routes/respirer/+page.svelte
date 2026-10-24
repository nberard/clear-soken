<script lang="ts">
	import { onDestroy } from 'svelte';

	// Cohérence cardiaque : 5 s inspiration / 5 s expiration (6 respirations par minute).
	const HALF = 5;
	const durations = [2, 5];

	let minutes = $state(2);
	let running = $state(false);
	let elapsed = $state(0);
	let timer: ReturnType<typeof setInterval> | undefined;

	let phase = $derived(Math.floor(elapsed / HALF) % 2 === 0 ? 'Inspire' : 'Expire');
	let remaining = $derived(Math.max(0, minutes * 60 - elapsed));

	function start() {
		elapsed = 0;
		running = true;
		timer = setInterval(() => {
			elapsed += 1;
			if (elapsed >= minutes * 60) stop();
		}, 1000);
	}

	function stop() {
		running = false;
		clearInterval(timer);
	}

	onDestroy(stop);

	const grounding = [
		'5 choses que tu vois',
		'4 choses que tu peux toucher',
		'3 sons que tu entends',
		'2 odeurs que tu sens',
		'1 chose que tu aimes chez toi'
	];
	let groundStep = $state(-1);
</script>

<h1>Respirer</h1>
<p class="lead">Laisse le cercle guider ta respiration.</p>

<div class="card center">
	<div class="circle" class:on={running} style:--half="{HALF}s" aria-hidden="true"></div>
	{#if running}
		<p class="phase" aria-live="polite">{phase}</p>
		<p class="muted">{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}</p>
		<button class="btn secondary" onclick={stop}>Arrêter</button>
	{:else}
		{#if elapsed > 0}<p class="phase">Bravo 🌿</p>{/if}
		<div class="choices" role="radiogroup" aria-label="Durée">
			{#each durations as d (d)}
				<button role="radio" aria-checked={minutes === d} class="btn secondary" class:sel={minutes === d} onclick={() => (minutes = d)}>{d} min</button>
			{/each}
		</div>
		<button class="btn" onclick={start}>Commencer</button>
	{/if}
</div>

<h2>Revenir ici et maintenant</h2>
<div class="card">
	<p class="muted">L’exercice 5-4-3-2-1 aide quand les pensées s’emballent.</p>
	{#if groundStep < 0}
		<button class="btn" onclick={() => (groundStep = 0)}>Commencer</button>
	{:else if groundStep < grounding.length}
		<p class="phase">{grounding[groundStep]}</p>
		<button class="btn" onclick={() => groundStep++}>Suivant</button>
	{:else}
		<p class="phase">Tu es là. 💛</p>
		<button class="btn secondary" onclick={() => (groundStep = -1)}>Recommencer</button>
	{/if}
</div>

<style>
	.center { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 0.6rem; }
	.circle {
		width: 160px;
		height: 160px;
		margin: 1rem auto;
		border-radius: 50%;
		background: radial-gradient(circle, var(--primary-soft), var(--primary));
		transform: scale(0.6);
	}
	.circle.on { animation: breathe calc(var(--half) * 2) ease-in-out infinite; }
	@keyframes breathe {
		0%, 100% { transform: scale(0.6); }
		50% { transform: scale(1); }
	}
	.phase { font-size: 1.3rem; font-weight: 700; }
	.choices { display: flex; gap: 0.5rem; }
	.sel { outline: 2px solid var(--primary); }
</style>
